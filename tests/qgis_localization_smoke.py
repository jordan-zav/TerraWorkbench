"""Real offscreen widgets, live language switching and catalogue leakage audit."""

import json
import os
from pathlib import Path
import re
import sys
import tempfile

from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsSettings, QgsProcessingParameterDefinition
from qgis.PyQt.QtGui import QFont, QFontDatabase

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from TerraWorkbench.ui.i18n import LANGUAGE_KEY, set_language, translate, _ES, _PT_EXACT
from TerraWorkbench.qgis_plugin.provider import TerraWorkbenchProvider
from TerraWorkbench.ui.workflow_dock import FilterStackDock
from TerraWorkbench.ui.knowledge_content import CHAPTERS
from TerraWorkbench.ui.core_presentation import OPERATION_TITLES, operation_title
from TerraWorkbench.ui.process_centre import ProcessCentre
from TerraWorkbench.ui.core_job_dialog import CoreJobDialog


def catalogue(provider):
    result = {}
    for algorithm in provider.algorithms():
        key = algorithm.id()
        result[key + ":title"] = algorithm.displayName()
        result[key + ":group"] = algorithm.group()
        result[key + ":help"] = algorithm.shortHelpString()
        result[key + ":domain"] = translate(getattr(algorithm, "processing_domain", ""))
        for index, (label, value) in enumerate(
            getattr(algorithm, "implementation_details", ())
        ):
            result[f"{key}:library-label:{index}"] = translate(label)
            result[f"{key}:library-value:{index}"] = translate(value)
        clone = algorithm.create()
        for parameter in clone.parameterDefinitions():
            original = algorithm.parameterDefinition(parameter.name())
            assert original.flags() == parameter.flags()
            assert original.defaultValue() == parameter.defaultValue()
            if parameter.flags() & QgsProcessingParameterDefinition.FlagOptional:
                assert not re.search(r"\b(optional|opcional)\b", parameter.description(), re.I)
        for parameter in algorithm.parameterDefinitions():
            result[key + ":" + parameter.name()] = parameter.description()
            if hasattr(parameter, "options"):
                for index, option in enumerate(parameter.options()):
                    result[f"{key}:{parameter.name()}:{index}"] = option
    return result


def cached_windows_smoke(app, destination):
    from threading import Event
    from time import monotonic, sleep
    from qgis.PyQt.QtWidgets import QMainWindow, QTreeWidgetItemIterator

    from TerraWorkbench.qgis_plugin.plugin import TerraWorkbenchPlugin

    def selected_process(centre, key):
        items = QTreeWidgetItemIterator(centre.tree)
        while items.value() is not None:
            if items.value().data(0, 256) == key:
                return items.value()
            items += 1
        raise AssertionError(key)

    def wait_for_workspace(dialog):
        deadline = monotonic() + 8
        while dialog.worker is not None and monotonic() < deadline:
            app.processEvents()
            sleep(0.01)
        assert dialog.worker is None

    class Interface:
        def __init__(self):
            self.window = QMainWindow()

        def mainWindow(self):
            return self.window

    set_language("es")
    plugin = TerraWorkbenchPlugin(Interface())
    plugin.filter_stack_dock = dock = FilterStackDock(plugin.iface.mainWindow())
    dock.languageChanged.connect(plugin.retranslate)
    plugin.show_processes()
    plugin.show_workspace()
    centre, workspace = plugin.process_dialog, plugin.workspace_dialog
    destination.mkdir(parents=True, exist_ok=True)
    workspace.set_project(destination / "workspace", create=True)
    source = destination / "source.csv"
    source.write_text("x,y,mag\n1,2,3\n4,5,6\n", encoding="utf-8")
    workspace.store.import_file(source)
    workspace.refresh()
    workspace.databases_list.item(0).setSelected(True)
    workspace.channels_list.item(0).setSelected(True)
    workspace.preview()
    wait_for_workspace(workspace)
    workspace.filter_values.setText("3")
    workspace.tasks.toggle.setChecked(True)

    key = "core:depth.euler_window"
    centre.mode.setCurrentIndex(centre.mode.findData("core"))
    centre.search.setText("euler_window")
    centre.tree.setCurrentItem(selected_process(centre, key))
    assert "Procesos geofísicos" in centre.windowTitle()
    assert "Ventana Euler" in centre.browser.toPlainText()
    assert "Filas 1" in workspace.page_status.text()
    assert dock.import_geosoft_action.text() == "Inventario y exportación de GeoDatabase Geosoft…"
    previous_rows = workspace.table.model().rowCount()
    previous_selection = workspace.selected_databases(), workspace.selected_channels()

    settings = dock.settings_dialog
    settings.load()
    settings.language_combo.setCurrentIndex(settings.language_combo.findData("en"))
    settings.save()
    app.processEvents()
    assert plugin.process_dialog is centre and plugin.workspace_dialog is workspace
    assert "Geophysical processes" in centre.windowTitle()
    assert centre.search.text() == "euler_window" and centre.mode.currentData() == "core"
    assert centre.tree.currentItem().data(0, 256) == key
    assert "Source depth" in centre.tree.currentItem().parent().text(0)
    assert centre.tree.currentItem().text(0) == "Euler window"
    assert "Euler window" in centre.browser.toPlainText()
    assert "Ventana Euler" not in centre.browser.toPlainText()
    assert "visible /" in centre.count.text()
    assert workspace.windowTitle() == "Survey databases"
    assert workspace.views.tabText(0) == "Table"
    assert workspace.filter_values.placeholderText() == "Values separated by commas"
    assert workspace.filter_values.text() == "3"
    assert "Selection rows 1" in workspace.page_status.text()
    assert workspace.status.text() == workspace.page_status.text()
    assert workspace.table.model().rowCount() == previous_rows
    assert (workspace.selected_databases(), workspace.selected_channels()) == previous_selection
    assert workspace.tasks.tree.topLevelItem(0).text(1) == "Completed"
    assert workspace.tasks.toggle.isChecked()
    assert "Knowledge Base" in dock.knowledge_base.windowTitle()
    centre.resize(1180, 780)
    centre.show()
    app.processEvents()
    assert centre.grab().save(str(destination / "process-centre-en.png"))

    completed = Event()
    def operation(cancel, progress):
        assert completed.wait(5)
        return "Test task"

    workspace.start(operation)
    worker = workspace.worker
    try:
        settings.load()
        settings.language_combo.setCurrentIndex(settings.language_combo.findData("pt"))
        settings.save()
        assert workspace.worker is worker
        assert workspace.tasks.active["item"].text(1) == "Em execução"
    finally:
        completed.set()
        wait_for_workspace(workspace)
    assert dock.import_geosoft_action.text() == "Inventário e exportação do GeoDatabase Geosoft…"
    assert workspace.windowTitle() == "Bancos de levantamentos"
    centre.close()
    workspace.close()
    dock.disconnect_project()
    plugin.iface.mainWindow().close()
    print("PASS: cached process centre, survey workspace and Geosoft action switch languages live")


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    if os.name == "nt":
        QFontDatabase.addApplicationFont(
            str(Path(os.environ["WINDIR"]) / "Fonts/arial.ttf")
        )
    app.setFont(QFont("Arial", 10))
    sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python/plugins"))
    from processing.core.Processing import Processing

    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    settings = QgsSettings()
    previous = settings.value(LANGUAGE_KEY) if settings.contains(LANGUAGE_KEY) else None
    if destination := os.environ.get("TW_HOT_LANGUAGE_CAPTURE"):
        try:
            cached_windows_smoke(app, Path(destination))
        finally:
            if previous is None:
                settings.remove(LANGUAGE_KEY)
            else:
                settings.setValue(LANGUAGE_KEY, previous)
            QgsProject.instance().clear()
            QgsApplication.processingRegistry().removeProvider(provider)
            app.exitQgis()
        return
    root = Path(tempfile.gettempdir()) / "localization"
    root.mkdir()
    dock = None
    leaks = {}
    try:
        set_language("en")
        provider.refreshAlgorithms()
        english = catalogue(provider)
        layer = QgsRasterLayer(
            str(
                Path(__file__).resolve().parents[1]
                / "sample_data/synthetic/synthetic_magnetic_anomaly.tif"
            ),
            "Synthetic magnetic grid",
        )
        QgsProject.instance().addMapLayer(layer)
        dock = FilterStackDock()
        dock.resize(460, 850)
        dock.algorithm_combo.setCurrentIndex(
            dock.algorithm_combo.findData("terraworkbench:butterworth_lowpass")
        )
        dock.add_step()
        dock.filter_info.set_algorithm(
            QgsApplication.processingRegistry().algorithmById(
                "terraworkbench:butterworth_lowpass"
            )
        )
        dock._parameter_editors["WAVELENGTH"][0].setText("432.5")
        for locale, title in (
            ("en", "Cutoff wavelength"),
            ("es", "Longitud de onda"),
            ("pt", "Comprimento de onda"),
        ):
            set_language(locale)
            provider.refreshAlgorithms()
            dock.retranslate()
            app.processEvents()
            assert title in dock._parameter_editors["WAVELENGTH"][1].description()
            assert dock._parameter_editors["WAVELENGTH"][0].text() == "432.5"
            assert dock.steps()[0].parameters["WAVELENGTH"] == 432.5
            dock.parameters_button.click()
            app.processEvents()
            assert dock.inspector.grab().save(str(root / f"parameters_{locale}.png"))
            knowledge = dock.knowledge_base
            knowledge.chapter_search.clear()
            assert knowledge.chapter_picker.count() == len(CHAPTERS)
            for chapter in CHAPTERS:
                knowledge.chapter_picker.setCurrentIndex(
                    knowledge.chapter_picker.findData(chapter[0])
                )
                assert (
                    chapter[1][("en", "es", "pt").index(locale)]
                    in knowledge.handbook_browser.toPlainText()
                )
            knowledge.chapter_search.setText("Butterworth")
            assert knowledge.chapter_picker.count() >= 1
            knowledge.chapter_search.setText("no_such_chapter_996")
            assert knowledge.chapter_picker.count() == 0
            knowledge.chapter_search.clear()
            knowledge.chapter_picker.setCurrentIndex(
                knowledge.chapter_picker.findData("em")
            )
            knowledge.show()
            app.processEvents()
            assert knowledge.grab().save(str(root / f"knowledge_{locale}.png"))
            centre = ProcessCentre()
            centre.show()
            count = 0
            for index in range(centre.tree.topLevelItemCount()):
                group = centre.tree.topLevelItem(index)
                for row in range(group.childCount()):
                    item = group.child(row)
                    key = item.data(0, 256)
                    if key.startswith("core:"):
                        count += 1
                        assert item.text(0) == operation_title(key[5:])
                        if key == "core:mt.layered_forward":
                            centre.tree.setCurrentItem(item)
            assert count == len(OPERATION_TITLES)
            app.processEvents()
            assert centre.grab().save(str(root / f"processes_{locale}.png"))
            centre.close()
            centre.deleteLater()
            console = CoreJobDialog("gpr.dewow")
            assert not console.contract.isVisible()
            assert set(console.parameter_form.fields) == {
                "traces",
                "dt_s",
                "window_samples",
            }
            console.show_progress("Reading explicit inputs")
            if locale != "en":
                assert console.status.text() != "Reading explicit inputs"
            console.show()
            app.processEvents()
            assert console.grab().save(str(root / f"console_{locale}.png"))
            console.close()
            console.deleteLater()
            translated = catalogue(provider)
            leaks[locale] = {
                key: value
                for key, value in translated.items()
                if locale != "en"
                and value == english[key]
                and len(re.findall(r"[A-Za-z]{3,}", value)) >= 2
            }
            neutral = {
                "NumPy",
                "SciPy",
                "Harmonica",
                "SimPEG",
                "GDAL",
                "QGIS",
                "lasio",
                "ndimage",
                "cKDTree",
                "ppigrf",
                "xarray",
                "FFT",
                "SI",
                "VTK",
                "NPZ",
                "CSV",
                "JSON",
                "GPL",
                "BSD",
                "MIT",
            }
            exact = _ES if locale == "es" else _PT_EXACT
            if locale != "en":
                for key, source in english.items():
                    if ":library-value:" not in key and not key.endswith(":domain"):
                        continue
                    words = re.findall(r"[A-Za-z]+", source)
                    if (
                        any(word not in neutral for word in words)
                        and source not in exact
                    ):
                        leaks[locale][key + ":missing-exact"] = source
            print(
                "PASS",
                locale,
                "catalogue strings",
                len(translated),
                "unchanged English phrases",
                len(leaks[locale]),
                flush=True,
            )
        (root / "catalogue_audit.json").write_text(
            json.dumps(leaks, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        assert not any(leaks.values()), leaks
        print("CAPTURES", root, flush=True)
    finally:
        if dock is not None:
            dock.disconnect_project()
            dock.close()
            dock.deleteLater()
            app.processEvents()
        if previous is None:
            settings.remove(LANGUAGE_KEY)
        else:
            settings.setValue(LANGUAGE_KEY, previous)
        QgsProject.instance().clear()
        QgsApplication.processingRegistry().removeProvider(provider)
        app.exitQgis()


if __name__ == "__main__":
    main()

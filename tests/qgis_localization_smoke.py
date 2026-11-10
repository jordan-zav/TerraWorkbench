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

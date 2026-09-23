"""Build and render the Filter Stack in a real QGIS Qt runtime."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile


PROJECT_PARENT = Path(
    os.environ.get(
        "TERRAWORKBENCH_PLUGIN_PARENT",
        str(Path(__file__).resolve().parents[2]),
    )
)
if str(PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(PROJECT_PARENT))


def main():
    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if not prefix:
        raise RuntimeError("Run this test through python-qgis-ltr.bat")

    from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsSettings
    QgsApplication.setPrefixPath(prefix, True)
    application = QgsApplication([], False)
    application.initQgis()
    from qgis.PyQt.QtGui import QFont, QFontDatabase
    if os.name == "nt":
        QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf"))
    application.setFont(QFont("Arial", 10))

    from TerraWorkbench.i18n import language, set_language
    from TerraWorkbench.provider import TerraWorkbenchProvider
    from TerraWorkbench.settings_dialog import KEY_INSPECTOR
    from TerraWorkbench.workflow_dock import FilterStackDock, available_algorithms

    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    settings = QgsSettings()
    had_inspector_preference = settings.contains(KEY_INSPECTOR)
    previous_inspector_preference = settings.value(KEY_INSPECTOR)
    previous_language = language()
    dock = None
    try:
        set_language("en")
        settings.setValue(KEY_INSPECTOR, False)
        sample = (
            PROJECT_PARENT
            / "TerraWorkbench"
            / "sample_data"
            / "synthetic"
            / "synthetic_magnetic_anomaly.tif"
        )
        layer = QgsRasterLayer(str(sample), "Regional magnetics — TMI")
        if not layer.isValid():
            raise AssertionError(f"Sample raster is invalid: {sample}")
        QgsProject.instance().addMapLayer(layer)

        dock = FilterStackDock()
        dock.resize(410, 820)
        dock.show()
        application.processEvents()

        if dock.windowIcon().isNull() or dock.brand_icon.pixmap().isNull():
            raise AssertionError("Brand icon did not load in the Filter Stack")
        about_logo = dock.settings_dialog.about_logo.pixmap()
        if about_logo is None or about_logo.isNull():
            raise AssertionError("Full brand logo did not load in Settings / About")
        content_right = dock.widget().rect().right()
        if dock.add_button.geometry().right() > content_right:
            raise AssertionError("Add-filter button overflows the dock width")

        if dock.run_button.isEnabled() or dock.step_count.text() != "0 filters":
            raise AssertionError("Empty workflow state is inconsistent")
        catalogue = available_algorithms()
        if dock.algorithm_combo.count() < 3:
            raise AssertionError("Filter catalogue did not load")
        for algorithm in catalogue:
            details = getattr(algorithm, "implementation_details", ())
            if not details or any(len(item) != 2 for item in details):
                raise AssertionError(
                    f"Implementation libraries are not declared for {algorithm.id()}"
                )

        info_algorithm = next(
            algorithm
            for algorithm in catalogue
            if algorithm.id().endswith("butterworth_lowpass")
        )
        dock.filter_info.set_algorithm(info_algorithm)
        info_html = dock.filter_info.browser.toPlainText()
        if "Implementation and libraries" not in info_html or "NumPy FFT" not in info_html:
            raise AssertionError("Per-filter library attribution is not visible")
        set_language("es")
        dock.filter_info.set_algorithm(info_algorithm)
        spanish_info = dock.filter_info.browser.toPlainText()
        if "Implementación y librerías" not in spanish_info or "FFT de NumPy" not in spanish_info:
            raise AssertionError("Per-filter library attribution is not translated")
        set_language("en")
        dock.filter_info.set_algorithm(info_algorithm)
        for locale, heading, subtitle, count_label in (
            ("en", "Implementation and libraries", "Geophysical workflow builder", "0 filters"),
            ("es", "Implementación y librerías", "Constructor de flujos geofísicos", "0 filtros"),
            ("pt", "Implementação e bibliotecas", "Construtor de fluxos geofísicos", "0 filtros"),
        ):
            set_language(locale)
            dock.retranslate()
            dock.filter_info.set_algorithm(info_algorithm)
            assert heading in dock.filter_info.browser.toPlainText()
            assert dock.brand_subtitle.text() == subtitle
            assert dock.step_count.text() == count_label
            dock.refresh_algorithms()
            dock.domain_filter.setCurrentIndex(dock.domain_filter.findData("SPACE"))
            dock.algorithm_search.setText("circular")
            visible = [dock.algorithm_list.item(i) for i in range(dock.algorithm_list.count())
                       if not dock.algorithm_list.item(i).isHidden()]
            assert len(visible) == 1
            dock.domain_filter.setCurrentIndex(dock.domain_filter.findData("FREQUENCY"))
            assert all(dock.algorithm_list.item(i).isHidden() for i in range(dock.algorithm_list.count()))
            dock.algorithm_search.clear()
            assert any(not dock.algorithm_list.item(i).isHidden() for i in range(dock.algorithm_list.count()))
            dock.algorithm_picker.show()
            application.processEvents()
            assert dock.algorithm_picker.grab().save(str(Path(tempfile.gettempdir()) / f"tw_catalogue_{locale}.png"))
            dock.domain_filter.setCurrentIndex(0)
            dock.algorithm_picker.hide()
        set_language("en")
        dock.retranslate()
        dock.filter_info.set_algorithm(info_algorithm)
        info_screenshot = os.environ.get("TERRAWORKBENCH_INFO_SCREENSHOT", "")
        if info_screenshot:
            dock.filter_info.resize(540, 680)
            dock.filter_info.show()
            application.processEvents()
            destination = Path(info_screenshot)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not dock.filter_info.grab().save(str(destination), "PNG"):
                raise AssertionError(
                    f"Could not save filter-information screenshot: {destination}"
                )

        for index in range(3):
            dock.algorithm_combo.setCurrentIndex(index)
            dock.add_step()
        application.processEvents()
        if dock.step_list.count() != 3 or dock.step_count.text() != "3 filters":
            raise AssertionError("Workflow count did not update")
        if not dock.run_button.isEnabled() or dock.empty_stack_note.isVisible():
            raise AssertionError("Ready workflow state is inconsistent")

        dock.step_list.setCurrentRow(1)
        middle_id = dock.steps()[1].algorithm_id
        dock.move_step(-1)
        if dock.steps()[0].algorithm_id != middle_id:
            raise AssertionError("Move-up control did not preserve the selected step")

        screenshot = os.environ.get("TERRAWORKBENCH_GUI_SCREENSHOT", "")
        if screenshot:
            destination = Path(screenshot)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not dock.grab().save(str(destination), "PNG"):
                raise AssertionError(f"Could not save GUI screenshot: {destination}")
            print(f"OK: Filter Stack screenshot saved to {destination}", flush=True)
        print("OK: Filter Stack visual and interaction smoke test passed", flush=True)
    finally:
        set_language(previous_language)
        if had_inspector_preference:
            settings.setValue(KEY_INSPECTOR, previous_inspector_preference)
        else:
            settings.remove(KEY_INSPECTOR)
        if dock is not None:
            dock.disconnect_project()
            dock.close()
            dock.deleteLater()
            application.processEvents()
            del dock
        QgsProject.instance().clear()
        QgsApplication.processingRegistry().removeProvider(provider)
        application.exitQgis()
        del provider
        del application


if __name__ == "__main__":
    main()

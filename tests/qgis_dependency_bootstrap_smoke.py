"""The first-run dependency manager must load before defusedxml is installed."""

import importlib.abc
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

from qgis.core import QgsApplication, QgsProcessingException

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class MissingXMLDependency(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "defusedxml" or fullname.startswith("defusedxml."):
            raise ModuleNotFoundError("Simulated clean QGIS without defusedxml")
        return None


def check_language_and_layout(app):
    from qgis.PyQt.QtCore import QPoint, QRect, QSettings
    from qgis.PyQt.QtGui import QFont, QFontDatabase
    from qgis.PyQt.QtWidgets import QPushButton, QStyle, QStyleOptionButton

    from TerraWorkbench.embedded_qpip import dependency_directory
    from TerraWorkbench.ui import i18n
    from TerraWorkbench.ui.dependency_dialog import DependencyDialog
    from TerraWorkbench.ui.workflow_dock import FilterStackDock

    if os.name == "nt":
        for filename in ("arial.ttf", "arialbd.ttf"):
            font = Path(os.environ["WINDIR"]) / "Fonts" / filename
            assert QFontDatabase.addApplicationFont(str(font)) >= 0
    app.setFont(QFont("Arial", 10))
    settings = QSettings()
    legacy = "TerraWorkbench/language"
    settings.setValue(legacy, "es")
    settings.remove(i18n.LANGUAGE_KEY)
    with patch.object(QgsApplication, "locale", return_value="en_US") as qgis_locale, patch.object(
        i18n, "QLocale"
    ) as system_locale:
        system_locale.system.return_value.name.return_value = "es_PE"
        assert i18n.language_preference() == i18n.AUTOMATIC_LANGUAGE
        assert i18n.language() == "en"
        system_locale.system.assert_not_called()
        i18n.set_language("pt")
        assert i18n.language() == "pt"

        dock = FilterStackDock()
        preferences = dock.settings_dialog
        emitted = []
        dock.languageChanged.connect(lambda: emitted.append(i18n.language()))
        preferences.load()
        assert preferences.language_combo.currentData() == "pt"
        preferences.restore_defaults()
        assert preferences.language_combo.currentData() == i18n.AUTOMATIC_LANGUAGE
        preferences.save()
        assert emitted == ["en"] and i18n.language() == "en"
        qgis_locale.return_value = "es_ES"
        assert i18n.language() == "es"
        qgis_locale.return_value = "de_DE"
        assert i18n.language() == "en"
        qgis_locale.return_value = ""
        assert i18n.language() == "es"
        dock.disconnect_project()
        dock.close()
        dock.deleteLater()
        app.processEvents()

    capture_dir = os.environ.get("TW_DEPENDENCY_CAPTURES")
    if capture_dir:
        Path(capture_dir).mkdir(parents=True, exist_ok=True)
    for locale in ("en", "es", "pt"):
        i18n.set_language(locale)
        dialog = DependencyDialog()
        dialog.show()
        app.processEvents()
        assert dialog.width() == 760
        assert dialog.location.isReadOnly()
        assert dialog.location.toPlainText() == dialog.location.toolTip() == str(dependency_directory())
        button_rectangles = []
        for button in dialog.findChildren(QPushButton):
            if not button.isVisibleTo(dialog):
                continue
            option = QStyleOptionButton()
            option.initFrom(button)
            option.text = button.text()
            area = button.style().subElementRect(QStyle.SE_PushButtonContents, option, button)
            assert area.width() >= button.fontMetrics().horizontalAdvance(button.text()), (
                locale, button.text(), area.width()
            )
            rectangle = QRect(button.mapTo(dialog, QPoint()), button.size())
            assert dialog.rect().contains(rectangle), (locale, button.text(), rectangle)
            assert not any(rectangle.intersects(other) for other in button_rectangles), (
                locale, button.text(), rectangle
            )
            button_rectangles.append(rectangle)
        if capture_dir:
            dialog.resize(900, 640)
            app.processEvents()
            assert dialog.grab().save(str(Path(capture_dir) / f"dependencies-{locale}.png"))
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
    print("PASS: QGIS locale, legacy preference, hot retranslation and button widths in en/es/pt")


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    check_language_and_layout(app)
    blocker = MissingXMLDependency()
    saved = {key: sys.modules.pop(key) for key in list(sys.modules)
             if key == "defusedxml" or key.startswith("defusedxml.")}
    sys.meta_path.insert(0, blocker)
    try:
        from TerraWorkbench import classFactory
        from TerraWorkbench.qgis_plugin.data_import import read_sidecar_metadata
        from TerraWorkbench.embedded_qpip.manager import dependency_directory, RequirementStatus
        from TerraWorkbench.ui.dependency_dialog import _status_html
        from TerraWorkbench.ui.i18n import set_language, text
        from packaging.requirements import Requirement
        from qgis.PyQt.QtWidgets import QTextBrowser
        plugin = classFactory(None)
        assert plugin.provider is None
        with tempfile.TemporaryDirectory(prefix="tw_bootstrap_") as folder:
            source = Path(folder) / "survey.grd"
            assert read_sidecar_metadata(source) == {}
            Path(str(source) + ".xml").write_text("<metadata/>", encoding="utf-8")
            try:
                read_sidecar_metadata(source)
            except QgsProcessingException as error:
                assert "dependency manager" in str(error)
            else:
                raise AssertionError("XML metadata must require the safe parser")
            appdata = Path(folder) / "appdata"
            (appdata / "QGIS/QGIS3/profiles/default").mkdir(parents=True)
            custom = Path(folder) / "custom/profiles/clean"
            custom.mkdir(parents=True)
            with patch.dict(os.environ, {"APPDATA": str(appdata)}), patch.object(
                QgsApplication, "qgisSettingsDirPath", return_value=str(custom)
            ):
                version = f"{sys.version_info.major}.{sys.version_info.minor}"
                assert dependency_directory() == custom / f"python/dependencies/TerraWorkbench/{version}"
            browser = QTextBrowser()
            status = RequirementStatus(Requirement("harmonica>=0.7,<0.8"), None, False)
            for locale, label in (("en", "Missing"), ("es", "Falta"), ("pt", "Ausente")):
                set_language(locale)
                browser.setHtml("<table>" + _status_html([status]) + "</table>")
                assert "<0.8" in browser.toPlainText(), browser.toPlainText()
                assert label in browser.toPlainText(), browser.toPlainText()
            browser.close()
            set_language("pt")
            for suffix in ("added to the map", "written to disk"):
                message = text(f"Completed 2 filter(s). The final result was {suffix}.", "")
                assert "The final result" not in message, message
                assert "O resultado final" in message, message
        print("PASS: plugin factory loads without defusedxml; XML requires safe dependency setup")
        print("PASS: custom-profile dependency isolation and translated complete requirement ranges")
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(saved)
        app.exitQgis()


if __name__ == "__main__":
    main()

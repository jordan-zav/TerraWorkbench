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


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
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

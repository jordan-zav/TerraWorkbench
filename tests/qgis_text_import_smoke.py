"""Exercise the actual text wizard and workspace import action in QGIS."""

import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.PyQt import sip

from TerraWorkbench.i18n import LANGUAGE_KEY, set_language
from TerraWorkbench.survey_workspace_dialog import SurveyWorkspaceDialog, KEY_WORKSPACE
from TerraWorkbench.text_import_dialog import TextImportDialog


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    if os.name == "nt":
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Arial", 10))
    settings = QSettings()
    previous = {key: settings.value(key, None) for key in (LANGUAGE_KEY, KEY_WORKSPACE)}
    settings.remove(KEY_WORKSPACE)
    get_files, execute = QFileDialog.getOpenFileNames, TextImportDialog.exec
    errors = []
    manager = None
    try:
        with tempfile.TemporaryDirectory(prefix="tw_text_import_") as folder:
            first = Path(folder) / "instrument.csv"
            first.write_bytes("Exportación\n# notes\nLine;X [m];Y [m];Mag [nT]\n001;500000,5;4000000,5;3,5\n002;500001,5;4000001,5;4,5\n".encode("cp1252"))
            second = Path(folder) / "points.xyz"
            second.write_text("# no header\n1 2 3\n4 5 6\n", encoding="utf-8")
            for lang in ("en", "es", "pt"):
                set_language(lang)
                wizard = TextImportDialog(first)
                wizard.show()
                assert wizard.header.value() == 3 and wizard.data.value() == 4
                assert wizard.decimal.currentText() == ","
                assert wizard.channels.rowCount() == 4
                wizard.accept()
                assert wizard.options is None  # first click opens preview, not import
                assert wizard.sample.rowCount() == 2
                assert wizard.sample.item(0, 0).text() == "001"
                wizard.channels.item(3, 0).setText("magnetic_field")
                wizard.accept()
                assert wizard.options is None  # changed schema must be previewed again
                wizard.accept()
                assert wizard.options.columns[3].name == "magnetic_field"
                wizard.show()
                app.processEvents()
                image = Path(tempfile.gettempdir()) / f"tw_text_import_{lang}.png"
                assert wizard.grab().save(str(image))
                wizard.close()
                sip.delete(wizard)
                print(f"PASS {lang}: settings, typed preview, review gate, editable channels; {image}", flush=True)

            manager = SurveyWorkspaceDialog()
            manager.fail = errors.append
            manager.set_project(Path(folder) / "project", create=True)
            seen = []
            def accept_wizard(self):
                seen.append(self.path.name)
                assert self.refresh_preview(), self.status.text()
                self.accept()
                return self.result()
            TextImportDialog.exec = accept_wizard
            QFileDialog.getOpenFileNames = lambda *args, **kwargs: ([str(first), str(second)], "")
            manager.import_files()
            deadline = time.monotonic() + 30
            while manager.worker is not None and time.monotonic() < deadline:
                app.processEvents()
                QTest.qWait(10)
            assert manager.worker is None and not errors, errors
            assert seen == [first.name, second.name]
            assert len(manager.store.databases()) == 2
            imported = next(row for row in manager.store.databases() if row["name"] == "instrument")
            channels = manager.store.channels(imported["id"])
            assert next(c for c in channels if c["name"] == "Mag [nT]")["data_type"] == "double"
            assert imported["rows"] == 2
            manager.close()
            sip.delete(manager)
            manager = None
            print("PASS: multi-file workspace import uses reviewed per-file options", flush=True)
    finally:
        TextImportDialog.exec, QFileDialog.getOpenFileNames = execute, get_files
        if manager is not None:
            manager.dispose()
        for key, value in previous.items():
            if value is None:
                settings.remove(key)
            else:
                settings.setValue(key, value)


if __name__ == "__main__":
    main()

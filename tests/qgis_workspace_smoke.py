"""Headless workspace UI, worker and QGIS point-bridge integration test."""

import gc
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt import sip

from TerraWorkbench.i18n import LANGUAGE_KEY, set_language
from TerraWorkbench.survey_workspace_dialog import SurveyWorkspaceDialog, KEY_WORKSPACE


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
    errors = []
    dialog = None

    def wait():
        deadline = time.monotonic() + 30
        while dialog.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        assert dialog.worker is None, "Worker did not finish"
        assert not errors, errors

    try:
        with tempfile.TemporaryDirectory(prefix="tw_workspace_") as folder:
            source = Path(folder) / "survey.csv"
            source.write_text("line,x,y,mag,base\n001,500000,4000000,100,5\n002,500001,4000001,110,6\n001,500002,4000002,120,7\n", encoding="utf-8")
            titles = []
            for lang in ("en", "es", "pt"):
                set_language(lang)
                dialog = SurveyWorkspaceDialog()
                titles.append(dialog.windowTitle())
                dialog.fail = errors.append
                dialog.set_project(Path(folder) / "project", create=True)
                dialog.show()
                if not dialog.store.databases():
                    dialog.start(lambda cancel, progress: dialog.store.import_file(source, canceled=cancel, progress=progress))
                    wait()
                    dialog.store.import_file(source, "second")
                    dialog.refresh()
                assert dialog.databases_list.count() == 2
                for i in range(2):
                    dialog.databases_list.item(i).setSelected(True)
                assert dialog.channels_list.count() == 5
                # Select a single database for preview and bridge.
                dialog.databases_list.item(1).setSelected(False)
                for i in range(dialog.channels_list.count()):
                    item = dialog.channels_list.item(i)
                    item.setSelected(item.data(256) in {"mag", "base"})
                database = dialog.selected_databases()[0]
                dialog.start(lambda cancel, progress: dialog.store.derive(database, "corrected", 'c("mag")-c("base")', "nT", cancel, progress))
                wait()
                dialog.preview()
                wait()
                assert dialog.table.rowCount() == 3
                dialog.filter_channel.setCurrentIndex(dialog.filter_channel.findData("line"))
                dialog.filter_values.setText("001")
                dialog.preview()
                wait()
                assert dialog.table.rowCount() == 2
                get_item, get_text = QInputDialog.getItem, QInputDialog.getText
                axes = iter(["x", "y"])
                try:
                    QInputDialog.getItem = lambda *args, **kwargs: (next(axes), True)
                    QInputDialog.getText = lambda *args, **kwargs: ("EPSG:32617", True)
                    dialog.to_qgis()
                    wait()
                finally:
                    QInputDialog.getItem, QInputDialog.getText = get_item, get_text
                layers = list(QgsProject.instance().mapLayers().values())
                assert len(layers) == 1 and layers[0].featureCount() == 2
                assert layers[0].crs().authid() == "EPSG:32617"
                assert layers[0].fields().names() == ["x", "y", "base", "mag"]
                QgsProject.instance().clear()
                layers.clear()
                screenshot = Path(tempfile.gettempdir()) / f"tw_workspace_{lang}.png"
                app.processEvents()
                assert dialog.grab().save(str(screenshot))
                print(f"PASS {lang}: workspace, two databases, worker, preview, filtered QGIS points; {screenshot}", flush=True)
                dialog.close()
                sip.delete(dialog)
                dialog = None
            assert len(set(titles)) == 3
            gc.collect()
    finally:
        if dialog is not None:
            dialog.dispose()
        QgsProject.instance().clear()
        for key, value in previous.items():
            if value is None:
                settings.remove(key)
            else:
                settings.setValue(key, value)


if __name__ == "__main__":
    main()

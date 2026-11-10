"""Offscreen Qt integration: pagination, profile breaks and three languages."""

import gc
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qgis.core import QgsApplication
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtTest import QTest

from TerraWorkbench.ui.i18n import LANGUAGE_KEY, set_language
from TerraWorkbench.ui.survey_workspace_dialog import KEY_WORKSPACE, SurveyWorkspaceDialog


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    if os.name == "nt":
        font = Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf"
        QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Arial", 10))
    settings = QSettings()
    previous = {key: settings.value(key, None) for key in (LANGUAGE_KEY, KEY_WORKSPACE)}
    settings.remove(KEY_WORKSPACE)
    dialog = None
    errors = []

    def wait():
        deadline = time.monotonic() + 40
        while dialog.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        assert dialog.worker is None, "Worker did not finish"
        assert not errors, errors

    def choose(combo, value):
        index = combo.findData(value)
        assert index >= 0, value
        combo.setCurrentIndex(index)

    try:
        with tempfile.TemporaryDirectory(prefix="tw_explorer_") as folder:
            source = Path(folder) / "synthetic.csv"
            source.write_text(
                "line,sensor,time,signal,x,y\n"
                + "".join(
                    f"{'L1' if i < 450 else 'L2'},S1,{i % 450},{100 + i * 0.02},{500000 + i % 450},{4000000 + (i // 450) * 100}\n"
                    for i in range(650)
                ),
                encoding="utf-8",
            )
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            for lang in ("en", "es", "pt"):
                set_language(lang)
                dialog = SurveyWorkspaceDialog()
                dialog.fail = errors.append
                dialog.set_project(Path(folder) / "project", create=True)
                if not dialog.store.databases():
                    dialog.store.import_file(source)
                    dialog.refresh()
                database = dialog.selected_databases()[0]
                dialog.store.configure_geometry(database, "x", "y", "EPSG:32618")
                if "signal_B" not in {
                    row["name"] for row in dialog.store.channels(database)
                }:
                    dialog.store.rename_channel(database, "signal", "signal", "nT")
                    dialog.store.derive(database, "signal_B", 'c("signal")+2', "nT")
                    dialog.refresh()
                history = dialog.store.history(database)
                for i in range(dialog.channels_list.count()):
                    item = dialog.channels_list.item(i)
                    item.setSelected(item.data(256) in {"signal", "time"})
                dialog.show()
                dialog.preview()
                wait()
                assert dialog.table.rowCount() == 200 and dialog.page_next.isEnabled()
                dialog.page_next.click()
                wait()
                assert dialog._page_offset == 200
                assert dialog.table.verticalHeaderItem(0).text() == "201"
                choose(dialog.profile_group, "line")
                choose(dialog.profile_sensor, "sensor")
                dialog.load_group_values()
                wait()
                assert dialog.group_choices.count() == 3
                assert dialog.sensor_choices.count() == 2
                dialog.group_choices.setCurrentIndex(
                    dialog.group_choices.findData("L2")
                )
                assert dialog.group_values.text() == "L2"
                dialog.group_values.setText("L2")
                dialog.sensor_values.setText("S1")
                dialog.page_next.click()
                wait()
                assert dialog._page_offset == 0 and dialog.table.rowCount() == 200
                assert not dialog.page_next.isEnabled()
                choose(dialog.profile_channel, "signal")
                choose(dialog.profile_axis, "time")
                dialog.group_values.clear()
                dialog.load_profile()
                wait()
                result = dialog.profile_plot.profile
                assert result["rows"] == 650 and len(result["segments"]) == 2
                assert result["valid_rows"] == 650 and result["minimum"] == 100
                assert dialog.views.currentIndex() == 1
                initial_bounds = dialog.profile_plot.bounds()
                dialog.profile_plot.zoom(0.5)
                zoomed = dialog.profile_plot.bounds()
                assert zoomed[1] - zoomed[0] < initial_bounds[1] - initial_bounds[0]
                dialog.profile_plot.fit()
                assert dialog.profile_plot.bounds() == initial_bounds
                assert dialog.tasks.records[-1]["state"] == "completed"
                dialog.profile_distance.setChecked(True)
                dialog.load_profile()
                wait()
                assert all(
                    segment["x"][0] == 0
                    for segment in dialog.profile_plot.profile["segments"]
                )
                assert "(m)" in dialog.profile_plot.x_label
                dialog.profile_distance.setChecked(False)
                choose(dialog.profile_compare, "signal_B")
                choose(dialog.profile_compare_mode, "difference")
                dialog.load_profile()
                wait()
                assert abs(dialog.profile_plot.profile["mean"] - 2) < 1e-12
                assert "signal_B − signal" in dialog.profile_plot.y_label
                choose(dialog.profile_compare_mode, "overlay")
                dialog.load_profile()
                wait()
                assert len(dialog.profile_plot.profile["segments"]) == 4
                dialog.resize(1000, 720)
                app.processEvents()
                shot = Path(tempfile.gettempdir()) / f"tw_explorer_{lang}.png"
                assert dialog.grab().save(str(shot))
                assert dialog.profile_plot.width() >= 320
                assert dialog.profile_plot.height() >= 240
                assert dialog.store.history(database) == history
                assert hashlib.sha256(source.read_bytes()).hexdigest() == original
                print(
                    f"PASS {lang}: pagination, selection reset, transect/sensor profiles, immutable source/history; {shot}",
                    flush=True,
                )
                dialog.close()
                sip.delete(dialog)
                dialog = None
            gc.collect()
    finally:
        if dialog is not None:
            dialog.dispose()
        for key, value in previous.items():
            if value is None:
                settings.remove(key)
            else:
                settings.setValue(key, value)


if __name__ == "__main__":
    main()

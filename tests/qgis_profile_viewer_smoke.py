"""Offscreen QGIS smoke for exact editing, navigation, map tracking and painting."""

import json
import os
from pathlib import Path
import time
from unittest.mock import patch

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from qgis.PyQt.QtCore import QEvent, QPoint, Qt, QThreadPool
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QInputDialog, QMainWindow
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsPointXY,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent

from TerraWorkbench.qgis_plugin.plugin import TerraWorkbenchPlugin
from TerraWorkbench.qgis_plugin.survey_map_layers import (
    SURVEY_PROPERTY,
    WORKSPACE_PROPERTY,
)
from TerraWorkbench.terraworkbench_core.survey_store import SurveyStore
from TerraWorkbench.ui.i18n import set_language


class Interface:
    def __init__(self):
        self.window = QMainWindow()
        self.canvas = QgsMapCanvas(self.window)
        self.window.setCentralWidget(self.canvas)

    def mainWindow(self):
        return self.window

    def messageBar(self):
        from qgis.gui import QgsMessageBar

        return QgsMessageBar(self.window)

    def mapCanvas(self):
        return self.canvas

    def addDockWidget(self, area, dock):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)


def wait(app, condition):
    deadline = time.monotonic() + 25
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert condition()


def synthetic(evidence):
    n = 100000
    rows = np.arange(n + 20)
    values = np.sin(rows / 200) + np.cos(rows / 55) / 6
    values[n // 2] += 8
    values[n // 2 + 350] += 4
    path = evidence / "synthetic.parquet"
    pq.write_table(
        pa.table(
            {
                "line": np.where(rows < n, "L100", "L200").tolist(),
                "fiducial": rows + 1,
                "x": 500000 + rows,
                "y": np.full(rows.size, 5500000),
                "mag": 50000 + 50 * values,
                "alt": 100 + 10 * np.cos(rows / 1500),
            }
        ),
        path,
    )
    store = SurveyStore(evidence / "survey", create=True)
    database = store.import_file(path)
    store.configure_geometry(database, "x", "y", "EPSG:32610", line="line")
    return store, database


def main():
    app = QgsApplication([], True)
    app.initQgis()
    if os.name == "nt":
        QFontDatabase.addApplicationFont(
            str(Path(os.environ["WINDIR"]) / "Fonts/arial.ttf")
        )
    app.setFont(QFont("Arial", 10))
    evidence = Path(os.environ.get("TW_PROFILE_EVIDENCE", os.environ["TEMP"]))
    iface = Interface()
    iface.window.resize(1300, 720)
    crs = QgsCoordinateReferenceSystem("EPSG:32610")
    iface.canvas.setDestinationCrs(crs)
    iface.window.show()
    set_language("es")
    plugin = TerraWorkbenchPlugin(iface)
    store, database = synthetic(evidence)
    layer = QgsVectorLayer(
        "LineString?crs=EPSG:32610&field=line_id:string", "Líneas", "memory"
    )
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle

    feature = QgsFeature(layer.fields())
    feature.setAttributes(["L100"])
    feature.setGeometry(
        QgsGeometry.fromPolylineXY(
            [
                QgsPointXY(500000, 5500000),
                QgsPointXY(599999, 5500000),
            ]
        )
    )
    assert layer.dataProvider().addFeatures([feature])[0]
    layer.setCustomProperty(SURVEY_PROPERTY, database)
    layer.setCustomProperty(WORKSPACE_PROPERTY, str(store.root))
    project = QgsProject.instance()
    project.addMapLayer(layer)
    iface.canvas.setLayers([layer])
    iface.canvas.setExtent(QgsRectangle(500000, 5490000, 600000, 5510000))
    iface.canvas.refresh()
    app.processEvents()
    plugin.pick_profile_on_map()
    xy = iface.canvas.getCoordinateTransform().transform(525000, 5500000)
    click = QPoint(round(xy.x()), round(xy.y()))
    start = time.perf_counter()
    plugin.profile_tool.canvasReleaseEvent(
        event := QgsMapMouseEvent(
            iface.canvas,
            QEvent.MouseButtonRelease,
            click,
            Qt.LeftButton,
        )
    )
    assert plugin.profile_dock is not None, (event.mapPoint(), layer.extent(), click)
    wait(app, lambda: bool(plugin.profile_dock._data))
    dock = plugin.profile_dock
    assert event.mapPoint() is not None and dock.plot.cursor is not None
    assert abs(dock.plot.cursor - 25000) < 150
    dock.open_survey(store, database, line="L100", channels=["mag", "alt"])
    wait(app, lambda: len(dock._data) == 2)
    load_ms = (time.perf_counter() - start) * 1000
    dock._select_channel("mag")
    dock.axis.setCurrentIndex(dock.axis.findData("distance"))
    assert dock.plot.axis.size == 100000
    assert dock.plot.axis[-1] == 99999
    paint = []
    overlay = []
    for _ in range(12):
        dock.plot._invalidate()
        start = time.perf_counter()
        assert not dock.plot.grab().isNull()
        paint.append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        dock.plot.cursor = 30000
        dock.plot.grab()
        overlay.append((time.perf_counter() - start) * 1000)
    dock.mark_map(25000)
    assert abs(dock._marker.center().x() - 525000) < 0.01
    layer.selectByIds([next(layer.getFeatures()).id()])
    plugin._profile_map_selection(layer)
    wait(app, lambda: dock.plot.cursor is not None and bool(dock._data))
    assert abs(dock.plot.cursor - 50000) < 2
    dock._select_channel("mag")
    dock.plot._select(49999, 50001)
    dock.edit("dummy")
    assert np.isnan(dock._data["mag"].values[50000])
    dock.edit("undo")
    assert np.isfinite(dock._data["mag"].values[50000])
    dock.edit("redo")
    dock.edit("linear")
    assert np.isfinite(dock._data["mag"].values[50000])
    QTest.keyClick(dock.plot, Qt.Key_Right)
    wait(app, lambda: dock.line.currentText() == "L200" and bool(dock._data))
    QTest.keyClick(dock.plot, Qt.Key_Left)
    wait(app, lambda: dock.line.currentText() == "L100" and bool(dock._data))
    dock._select_channel("mag")
    dock.plot._select(49500, 50500)
    dock.toggle_fourth()
    with patch.object(QInputDialog, "getDouble", return_value=(35.0, True)):
        dock.preview_spikes(False)
    assert dock._preview is not None and dock.apply.isVisible()
    assert 50350 in dock._preview[0]
    app.processEvents()
    assert dock.grab().save(str(evidence / "perfiles-sintetico.png"))
    dock.apply_preview()
    assert np.isnan(dock._data["mag"].values[50350])
    with patch.object(QInputDialog, "getText", return_value=("mag_edited", True)):
        dock.save_channel()
    wait(app, lambda: not dock._saving)
    assert "mag_edited" in {row["name"] for row in store.channels(database)}
    result = {
        "samples": 100000,
        "channels": 2,
        "map_click_and_reload_ms": load_ms,
        "paint_median_ms": float(np.median(paint)),
        "paint_max_ms": max(paint),
        "cached_cursor_median_ms": float(np.median(overlay)),
    }
    (evidence / "rendimiento.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    archive = os.environ.get("TW_PROFILE_ARCHIVE")
    if archive:
        converted = SurveyStore(archive)
        converted_db = converted.databases()[0]["id"]
        dock.open_survey(converted, converted_db)
        wait(app, lambda: bool(dock._data))
        assert dock.grab().save(str(evidence / "perfiles-mount-polley.png"))

    plugin.unload()
    QThreadPool.globalInstance().waitForDone()
    project.clear()
    iface.window.close()
    app.processEvents()
    print("Profile viewer smoke passed")


if __name__ == "__main__":
    main()

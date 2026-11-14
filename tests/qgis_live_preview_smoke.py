"""Exercise debounce, cancellation, native apply and temporary-layer teardown."""

import json
import os
from pathlib import Path
import sys
import time
import traceback

import numpy as np
from osgeo import gdal, osr
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer
from qgis.gui import QgsMapCanvas, QgsLayerTreeMapCanvasBridge
from qgis.PyQt.QtCore import Qt, QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QMainWindow, QListWidgetItem, QMessageBox
from qgis.PyQt.QtTest import QTest, QSignalSpy


def main():
    sys.excepthook = lambda kind, value, tb: traceback.print_exception(kind, value, tb)
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python/plugins"))
    from processing.core.Processing import Processing
    from TerraWorkbench.qgis_plugin.provider import TerraWorkbenchProvider
    from TerraWorkbench.ui.workflow_dock import (
        FilterStackDock,
        PipelineStep,
        algorithm_defaults,
    )
    from TerraWorkbench.ui.i18n import set_language

    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    set_language("es")
    root = Path(os.environ["TEMP"])
    source = root / "synthetic.tif"
    yy, xx = np.mgrid[:512, :512]
    values = 100 * np.exp(-((xx - 250) ** 2 + (yy - 250) ** 2) / 2000) + 10 * np.sin(
        xx / 20
    )
    ds = gdal.GetDriverByName("GTiff").Create(
        str(source), 512, 512, 1, gdal.GDT_Float64
    )
    ds.SetGeoTransform((500000, 10, 0, 9000000, 0, -10))
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(32718)
    ds.SetProjection(crs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(values)
    ds = None
    layer = QgsRasterLayer(str(source), "Original")
    project = QgsProject.instance()
    project.addMapLayer(layer)
    window = QMainWindow()
    canvas = QgsMapCanvas()
    canvas.resize(600, 600)
    window.setCentralWidget(canvas)
    canvas.setDestinationCrs(layer.crs())
    canvas.setLayers([layer])
    canvas.setExtent(layer.extent())
    bridge = QgsLayerTreeMapCanvasBridge(project.layerTreeRoot(), canvas)
    assert bridge

    class Iface(QObject):
        currentLayerChanged = pyqtSignal(object)

        def mainWindow(self):
            return window

        def mapCanvas(self):
            return canvas

        def activeLayer(self):
            return layer

        def setActiveLayer(self, selected):
            self.selected = selected

        def layerTreeView(self):
            from types import SimpleNamespace

            return SimpleNamespace(refreshLayerSymbology=lambda *args: None)

        def addCustomActionForLayerType(self, *args):
            pass

        def addCustomActionForLayer(self, *args):
            pass

        def removeCustomActionForLayerType(self, *args):
            pass

    dock = FilterStackDock(window, iface=Iface())
    window.addDockWidget(Qt.RightDockWidgetArea, dock)
    window.resize(1100, 800)
    window.show()
    dock.layer_combo.setCurrentIndex(dock.layer_combo.findData(layer.id()))
    algorithm = dock._algorithm("terraworkbench:upward_continuation")
    assert algorithm
    params = algorithm_defaults(algorithm)
    params["HEIGHT"] = 50
    item = QListWidgetItem()
    dock._set_item_step(item, PipelineStep(algorithm.id(), params))
    dock.step_list.addItem(item)
    dock.step_list.setCurrentRow(0)
    live = dock.live_preview
    published = QSignalSpy(live.updated)

    def wait_until(predicate):
        deadline = time.monotonic() + 30
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        assert predicate(), live.status.text()

    live.enabled.setChecked(True)
    print("preview enabled", flush=True)
    QTest.qWait(100)
    assert live.worker is None and live.layer is None
    wait_until(lambda: live.worker is not None)
    cancelled_token = live.latest.cancelled
    dock._parameter_editors["HEIGHT"][0].setText("75")
    assert cancelled_token.is_set()
    wait_until(lambda: live.layer is not None)
    assert len(published) == 1 and published[0][0] == live.latest.generation
    print("first preview published", flush=True)
    first_id = live.layer.id()
    first = gdal.Open(live.path).ReadAsArray().copy()
    first_elapsed = live.elapsed
    editor = dock._parameter_editors["HEIGHT"][0]
    for height in ("100", "200", "300"):
        editor.setText(height)
        QTest.qWait(30)
    wait_until(lambda: live.worker is None and not live.timer.isActive())
    print("second preview published", flush=True)
    second = gdal.Open(live.path).ReadAsArray()
    assert live.layer.id() == first_id
    assert not np.allclose(first, second)
    assert live.last_cache_hit
    assert len(published) == 2, "Rapid edits should produce one debounced publication"
    assert project.write(str(root / "preview-project.qgs"))
    assert first_id not in (root / "preview-project.qgs").read_text(encoding="utf-8")
    wait_until(
        lambda: (
            live.layer is not None and live.worker is None and not live.timer.isActive()
        )
    )
    first_id = live.layer.id()
    assert (
        sum(
            bool(candidate.customProperty("TerraWorkbench/livePreview"))
            for candidate in project.mapLayers().values()
        )
        == 1
    )
    live.before.setChecked(True)
    assert not project.layerTreeRoot().findLayer(first_id).itemVisibilityChecked()
    live.before.setChecked(False)
    # Native Apply goes through the real dock action and provenance publisher.
    dock.output_directory.setText(str(root / "native"))
    before_ids = set(project.mapLayers())
    QMessageBox.information = lambda *args: QMessageBox.Ok
    QMessageBox.critical = lambda *args: (_ for _ in ()).throw(
        AssertionError(str(args))
    )
    dock.run_stack()
    print("native apply returned", flush=True)
    final = [
        candidate
        for key, candidate in project.mapLayers().items()
        if key not in before_ids
    ]
    assert final and final[-1].width() == 512
    assert any((root / "native").rglob("*.json"))
    full = gdal.Open(final[-1].source()).ReadAsArray()
    from scipy.ndimage import map_coordinates

    preview_transform = gdal.Open(live.path).GetGeoTransform()
    rows, columns = second.shape
    yy, xx = np.mgrid[
        rows * 3 // 8 : rows * 5 // 8, columns * 3 // 8 : columns * 5 // 8
    ]
    gt = layer.dataProvider().extent()
    source_x = (
        preview_transform[0] + (xx + 0.5) * preview_transform[1] - gt.xMinimum()
    ) / 10 - 0.5
    source_y = (
        gt.yMaximum() - preview_transform[3] - (yy + 0.5) * preview_transform[5]
    ) / 10 - 0.5
    expected = map_coordinates(full, [source_y, source_x], order=1)
    difference = float(np.max(np.abs(expected - second[yy, xx])))
    assert difference < np.ptp(full) * 0.03, difference
    # Zoom and pan must create a new generation and recompute without edits.
    generation = live.latest.generation
    extent = layer.extent()
    extent.scale(0.5)
    canvas.setExtent(extent)
    wait_until(
        lambda: (
            live.latest.generation > generation
            and live.worker is None
            and not live.timer.isActive()
        )
    )
    # Two-filter stacks stop at the selected filter.
    assert not live.last_cache_hit
    extra = dock._algorithm("terraworkbench:fft_derivative_easting")
    item2 = QListWidgetItem()
    dock._set_item_step(item2, PipelineStep(extra.id(), algorithm_defaults(extra)))
    dock.step_list.addItem(item2)
    dock.step_list.setCurrentRow(1)
    wait_until(lambda: live.worker is None and not live.timer.isActive())
    two_steps = gdal.Open(live.path).ReadAsArray().copy()
    dock.step_list.setCurrentRow(0)
    wait_until(lambda: live.worker is None and not live.timer.isActive())
    assert not np.allclose(two_steps, gdal.Open(live.path).ReadAsArray())
    rtp = dock._algorithm("terraworkbench:reduction_to_pole")
    rtp_parameters = algorithm_defaults(rtp)
    rtp_parameters.update(INCLINATION=60, DECLINATION=0)
    dock._set_item_step(item, PipelineStep(rtp.id(), rtp_parameters))
    dock.show_step_parameters(0, reveal=False)
    live.schedule()
    wait_until(lambda: live.worker is None and not live.timer.isActive())
    rtp_before = gdal.Open(live.path).ReadAsArray().copy()
    cached_input = next(
        value for key, value in live.cache.items() if key[0] != "fft"
    )
    np.testing.assert_allclose(
        np.nanmean(rtp_before), np.nanmean(cached_input.values), atol=1e-4, rtol=0,
        err_msg="RTP preview must preserve the supported input mean",
    )
    dock._parameter_editors["PRESERVE_MEAN"][0].setText("0")
    wait_until(lambda: live.worker is None and not live.timer.isActive())
    assert abs(np.nanmean(gdal.Open(live.path).ReadAsArray())) < 1e-4
    dock._parameter_editors["PRESERVE_MEAN"][0].setText("1")
    wait_until(lambda: live.worker is None and not live.timer.isActive())
    # Exercise final RTP publication after both optimized and fallback stacks.
    from dataclasses import replace
    from TerraWorkbench.ui.live_preview import PreviewWorker

    for preceding_id in ("upward_continuation", "derivative_easting"):
        preceding = dock._algorithm("terraworkbench:" + preceding_id)
        prior_step = PipelineStep(preceding.id(), algorithm_defaults(preceding))
        worker = PreviewWorker(0, live.latest.cancelled, None, live)
        worker.window_key = ("mean-regression", preceding_id)

        def calculate(selected_steps, selected_algorithms):
            grid = replace(
                cached_input, values=cached_input.values.copy(),
                metadata=dict(cached_input.metadata),
            )
            return worker.harmonica_stack(grid, selected_steps, selected_algorithms).values

        previous = calculate([prior_step], [preceding])
        rtp_step = PipelineStep(rtp.id(), dict(rtp_parameters, PRESERVE_MEAN=1))
        retained = calculate([prior_step, rtp_step], [preceding, rtp])
        np.testing.assert_allclose(
            np.nanmean(retained), np.nanmean(previous), atol=1e-8, rtol=0
        )
        rtp_step = PipelineStep(rtp.id(), dict(rtp_parameters, PRESERVE_MEAN=0))
        removed = calculate([prior_step, rtp_step], [preceding, rtp])
        assert abs(np.nanmean(removed)) < 1e-8
        np.testing.assert_allclose(
            retained - np.nanmean(retained), removed, atol=1e-8, rtol=0
        )
        worker.deleteLater()
    dock._parameter_editors["INCLINATION"][0].setText("50")
    dock._parameter_editors["DECLINATION"][0].setText("15")
    wait_until(lambda: live.worker is None and not live.timer.isActive())
    rtp_after = gdal.Open(live.path).ReadAsArray()
    assert np.isfinite(rtp_after).all() and not np.allclose(rtp_before, rtp_after)
    if os.environ.get("TW_GEORAMP_PARENT"):
        sys.path.insert(0, os.environ["TW_GEORAMP_PARENT"])
        from georamp.plugin import GeoRampPlugin
        from TerraWorkbench.qgis_plugin.georamp import open_georamp

        colours = GeoRampPlugin(dock.iface)
        assert open_georamp(
            dock.iface, live.layer, "mag_dz", plugins={"georamp": colours}
        )
        assert colours.dialog.layer_combo.currentData() == live.layer.id()
        assert colours.dialog.palette_combo.currentData() == "blue_white_red"
        assert colours.dialog.manual_check.isChecked()
        assert (
            colours.dialog.minimum_spin.value() == -colours.dialog.maximum_spin.value()
        )
        colours.dialog.close()
        wait_until(lambda: colours.dialog.active_task is None)
        colours.dialog.viewer_canvas.waitWhileRendering()
        colours.dialog.follow_manager.shutdown()
        from qgis.PyQt import sip

        sip.delete(colours.dialog.follow_manager)
        sip.delete(colours.dialog)
        colours.dialog = None
    live.enabled.setChecked(False)
    assert live.layer is None and first_id not in project.mapLayers()
    assert not gdal.VSIStatL(live.path)
    # Cancel while a new request is in flight and close before publication.
    live.enabled.setChecked(True)
    QTest.qWait(310)
    dock.close()
    wait_until(lambda: live.worker is None)
    assert live.layer is None
    (root / "live-preview-result.json").write_text(
        json.dumps(
            dict(
                first_seconds=first_elapsed,
                second_seconds=live.elapsed,
                centre_max_abs_difference=difference,
                debounce_and_cancellation=True,
                update=True,
                native_apply=True,
                teardown=True,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    dock.disconnect_project()
    window.close()
    project.clear()
    QgsApplication.processingRegistry().removeProvider(provider)
    app.processEvents()
    app.exitQgis()
    print("LIVE PREVIEW SMOKE PASS", flush=True)


if __name__ == "__main__":
    main()

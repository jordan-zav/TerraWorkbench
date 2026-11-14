"""Measure actual QGIS workers and capture live filtering on public Britain data.

Run with an isolated QGIS runner. TW_PREVIEW_OUTPUT selects a new evidence
directory. TW_PREVIEW_BRITAIN points to the pinned public CSV.xz; no desktop
input, private data or user's QGIS profile is used. GIF encoding is separate.
"""

import hashlib
import json
import os
from pathlib import Path
import sys
import time
from threading import Event

import numpy as np
from osgeo import gdal, osr
from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsRasterLayer,
    QgsStyle,
    QgsColorRampShader,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
)
from qgis.gui import QgsMapCanvas, QgsLayerTreeMapCanvasBridge
from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QMainWindow, QListWidgetItem
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtGui import QFont, QFontDatabase


def main():
    """Write measured worker latencies and actual widget renders to caller storage."""
    output = Path(os.environ["TW_PREVIEW_OUTPUT"])
    output.mkdir(parents=True, exist_ok=False)
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    QFontDatabase.addApplicationFont(
        str(Path(os.environ["WINDIR"]) / "Fonts/arial.ttf")
    )
    app.setFont(QFont("Arial", 10))
    sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python/plugins"))
    from processing.core.Processing import Processing
    from TerraWorkbench.qgis_plugin.provider import TerraWorkbenchProvider
    from TerraWorkbench.ui.workflow_dock import (
        FilterStackDock,
        PipelineStep,
        algorithm_defaults,
    )
    from TerraWorkbench.ui.live_preview import PreviewWorker
    from TerraWorkbench.ui.i18n import set_language
    from TerraWorkbench.qgis_plugin.raster_io import RasterGrid, write_geotiff

    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    set_language("es")
    reference = osr.SpatialReference()
    reference.ImportFromEPSG(32630)
    wkt = reference.ExportToWkt()
    algorithm = QgsApplication.processingRegistry().algorithmById(
        "terraworkbench:upward_continuation"
    )
    params = algorithm_defaults(algorithm)
    params["HEIGHT"] = 100
    step = PipelineStep(algorithm.id(), params)
    measurements = []
    for size in (512, 2048, 4096):
        filename = str(output / f"synthetic-{size}.tif")
        dataset = gdal.GetDriverByName("GTiff").Create(
            filename,
            size,
            size,
            1,
            gdal.GDT_Float32,
            options=["TILED=YES", "COMPRESS=LZW"],
        )
        dataset.SetProjection(wkt)
        dataset.SetGeoTransform((500000, 5120 / size, 0, 6500000, 0, -5120 / size))
        for start in range(0, size, 256):
            yy, xx = np.mgrid[start : min(start + 256, size), :size]
            values = 100 * np.exp(
                -((xx / size - 0.5) ** 2 + (yy / size - 0.5) ** 2) / 0.015
            )
            dataset.GetRasterBand(1).WriteArray(values, 0, start)
        dataset = None
        times = []
        shapes = []
        cache = {}
        for repetition in range(6):
            step.parameters["HEIGHT"] = 100 + 50 * repetition
            request = (
                filename,
                1,
                (501280, 6496160, 503840, 6498720),
                (512, 512),
                [step],
                [algorithm.create()],
            )
            worker = PreviewWorker(1, Event(), request, app, cache)
            results = []
            worker.result.connect(lambda _generation, result: results.append(result))
            started = time.perf_counter()
            worker.start()
            while worker.isRunning():
                app.processEvents()
                QTest.qWait(1)
            app.processEvents()
            assert results and not isinstance(results[0], str), results
            grid, elapsed = results[0]
            times.append(
                dict(
                    compute_seconds=elapsed,
                    wall_seconds=time.perf_counter() - started,
                    cache_hit=worker.cache_hit,
                )
            )
            shapes.append(grid.values.shape)
            worker.deleteLater()
        measurements.append(
            dict(
                native_shape=[size, size],
                preview_shapes=shapes,
                cold_or_first=times[0],
                warm=times[1:],
            )
        )
    (output / "timings.json").write_text(
        json.dumps(measurements, indent=2), encoding="utf-8"
    )
    print("BENCHMARKS COMPLETE", flush=True)
    if os.environ.get("TW_PREVIEW_BENCH_ONLY"):
        return

    # The public CSV is pinned by the same source record as the existing survey benchmark.
    import pandas as pd
    from scipy.interpolate import griddata

    source = Path(os.environ["TW_PREVIEW_BRITAIN"])
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == "4e00894c2e0fa5b9c547719c8ac08adb6e788a7074c0dae9fb1b2767cf494b38"
    data = pd.read_csv(source)
    geographic = osr.SpatialReference()
    geographic.ImportFromEPSG(4326)
    geographic.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    reference.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    projection = osr.CoordinateTransformation(geographic, reference)
    points = np.asarray(
        projection.TransformPoints(list(zip(data.longitude, data.latitude)))
    )
    x, y = points[:, 0], points[:, 1]
    cell = 1000.0
    xmin, xmax = np.floor(x.min() / cell) * cell, np.ceil(x.max() / cell) * cell
    ymin, ymax = np.floor(y.min() / cell) * cell, np.ceil(y.max() / cell) * cell
    gx, gy = np.meshgrid(
        np.arange(xmin, xmax, cell) + cell / 2, np.arange(ymax, ymin, -cell) - cell / 2
    )
    values = griddata(
        (x, y), data.total_field_anomaly_nt.to_numpy(), (gx, gy), method="linear"
    )
    filename = str(output / "britain-public.tif")
    grid = RasterGrid(
        values, (xmin, cell, 0, ymax, 0, -cell), wkt, float("nan"), {}, str(source)
    )
    write_geotiff(
        filename, values, grid, "Britain digitized magnetic anomaly", float("nan")
    )
    layer = QgsRasterLayer(filename, "Britain | BGS / UKRI 2021 / Fatiando a Terra")
    project = QgsProject.instance()
    project.addMapLayer(layer)
    window = QMainWindow()
    window.setWindowTitle("TerraWorkbench | Britain | Vista previa en vivo")
    canvas = QgsMapCanvas()
    window.setCentralWidget(canvas)
    canvas.setDestinationCrs(layer.crs())
    canvas.setExtent(layer.extent())
    bridge = QgsLayerTreeMapCanvasBridge(project.layerTreeRoot(), canvas)
    assert bridge

    class Iface(QObject):
        currentLayerChanged = pyqtSignal(object)

        def mapCanvas(self):
            return canvas

        def activeLayer(self):
            return layer

        def addCustomActionForLayerType(self, *args):
            pass

        def addCustomActionForLayer(self, *args):
            pass

        def removeCustomActionForLayerType(self, *args):
            pass

    dock = FilterStackDock(window, iface=Iface())
    window.addDockWidget(Qt.RightDockWidgetArea, dock)
    window.resize(1280, 900)
    window.show()
    app.processEvents()
    window.resizeDocks([dock], [460], Qt.Horizontal)
    item = QListWidgetItem()
    dock._set_item_step(item, step)
    dock.step_list.addItem(item)
    dock.step_list.setCurrentRow(0)
    live = dock.live_preview
    live.enabled.setChecked(True)
    frames = []
    for index, height in enumerate(
        (100, 300, 600, 1000, 1500, 2500, 4000, 6000, 9000, 12000)
    ):
        request_started = time.perf_counter()
        dock._parameter_editors["HEIGHT"][0].setText(str(height))
        deadline = time.monotonic() + 30
        while (
            live.timer.isActive() or live.worker is not None or live.layer is None
        ) and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        assert live.layer is not None, live.status.text()
        publication_seconds = time.perf_counter() - request_started
        if index == 0:
            # Use QGIS's own public style catalogue; no GeoRamp palette is copied.
            ramp = QgsStyle.defaultStyle().colorRamp("Spectral")
            shader = QgsColorRampShader(-250, 250)
            shader.setColorRampType(QgsColorRampShader.Interpolated)
            shader.setColorRampItemList(
                [
                    QgsColorRampShader.ColorRampItem(-250 + i * 5, ramp.color(i / 100))
                    for i in range(101)
                ]
            )
            raster_shader = QgsRasterShader()
            raster_shader.setRasterShaderFunction(shader)
            live.layer.setRenderer(
                QgsSingleBandPseudoColorRenderer(
                    live.layer.dataProvider(), 1, raster_shader
                )
            )
        live.layer.triggerRepaint()
        window.setWindowTitle(
            f"TerraWorkbench | Britain | Continuación ascendente: {height} m"
        )
        window.statusBar().showMessage(
            f"Britain | Continuación ascendente: {height} m | BGS / UKRI 2021 / Fatiando a Terra"
        )
        canvas.refresh()
        deadline = time.monotonic() + 10
        while canvas.isDrawing() and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        QTest.qWait(150)
        dock.step_list.doItemsLayout()
        dock.step_list.viewport().repaint()
        path = output / f"preview-{index:02d}.png"
        assert window.grab().save(str(path), "PNG")
        frames.append(
            dict(
                file=path.name,
                height_metres=height,
                compute_seconds=live.elapsed,
                publication_seconds=publication_seconds,
            )
        )
    (output / "capture-provenance.json").write_text(
        json.dumps(
            dict(
                runtime_sources_sha256={
                    name: hashlib.sha256(
                        (
                            Path(sys.modules["TerraWorkbench"].__file__).parent / name
                        ).read_bytes()
                    ).hexdigest()
                    for name in (
                        "ui/live_preview.py",
                        "ui/workflow_dock.py",
                        "qgis_plugin/raster_io.py",
                        "terraworkbench_core/live_preview.py",
                    )
                },
                source_sha256=digest,
                source_url="https://github.com/fatiando-data/britain-magnetic/releases/download/v1/britain-magnetic.csv.xz",
                attribution="Contains British Geological Survey materials, UKRI 2021; Fatiando a Terra Datasets",
                license="CC-BY-4.0 processed product; BGS source under Open Government Licence",
                gridding="Linear interpolation, UTM 30N, 1000 m; no field validation",
                capture="Actual offscreen QGIS widgets; frame duration 1000 ms; no desktop input",
                frames=frames,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    live.enabled.setChecked(False)
    dock.disconnect_project()
    window.close()
    project.clear()
    print("PUBLIC CAPTURES COMPLETE", flush=True)


if __name__ == "__main__":
    main()

"""Debounced, serial background preview owned by the filter dock.

Only file names, CRS snapshots, cloned algorithms and numbers cross into the
worker. QGIS project layers and map-canvas state are accessed on the GUI thread.
"""

import time
import uuid
import os
from dataclasses import replace
import numpy as np

from osgeo import gdal
from qgis.PyQt.QtCore import QObject, QThread, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QCheckBox, QPushButton, QLabel, QHBoxLayout
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProject,
    QgsRasterLayer,
)

from ..qgis_plugin.raster_io import (
    RasterGrid,
    write_geotiff,
    to_regular_data_array,
    restore_raster_order,
)
from ..qgis_plugin.georamp import installed_georamp, open_georamp
from ..terraworkbench_core.live_preview import LatestRequest, preview_window
from .i18n import text


class PreviewWorker(QThread):
    """Run one bounded raster stack; interruption is cooperative between stages."""

    result = pyqtSignal(int, object)

    def __init__(self, generation, token, request, parent, cache=None):
        """Accept immutable request snapshots and an optional single-window cache."""
        super().__init__(parent)
        self.generation, self.token, self.request = generation, token, request
        self.feedback = QgsProcessingFeedback()
        self.cache = cache if cache is not None else {}
        self.cache_hit = False

    def run(self):
        """Read only the preview window and run cloned Processing algorithms."""
        from .workflow_dock import _run_combined_spectral_stack
        from ..algorithms.spectral_filters import SpectralFilterBase
        from ..algorithms.transforms import HarmonicaTransformBase

        started = time.perf_counter()
        source, band, extent, screen, steps, algorithms = self.request
        paths = []
        try:
            if self.token.is_set():
                return
            grid = self.read_window(source, band, extent, screen)
            values = grid.values
            if self.token.is_set():
                return
            if all(
                isinstance(algorithm, HarmonicaTransformBase)
                for algorithm in algorithms
            ):
                grid = self.harmonica_stack(grid, steps, algorithms)
                if not self.token.is_set():
                    self.result.emit(
                        self.generation, (grid, time.perf_counter() - started)
                    )
                return
            input_path = "/vsimem/tw-preview-" + uuid.uuid4().hex + ".tif"
            paths.append(input_path)
            write_geotiff(input_path, values, grid, "Preview input", grid.nodata)
            context = QgsProcessingContext()
            settings = [
                a.preprocessing_values(s.parameters, context)
                if isinstance(a, SpectralFilterBase)
                else None
                for a, s in zip(algorithms, steps)
            ]
            if all(settings) and all(s[:3] == settings[0][:3] for s in settings):
                output, intermediates = _run_combined_spectral_stack(
                    input_path,
                    1,
                    steps,
                    algorithms,
                    settings,
                    context,
                    self.feedback,
                    None,
                    False,
                    temporary_prefix=input_path[:-4],
                )
                paths.extend(intermediates)
            else:
                # Legacy Harmonica and spatial algorithms have no shared FFT
                # preparation contract. Reflect/taper their bounded input once
                # and discard that margin after the complete selected chain.
                from ..terraworkbench_core.spectral import prepare_fft_grid

                original_grid = grid
                data = np.asarray(values, dtype=float).copy()
                if grid.nodata is not None:
                    data[data == grid.nodata] = np.nan
                padded, state = prepare_fft_grid(data, detrend_order=0)
                padded += state["trend"][0, 0]
                py, px = state["padding_cells"]
                x, dx, _, y, _, dy = grid.geotransform
                grid = RasterGrid(
                    padded,
                    (x - px * dx, dx, 0, y - py * dy, 0, dy),
                    grid.projection,
                    None,
                    {"TW_PREVIEW": "1"},
                    source,
                )
                write_geotiff(input_path, padded, grid, "Padded preview input")
                output = input_path
                for step, algorithm in zip(steps, algorithms):
                    if self.token.is_set():
                        return
                    destination = "/vsimem/tw-preview-" + uuid.uuid4().hex + ".tif"
                    paths.append(destination)
                    result, ok = algorithm.run(
                        dict(step.parameters, INPUT=output, BAND=1, OUTPUT=destination),
                        context,
                        self.feedback,
                    )
                    if not ok:
                        raise ValueError("Preview calculation failed")
                    output = result["OUTPUT"]
            if self.token.is_set():
                return
            result = gdal.Open(str(output))
            result_band = result.GetRasterBand(1)
            grid = RasterGrid(
                result_band.ReadAsArray(),
                result.GetGeoTransform(),
                result.GetProjection(),
                result_band.GetNoDataValue(),
                {"TW_PREVIEW": "1"},
                source,
            )
            result = None
            if not (all(settings) and all(s[:3] == settings[0][:3] for s in settings)):
                values = grid.values[state["row_slice"], state["column_slice"]].copy()
                values[state["missing"]] = np.nan
                grid = RasterGrid(
                    values,
                    original_grid.geotransform,
                    grid.projection,
                    float("nan"),
                    {"TW_PREVIEW": "1"},
                    source,
                )
            self.result.emit(self.generation, (grid, time.perf_counter() - started))
        except Exception as error:
            if not self.token.is_set():
                self.result.emit(self.generation, str(error))
        finally:
            for path in paths:
                if str(path).startswith("/vsimem/") and gdal.VSIStatL(str(path)):
                    gdal.Unlink(str(path))

    def read_window(self, source, band, extent, screen):
        """Reuse one input window across parameter edits; invalidate on file changes."""
        stat = os.stat(source) if os.path.isfile(source) else None
        identity = (stat.st_size, stat.st_mtime_ns) if stat else None
        key = (source, band, extent, screen, identity)
        self.window_key = key
        cached = self.cache.get(key)
        if cached is not None:
            self.cache_hit = True
            return replace(
                cached, values=cached.values.copy(), metadata=dict(cached.metadata)
            )
        dataset = gdal.Open(source)
        window = preview_window(
            dataset.GetGeoTransform(),
            (dataset.RasterYSize, dataset.RasterXSize),
            extent,
            screen,
            max_side=512,
        )
        raster_band = dataset.GetRasterBand(band)
        values = raster_band.ReadAsArray(
            window.xoff,
            window.yoff,
            window.width,
            window.height,
            window.columns,
            window.rows,
            resample_alg=gdal.GRIORA_Bilinear,
        )
        grid = RasterGrid(
            values,
            window.transform,
            dataset.GetProjection(),
            raster_band.GetNoDataValue(),
            {"TW_PREVIEW": "1"},
            source,
        )
        dataset = None
        if not self.token.is_set():
            self.cache.clear()
            self.cache[key] = grid
        return replace(grid, values=grid.values.copy(), metadata=dict(grid.metadata))

    def harmonica_stack(self, grid, steps, algorithms):
        """Call the algorithms' public array calculations without raster round trips."""
        if QgsCoordinateReferenceSystem.fromWkt(grid.projection).isGeographic():
            raise ValueError(
                text(
                    "Use a projected raster for filtering.",
                    "Use un ráster proyectado para filtrar.",
                )
            )
        from ..qgis_plugin.dependencies import import_harmonica
        from ..terraworkbench_core.spectral import prepare_fft_grid

        harmonica = import_harmonica()
        orientation = to_regular_data_array(grid, fill_missing=True)
        padded, state = prepare_fft_grid(orientation.data.values, detrend_order=0)
        padded += state["trend"][0, 0]
        import xarray as xr

        py, px = state["padding_cells"]
        northing = np.asarray(orientation.data.coords["northing"])
        easting = np.asarray(orientation.data.coords["easting"])
        data = xr.DataArray(
            padded,
            dims=("northing", "easting"),
            coords={
                "northing": northing[0]
                + (np.arange(padded.shape[0]) - py) * (northing[1] - northing[0]),
                "easting": easting[0]
                + (np.arange(padded.shape[1]) - px) * (easting[1] - easting[0]),
            },
        )
        context = QgsProcessingContext()
        source_values = grid.values
        kernels = []
        for step, algorithm in zip(steps, algorithms):
            name = algorithm.name()
            parameters = step.parameters
            if name in (
                "upward_continuation",
                "mag_upward_continuation",
                "grav_upward_continuation",
            ):
                kernels.append(
                    (
                        "upward_continuation_kernel",
                        {"height_displacement": parameters["HEIGHT"]},
                    )
                )
            elif name in ("gaussian_lowpass", "gaussian_highpass"):
                kernels.append(
                    (name + "_kernel", {"wavelength": parameters["WAVELENGTH"]})
                )
            elif name == "reduction_to_pole":
                kernels.append(
                    (
                        "reduction_to_pole_kernel",
                        dict(
                            inclination=parameters["INCLINATION"],
                            declination=parameters["DECLINATION"],
                            magnetization_inclination=parameters.get(
                                "MAGNETIZATION_INCLINATION"
                            ),
                            magnetization_declination=parameters.get(
                                "MAGNETIZATION_DECLINATION"
                            ),
                        ),
                    )
                )
            else:
                kernels = []
                break
        if kernels:
            # Public Harmonica kernels retain its conventions. NumPy owns one
            # transform pair, avoiding xrft's repeated coordinate transforms.
            from ..terraworkbench_core.spectral import apply_spectrum

            frequency = xr.DataArray(
                np.broadcast_to(0.0, padded.shape),
                dims=("freq_northing", "freq_easting"),
                coords={
                    "freq_northing": np.fft.fftfreq(
                        padded.shape[0], northing[1] - northing[0]
                    ),
                    "freq_easting": np.fft.fftfreq(
                        padded.shape[1], easting[1] - easting[0]
                    ),
                },
            )
            response = np.ones(padded.shape, dtype=complex)
            for index, (name, arguments) in enumerate(kernels):
                if self.token.is_set():
                    return grid
                if index == len(kernels) - 1 and index and name == "reduction_to_pole_kernel":
                    # Match the native stack: only the published final RTP gets
                    # its mean; preceding stages retain the raw FFT workspace.
                    previous = apply_spectrum(np.fft.fft2(padded), response)
                    source_values = restore_raster_order(
                        previous[state["row_slice"], state["column_slice"]], orientation
                    )
                response *= (
                    getattr(harmonica.filters, name)(frequency, **arguments)
                    .transpose(*frequency.dims)
                    .values
                )
            if not np.isfinite(response).all():
                raise ValueError("Non-finite preview FFT response")
            fft_key = ("fft", self.window_key, padded.shape)
            transformed = self.cache.get(fft_key)
            if transformed is None:
                transformed = np.fft.fft2(padded)
                if not self.token.is_set():
                    self.cache[fft_key] = transformed
            filtered = apply_spectrum(transformed, response)
            values = filtered[state["row_slice"], state["column_slice"]]
            grid.values = algorithms[-1].finalize_values(
                restore_raster_order(values, orientation), source_values,
                steps[-1].parameters, context,
            )
            grid.nodata = float("nan")
            return grid
        for index, (step, algorithm) in enumerate(zip(steps, algorithms)):
            if self.token.is_set():
                return grid
            if index == len(steps) - 1 and index:
                source_values = restore_raster_order(
                    np.asarray(data.values)[state["row_slice"], state["column_slice"]],
                    orientation,
                )
            data = algorithm.calculate(harmonica, data, step.parameters, context)
        values = np.asarray(data.values)[state["row_slice"], state["column_slice"]]
        grid.values = algorithms[-1].finalize_values(
            restore_raster_order(values, orientation), source_values,
            steps[-1].parameters, context,
        )
        grid.nodata = float("nan")
        return grid


class LivePreview(QObject):
    """Own one temporary map layer and one worker, replacing obsolete requests."""

    updated = pyqtSignal(int, float)

    def __init__(self, dock, layout):
        """Attach translated controls and view-change signals to their owning dock."""
        super().__init__(dock)
        self.dock, self.layer, self.worker = dock, None, None
        self.latest = LatestRequest()
        self.cache = {}
        self.pending = False
        self.path = "/vsimem/tw-live-" + uuid.uuid4().hex + ".tif"
        self.enabled = QCheckBox()
        self.before = QCheckBox()
        self.before.setShortcut("F6")
        self.colours = QPushButton()
        self.status = QLabel()
        self.status.setWordWrap(True)
        switches = QHBoxLayout()
        switches.addWidget(self.enabled)
        switches.addWidget(self.before)
        colours = QHBoxLayout()
        colours.addWidget(self.colours, 1)
        self.status.setMaximumWidth(90)
        colours.addWidget(self.status)
        layout.addLayout(switches)
        layout.addLayout(colours)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.launch)
        self.enabled.toggled.connect(self.toggle)
        self.before.toggled.connect(self.compare)
        self.colours.clicked.connect(self.adjust_colours)
        dock.layer_combo.currentIndexChanged.connect(self.schedule)
        dock.band_spin.valueChanged.connect(self.schedule)
        dock.step_list.currentRowChanged.connect(self.schedule)
        for signal in (
            dock.step_list.model().rowsInserted,
            dock.step_list.model().rowsRemoved,
            dock.step_list.model().rowsMoved,
        ):
            signal.connect(self.schedule)
        dock.visibilityChanged.connect(self.visibility_changed)
        self.canvas = (
            dock.iface.mapCanvas()
            if dock.iface and hasattr(dock.iface, "mapCanvas")
            else None
        )
        self.enabled.setEnabled(self.canvas is not None)
        self.before.setEnabled(self.canvas is not None)
        self.colours.setEnabled(dock.iface is not None)
        if self.canvas:
            self.canvas.extentsChanged.connect(self.schedule)
        QgsProject.instance().cleared.connect(self.project_cleared)
        QgsProject.instance().layersWillBeRemoved.connect(self.layers_removed)
        QgsProject.instance().writeProject.connect(self.omit_from_project)
        QgsProject.instance().projectSaved.connect(self.resume_after_save)
        self.retranslate()

    def omit_from_project(self, document):
        """Keep the in-memory preview out of a saved QGIS project."""
        if self.layer is None:
            return
        layer_id = self.layer.id()
        for tag in ("maplayer", "layer-tree-layer", "legendlayerfile", "layer", "item"):
            nodes = document.elementsByTagName(tag)
            for index in reversed(range(nodes.count())):
                element = nodes.at(index).toElement()
                matches = (
                    element.attribute("id") == layer_id
                    or element.attribute("layerid") == layer_id
                    or element.firstChildElement("id").text() == layer_id
                    or (tag == "item" and element.text() == layer_id)
                )
                if matches:
                    parent = element.parentNode()
                    if tag == "legendlayerfile":
                        element, parent = parent, parent.parentNode()
                    parent.removeChild(element)
        # writeProject precedes serialization of map layers. Retire the layer
        # now, then rebuild it after the saved project is complete.
        self._resume_after_save = self.enabled.isChecked()
        self.stop()

    def resume_after_save(self):
        """Recalculate a live preview after saving without serializing its layer."""
        if getattr(self, "_resume_after_save", False):
            self._resume_after_save = False
            self.schedule()

    def project_cleared(self):
        """Do not carry a preview request into a different QGIS project."""
        self.enabled.setChecked(False)
        self.stop()

    def layers_removed(self, ids):
        """Forget a layer removed externally before its C++ wrapper expires."""
        if self.layer is not None and self.layer.id() in ids:
            self.layer = None

    def retranslate(self):
        """Refresh controls after a runtime language change."""
        self.enabled.setText(text("Live preview", "Vista previa en vivo"))
        self.before.setText(text("Before / after (F6)", "Antes / después (F6)"))
        self.colours.setText(
            text("Adjust colours (GeoRamp)", "Ajustar colores (GeoRamp)")
            if installed_georamp()
            else text("Install GeoRamp", "Instalar GeoRamp")
        )
        if self.layer:
            self.layer.setName(text("Preview", "Vista previa"))
            self.action.setText(self.colours.text())

    def visibility_changed(self, visible):
        """Stop when the panel closes or the plugin unloads."""
        if not visible:
            self.enabled.setChecked(False)

    def toggle(self, enabled):
        """Enable updates or remove the temporary layer immediately."""
        if enabled:
            self.schedule()
        else:
            self.stop()

    def schedule(self, *_args):
        """Cancel obsolete work immediately, then debounce the newest request."""
        if not self.enabled.isChecked():
            return
        self.latest.replace()
        if self.worker:
            self.worker.feedback.cancel()
        self.pending = True
        self.timer.start()

    def launch(self):
        """Snapshot GUI state and start only after the previous worker exits."""
        if self.worker or not self.pending or not self.enabled.isChecked():
            return
        self.pending = False
        dock = self.dock
        source = dock._selected_raster()
        if source is None or self.canvas is None:
            self.stop()
            return
        if not dock.update_current_parameters():
            return
        steps = dock.steps()[: dock.step_list.currentRow() + 1]
        if not steps:
            self.stop()
            return
        extent = self.canvas.extent()
        if self.canvas.mapSettings().destinationCrs() != source.crs():
            extent = QgsCoordinateTransform(
                self.canvas.mapSettings().destinationCrs(),
                source.crs(),
                QgsProject.instance(),
            ).transformBoundingBox(extent)
        request = (
            source.source(),
            dock.band_spin.value(),
            (
                extent.xMinimum(),
                extent.yMinimum(),
                extent.xMaximum(),
                extent.yMaximum(),
            ),
            (self.canvas.width(), self.canvas.height()),
            steps,
            [dock._algorithm(s.algorithm_id).create() for s in steps],
        )
        self.worker = PreviewWorker(
            self.latest.generation, self.latest.cancelled, request, self, self.cache
        )
        self.worker.result.connect(self.publish)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def finished(self):
        """Release the old thread and run a pending request after its debounce."""
        self.worker.deleteLater()
        self.worker = None
        if self.pending and not self.timer.isActive():
            self.launch()

    def publish(self, generation, result):
        """Publish current results on the GUI thread, preserving the layer ID."""
        if not self.latest.accepts(generation) or not self.enabled.isChecked():
            return
        if isinstance(result, str):
            self.status.setText(
                text(
                    "Preview failed: {error}", "Falló la vista previa: {error}"
                ).format(error=result)
            )
            return
        grid, self.elapsed = result
        self.last_cache_hit = self.worker.cache_hit
        renderer = self.layer.renderer().clone() if self.layer else None
        previous_path = self.path
        self.path = "/vsimem/tw-live-" + uuid.uuid4().hex + ".tif"
        write_geotiff(self.path, grid.values, grid, "Live preview", grid.nodata)
        if self.layer is None:
            self.layer = QgsRasterLayer(self.path, text("Preview", "Vista previa"))
            self.layer.setCustomProperty("TerraWorkbench/livePreview", True)
            self.layer.setFlags(self.layer.flags() & ~QgsRasterLayer.Removable)
            QgsProject.instance().addMapLayer(self.layer)
            from qgis.PyQt.QtWidgets import QAction

            self.action = QAction(self.colours.text(), self.layer)
            self.action.triggered.connect(self.adjust_colours)
            if hasattr(self.dock.iface, "addCustomActionForLayerType"):
                self.dock.iface.addCustomActionForLayerType(
                    self.action, "TerraWorkbench", self.layer.type(), False
                )
                self.dock.iface.addCustomActionForLayer(self.action, self.layer)
        else:
            self.layer.setDataSource(self.path, self.layer.name(), "gdal")
            if renderer:
                self.layer.setRenderer(renderer)
        if gdal.VSIStatL(previous_path):
            gdal.Unlink(previous_path)
        self.compare()
        self.status.setText(f"{self.elapsed * 1000:.0f} ms")
        self.layer.triggerRepaint()
        self.updated.emit(generation, self.elapsed)

    def compare(self, *_args):
        """Toggle only the preview; the original remains beneath it."""
        if self.layer:
            node = QgsProject.instance().layerTreeRoot().findLayer(self.layer.id())
            if node:
                node.setItemVisibilityChecked(not self.before.isChecked())

    def adjust_colours(self):
        """Open GeoRamp for the preview or the selected source raster."""
        steps = self.dock.steps()[: self.dock.step_list.currentRow() + 1]
        open_georamp(
            self.dock.iface,
            self.layer or self.dock._selected_raster(),
            steps[-1].algorithm_id if steps else "",
        )
        self.retranslate()

    def stop(self):
        """Invalidate results and release the layer without blocking the GUI."""
        self.latest.replace()
        self.pending = False
        self.cache.clear()
        self.timer.stop()
        if self.worker:
            self.worker.feedback.cancel()
        if self.layer:
            if hasattr(self.dock.iface, "removeCustomActionForLayerType"):
                self.dock.iface.removeCustomActionForLayerType(self.action)
            QgsProject.instance().removeMapLayer(self.layer.id())
            self.layer = None
        if gdal.VSIStatL(self.path):
            gdal.Unlink(self.path)
        self.status.clear()

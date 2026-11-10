"""Native QGIS stage views and bounded, explicitly sampled grid diagnostics."""

import json
import numpy as np
from osgeo import gdal, osr

from qgis.core import QgsRasterLayer, QgsSingleBandGrayRenderer, QgsContrastEnhancement
from qgis.gui import QgsMapCanvas, QgsMapToolPan
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QSplitter,
    QPlainTextEdit,
    QCheckBox,
    QLineEdit,
)

from ..qgis_plugin.qgis_compat import qt_enum
from .survey_workspace_dialog import tr, StoreWorker


def sampled_statistics(values):
    finite = values[np.isfinite(values)]
    return {
        "valid_preview_cells": int(finite.size),
        "min": float(finite.min()) if finite.size else None,
        "max": float(finite.max()) if finite.size else None,
        "mean": float(finite.mean()) if finite.size else None,
        "population_std": float(finite.std()) if finite.size else None,
    }


def read_stage(record, cancel=None):
    if cancel and cancel():
        raise InterruptedError("Stage preview cancelled")
    dataset = gdal.OpenEx(
        str(record["path"]).split("|", 1)[0], gdal.OF_RASTER | gdal.OF_READONLY
    )
    if dataset is None:
        raise ValueError("Stage raster is no longer available: " + str(record["path"]))
    try:
        width, height = dataset.RasterXSize, dataset.RasterYSize
        band = dataset.GetRasterBand(int(record.get("band", 1)))
        if band is None:
            raise ValueError("Stage band is not available")
        nx, ny = min(width, 512), min(height, 512)
        data = band.ReadAsArray(buf_xsize=nx, buf_ysize=ny)
        if np.iscomplexobj(data):
            raise ValueError(
                "Complex grids require an explicit component before stage comparison"
            )
        values = np.asarray(data, dtype=float)
        mask = band.GetMaskBand().ReadAsArray(buf_xsize=nx, buf_ysize=ny) == 0
        nodata = band.GetNoDataValue()
        mask |= ~np.isfinite(values)
        if nodata is not None:
            mask |= values == nodata
        scale, offset = band.GetScale(), band.GetOffset()
        scale, offset = (
            1.0 if scale is None else float(scale),
            0.0 if offset is None else float(offset),
        )
        if not np.isfinite([scale, offset]).all():
            raise ValueError("Invalid GDAL band scale/offset")
        values = values * scale + offset
        mask |= ~np.isfinite(values)
        values[mask] = np.nan
        result = {
            **record,
            "band": int(record.get("band", 1)),
            "grid_shape": [height, width],
            "preview_shape": [ny, nx],
            "sampled": nx != width or ny != height,
            "geotransform": dataset.GetGeoTransform(can_return_null=True),
            "wkt": dataset.GetProjectionRef(),
            "unit": band.GetUnitType() or "",
            "scale_applied": scale,
            "offset_applied": offset,
            "statistics": sampled_statistics(values),
            "values": values,
        }
    finally:
        dataset = None
    if cancel and cancel():
        raise InterruptedError("Stage preview cancelled")
    return result


def compatible_geometry(a, b):
    if (
        a["grid_shape"] != b["grid_shape"]
        or a["geotransform"] is None
        or b["geotransform"] is None
        or not a["wkt"]
        or not b["wkt"]
    ):
        return False
    first, second = osr.SpatialReference(), osr.SpatialReference()
    first.ImportFromWkt(a["wkt"])
    second.ImportFromWkt(b["wkt"])
    return bool(first.IsSame(second)) and bool(
        np.allclose(a["geotransform"], b["geotransform"], rtol=0, atol=1e-9)
    )


def compare_stages(a, b, declared_unit=""):
    if not compatible_geometry(a, b):
        raise ValueError(
            "Different or unknown grid geometry/CRS; no automatic alignment"
        )
    if a["unit"] and b["unit"] and a["unit"] != b["unit"]:
        raise ValueError("Declared raster units differ; no automatic conversion")
    unit = a["unit"] if a["unit"] and a["unit"] == b["unit"] else declared_unit.strip()
    if not unit or any(record["unit"] and record["unit"] != unit for record in (a, b)):
        raise ValueError(
            "Confirm the same physical quantity and explicit units for both grids"
        )
    return {
        "difference": "B - A",
        "unit": unit,
        "unit_source": "both GDAL bands"
        if a["unit"] and a["unit"] == b["unit"]
        else "explicit reviewer declaration; source metadata unchanged",
        "sampled": a["sampled"] or b["sampled"],
        "statistics": sampled_statistics(b["values"] - a["values"]),
    }


class RasterStageReview(QDialog):
    def __init__(self, stages, parent=None):
        super().__init__(parent)
        self.stages = stages
        self.worker = None
        self.close_requested = False
        self.layers = []
        self.samples = None
        self._linking = False
        self.setWindowTitle(
            tr(
                "Raster stages · compare and inspect",
                "Etapas de grids · comparar e inspeccionar",
                "Etapas de grades · comparar e inspecionar",
            )
        )
        self.resize(1160, 780)
        layout = QVBoxLayout(self)
        note = QLabel(
            tr(
                "Read-only A/B views. Diagnostics use at most 512 × 512 nearest-sampled cells, not full-grid statistics. No resampling to a new geometry, processing or file changes. QGIS supplies map navigation.",
                "Vistas A/B de solo lectura. Los diagnósticos usan como máximo 512 × 512 celdas por muestreo vecino, no estadísticas completas del grid. Sin alineación a otra geometría, procesamiento ni cambios de archivos. QGIS proporciona la navegación.",
                "Vistas A/B somente leitura. Diagnósticos usam no máximo 512 × 512 células por amostragem vizinha, não estatísticas completas da grade. Sem alinhamento a outra geometria, processamento ou alterações de arquivos. QGIS fornece a navegação.",
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        controls = QHBoxLayout()
        self.a, self.b = QComboBox(), QComboBox()
        for combo in (self.a, self.b):
            for index, stage in enumerate(stages):
                combo.addItem(stage["label"], index)
        self.b.setCurrentIndex(max(0, len(stages) - 1))
        controls.addWidget(QLabel("A"))
        controls.addWidget(self.a, 1)
        controls.addWidget(QLabel("B"))
        controls.addWidget(self.b, 1)
        self.load_button = QPushButton(tr("Load A/B", "Cargar A/B", "Carregar A/B"))
        self.load_button.clicked.connect(self.load)
        controls.addWidget(self.load_button)
        layout.addLayout(controls)
        maps = QSplitter(qt_enum(Qt, "Orientation", "Horizontal"))
        self.canvases = [QgsMapCanvas(), QgsMapCanvas()]
        self.tools = []
        for index, canvas in enumerate(self.canvases):
            maps.addWidget(canvas)
            tool = QgsMapToolPan(canvas)
            canvas.setMapTool(tool)
            self.tools.append(tool)
            canvas.extentsChanged.connect(lambda i=index: self.link_extent(i))
        layout.addWidget(maps, 1)
        bar = QHBoxLayout()
        self.link = QCheckBox(
            tr(
                "Link extents (same geometry only)",
                "Vincular extensión (solo geometría igual)",
                "Vincular extensão (apenas geometria igual)",
            )
        )
        self.link.setChecked(True)
        self.unit = QLineEdit()
        self.unit.setPlaceholderText(
            tr(
                "Confirm same quantity + unit if missing",
                "Confirma misma magnitud + unidad si falta",
                "Confirme mesma grandeza + unidade se ausente",
            )
        )
        compare = QPushButton(
            tr("B − A statistics", "Estadísticas B − A", "Estatísticas B − A")
        )
        compare.clicked.connect(self.compare)
        bar.addWidget(self.link)
        bar.addWidget(self.unit, 1)
        bar.addWidget(compare)
        layout.addLayout(bar)
        self.status = QLabel(
            tr(
                "Load two stages. Display stretches are independent until a compatible comparison is confirmed.",
                "Carga dos etapas. Las escalas visuales son independientes hasta confirmar una comparación compatible.",
                "Carregue duas etapas. Escalas visuais são independentes até confirmar uma comparação compatível.",
            )
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(180)
        layout.addWidget(self.details)

    def load(self):
        if self.worker is not None or not self.stages:
            return
        selected = [
            dict(self.stages[combo.currentData()]) for combo in (self.a, self.b)
        ]
        self.samples = None
        self.unit.clear()
        self.a.setEnabled(False)
        self.b.setEnabled(False)
        self.status.setText(
            tr(
                "Loading stage previews…",
                "Cargando vistas de etapas…",
                "Carregando vistas das etapas…",
            )
        )
        self.load_button.setEnabled(False)
        self.worker = StoreWorker(
            lambda cancel, progress: [
                read_stage(record, cancel) for record in selected
            ],
            self,
        )
        self.worker.completed.connect(self.loaded)
        self.worker.failed.connect(self.status.setText)
        self.worker.cancelled.connect(
            lambda: self.status.setText(tr("Cancelled", "Cancelado", "Cancelado"))
        )
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def loaded(self, samples):
        try:
            self.samples = samples
            for canvas in self.canvases:
                canvas.stopRendering()
                canvas.setLayers([])
            self.layers = []
            for canvas, sample in zip(self.canvases, samples):
                layer = QgsRasterLayer(sample["path"], sample["label"])
                if not layer.isValid():
                    raise ValueError("QGIS could not open the stage raster")
                self.layers.append(layer)
                self.stretch(
                    layer,
                    sample["band"],
                    sample["statistics"]["min"],
                    sample["statistics"]["max"],
                )
                canvas.setDestinationCrs(layer.crs())
                canvas.setLayers([layer])
                canvas.setExtent(layer.extent())
                canvas.refresh()
            self.details.setPlainText(
                json.dumps(
                    [
                        {key: value for key, value in sample.items() if key != "values"}
                        for sample in samples
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            self.status.setText(
                tr(
                    "A/B loaded · independent preview min/max stretches · diagnostics describe the displayed sample, not the full grid",
                    "A/B cargados · escalas mín./máx. independientes · los diagnósticos describen la muestra, no el grid completo",
                    "A/B carregados · escalas mín./máx. independentes · diagnósticos descrevem a amostra, não a grade completa",
                )
            )
        except Exception as error:
            self.samples = None
            self.status.setText(str(error))

    @staticmethod
    def stretch(layer, band, minimum, maximum):
        if minimum is None or maximum is None:
            return
        if maximum == minimum:
            maximum = minimum + max(abs(minimum) * 1e-6, 1e-9)
        provider = layer.dataProvider()
        renderer = QgsSingleBandGrayRenderer(provider, band)
        contrast = QgsContrastEnhancement(provider.dataType(band))
        contrast.setMinimumValue(minimum)
        contrast.setMaximumValue(maximum)
        contrast.setContrastEnhancementAlgorithm(
            qt_enum(
                QgsContrastEnhancement,
                "ContrastEnhancementAlgorithm",
                "StretchToMinimumMaximum",
            )
        )
        renderer.setContrastEnhancement(contrast)
        layer.setRenderer(renderer)

    def compare(self):
        if not self.samples:
            return
        try:
            result = compare_stages(*self.samples, self.unit.text())
            finite = [
                sample["values"][np.isfinite(sample["values"])]
                for sample in self.samples
            ]
            finite = [array for array in finite if array.size]
            if finite:
                low, high = (
                    min(array.min() for array in finite),
                    max(array.max() for array in finite),
                )
                for layer, sample, canvas in zip(
                    self.layers, self.samples, self.canvases
                ):
                    self.stretch(layer, sample["band"], float(low), float(high))
                    canvas.refresh()
            self.details.setPlainText(json.dumps(result, indent=2))
            self.status.setText(
                tr(
                    "Shared preview min/max stretch · B−A uses paired valid preview cells only · files unchanged",
                    "Escala mín./máx. compartida · B−A usa solo celdas válidas emparejadas de la muestra · archivos sin cambios",
                    "Escala mín./máx. compartilhada · B−A usa apenas células válidas pareadas da amostra · arquivos inalterados",
                )
            )
        except Exception as error:
            self.status.setText(str(error))

    def link_extent(self, index):
        if (
            self._linking
            or not self.link.isChecked()
            or not self.samples
            or not compatible_geometry(*self.samples)
        ):
            return
        self._linking = True
        try:
            other = self.canvases[1 - index]
            other.setExtent(self.canvases[index].extent())
            other.refresh()
        finally:
            self._linking = False

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.load_button.setEnabled(True)
        self.a.setEnabled(True)
        self.b.setEnabled(True)
        if self.close_requested:
            self.close()

    def closeEvent(self, event):
        if self.worker is not None:
            self.close_requested = True
            self.worker.requestInterruption()
            event.ignore()
            return
        for canvas in self.canvases:
            canvas.stopRendering()
            canvas.setLayers([])
        self.layers = []
        event.accept()

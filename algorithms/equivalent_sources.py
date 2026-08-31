"""Equivalent-source interpolation and continuation for regular grids."""

from __future__ import annotations

import numpy as np
from qgis.core import QgsProcessingException, QgsProcessingParameterNumber

from .base import RasterAlgorithmBase
from ..dependencies import import_harmonica
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER
from ..raster_io import restore_raster_order, to_regular_data_array, write_geotiff


class EquivalentSourceContinuationAlgorithm(RasterAlgorithmBase):
    SOURCE_DEPTH = "SOURCE_DEPTH"
    DAMPING = "DAMPING"
    TARGET_HEIGHT = "TARGET_HEIGHT"
    BLOCK_SIZE = "BLOCK_SIZE"
    MAX_CELLS = "MAX_CELLS"
    processing_domain = "EQUIVALENT SOURCES / PHYSICAL MODEL"

    def name(self):
        return "equivalent_source_continuation"

    def displayName(self):
        return self.tr("Equivalent sources — fit and continue regular grid")

    def group(self):
        return self.tr("Potential-field modelling and depth")

    def groupId(self):
        return "potential_field_modelling"

    def initAlgorithm(self, config=None):
        del config
        self.add_raster_parameters()
        self.addParameter(QgsProcessingParameterNumber(
            self.SOURCE_DEPTH, self.tr("Equivalent-source depth below observations (CRS units)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=500.0, minValue=0.000001,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.DAMPING, self.tr("Damping regularization (0 = none)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.TARGET_HEIGHT, self.tr("Prediction height above input grid (CRS units)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.BLOCK_SIZE, self.tr("Source block size (0 = one source per cell)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_CELLS, self.tr("Safety limit: fitted grid cells"),
            type=PROCESSING_NUMBER_INTEGER, defaultValue=20000, minValue=4,
        ))

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context, require_projected=True)
        orientation = to_regular_data_array(grid)
        data = orientation.data
        cells = int(data.size)
        limit = self.parameterAsInt(parameters, self.MAX_CELLS, context)
        if cells > limit:
            raise QgsProcessingException(
                f"Grid has {cells:,} cells; resample or raise the explicit safety limit ({limit:,})."
            )
        easting, northing = np.meshgrid(
            np.asarray(data.coords["easting"], dtype=float),
            np.asarray(data.coords["northing"], dtype=float),
        )
        upward = np.zeros(easting.size, dtype=float)
        coordinates = (easting.ravel(), northing.ravel(), upward)
        damping = self.parameterAsDouble(parameters, self.DAMPING, context)
        block_size = self.parameterAsDouble(parameters, self.BLOCK_SIZE, context)
        harmonica = import_harmonica()
        model = harmonica.EquivalentSources(
            damping=None if damping == 0.0 else damping,
            depth=self.parameterAsDouble(parameters, self.SOURCE_DEPTH, context),
            block_size=None if block_size == 0.0 else block_size,
            parallel=True,
        )
        feedback.pushInfo(f"Fitting {cells:,} observations with equivalent sources.")
        model.fit(coordinates, np.asarray(data.values, dtype=float).ravel())
        feedback.setProgress(65)
        target_upward = np.full(
            upward.shape,
            self.parameterAsDouble(parameters, self.TARGET_HEIGHT, context),
        )
        prediction = model.predict((coordinates[0], coordinates[1], target_upward))
        values = restore_raster_order(prediction.reshape(data.shape), orientation)
        output = self.output_path(parameters, context)
        write_geotiff(output, values, grid, "Equivalent-source prediction")
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr("Fits Harmonica equivalent point sources below a complete projected grid and predicts the field on the same horizontal mesh at a configurable relative height. Damping and source blocking control stability and cost. This is a physical interpolation/continuation model, not a unique source-depth estimate; use spatial holdout validation and sensitivity tests.")

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
    MAX_MATRIX_ELEMENTS = "MAX_MATRIX_ELEMENTS"
    HOLDOUT_PERCENT = "HOLDOUT_PERCENT"
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
            type=PROCESSING_NUMBER_INTEGER, defaultValue=10000, minValue=4,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_MATRIX_ELEMENTS,
            self.tr("Safety limit: Jacobian elements (observations × sources)"),
            type=PROCESSING_NUMBER_INTEGER, defaultValue=25000000, minValue=16,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.HOLDOUT_PERCENT,
            self.tr("Spatial holdout validation (%; 0 = disabled)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=10.0, minValue=0.0,
            maxValue=50.0,
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
        if block_size == 0.0:
            estimated_sources = cells
        else:
            source_columns = max(
                1, int(np.ceil(np.ptp(easting) / block_size)) + 1
            )
            source_rows = max(
                1, int(np.ceil(np.ptp(northing) / block_size)) + 1
            )
            estimated_sources = min(cells, source_columns * source_rows)
        matrix_elements = cells * estimated_sources
        matrix_limit = self.parameterAsInt(
            parameters, self.MAX_MATRIX_ELEMENTS, context
        )
        if matrix_elements > matrix_limit:
            gibibytes = matrix_elements * 8.0 / (1024.0**3)
            raise QgsProcessingException(
                f"Estimated Jacobian has {matrix_elements:,} elements "
                f"(~{gibibytes:.2f} GiB before working copies), exceeding the "
                f"{matrix_limit:,}-element guard. Increase source block size or "
                "resample the grid."
            )
        harmonica = import_harmonica()
        depth = self.parameterAsDouble(parameters, self.SOURCE_DEPTH, context)

        def new_model():
            return harmonica.EquivalentSources(
                damping=None if damping == 0.0 else damping,
                depth=depth,
                block_size=None if block_size == 0.0 else block_size,
                parallel=True,
            )

        observations = np.asarray(data.values, dtype=float).ravel()
        holdout_percent = self.parameterAsDouble(
            parameters, self.HOLDOUT_PERCENT, context
        )
        if holdout_percent > 0.0:
            random = np.random.default_rng(0)
            holdout_count = max(1, int(round(cells * holdout_percent / 100.0)))
            holdout = np.sort(random.choice(cells, holdout_count, replace=False))
            training = np.ones(cells, dtype=bool)
            training[holdout] = False
            if int(training.sum()) < 4:
                raise QgsProcessingException(
                    "Holdout validation leaves fewer than four training cells."
                )
            validation_model = new_model()
            validation_model.fit(
                tuple(component[training] for component in coordinates),
                observations[training],
            )
            validation_prediction = validation_model.predict(
                tuple(component[holdout] for component in coordinates)
            )
            residual = observations[holdout] - validation_prediction
            holdout_rmse = float(np.sqrt(np.mean(residual**2)))
            holdout_scale = float(np.std(observations[holdout]))
            holdout_nrmse = (
                holdout_rmse / holdout_scale if holdout_scale > 0.0 else None
            )
            feedback.pushInfo(
                f"Deterministic holdout ({holdout_count:,} cells): RMSE="
                f"{holdout_rmse:.6g}; normalized RMSE="
                f"{holdout_nrmse:.6g}." if holdout_nrmse is not None else
                f"Deterministic holdout ({holdout_count:,} cells): RMSE="
                f"{holdout_rmse:.6g}; normalized RMSE unavailable (zero variance)."
            )
            grid.metadata = dict(grid.metadata)
            grid.metadata.update(
                {
                    "TW_EQS_HOLDOUT_PERCENT": str(holdout_percent),
                    "TW_EQS_HOLDOUT_RMSE": str(holdout_rmse),
                    "TW_EQS_HOLDOUT_NRMSE": ""
                    if holdout_nrmse is None
                    else str(holdout_nrmse),
                }
            )
        model = new_model()
        feedback.pushInfo(
            f"Fitting {cells:,} observations with approximately "
            f"{estimated_sources:,} equivalent sources."
        )
        model.fit(coordinates, observations)
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

"""Bouguer plate correction algorithm."""

import numpy as np
from qgis.core import QgsProcessingParameterNumber

from .base import RasterAlgorithmBase
from ..dependencies import import_harmonica
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE
from ..raster_io import nodata_mask, write_geotiff


class BouguerCorrectionAlgorithm(RasterAlgorithmBase):
    """Calculate the gravitational effect of topography in mGal."""

    DENSITY_CRUST = "DENSITY_CRUST"
    DENSITY_WATER = "DENSITY_WATER"

    def name(self):
        return "bouguer_correction"

    def displayName(self):
        return self.tr("Bouguer correction")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DENSITY_CRUST,
                self.tr("Crust density (kg/m³)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=2670.0,
                minValue=1.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DENSITY_WATER,
                self.tr("Water density (kg/m³)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=1040.0,
                minValue=0.0,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context)
        density_crust = self.parameterAsDouble(parameters, self.DENSITY_CRUST, context)
        density_water = self.parameterAsDouble(parameters, self.DENSITY_WATER, context)
        output = self.output_path(parameters, context)
        mask = nodata_mask(grid)

        feedback.setProgress(15)
        harmonica = import_harmonica()
        values = np.asarray(
            harmonica.bouguer_correction(
                grid.values,
                density_crust=density_crust,
                density_water=density_water,
            ),
            dtype=np.float64,
        )
        output_nodata = grid.nodata if grid.nodata is not None else -99999.0
        values[mask] = output_nodata
        feedback.setProgress(80)
        write_geotiff(output, values, grid, "Bouguer correction (mGal)", output_nodata)
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr(
            "Calculates the gravitational effect of topography using the infinite "
            "Bouguer plate approximation implemented by Harmonica. Input heights "
            "must be geometric heights in metres; output units are mGal."
        )

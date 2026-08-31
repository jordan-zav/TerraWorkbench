"""Directional microleveling of already leveled magnetic grids."""

import numpy as np
from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
)

from .base import RasterAlgorithmBase
from ..microlevel import microlevel_grid
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE
from ..raster_io import nodata_mask, write_geotiff


class MicrolevelingAlgorithm(RasterAlgorithmBase):
    processing_domain = "FFT / DIRECTIONAL DECORRUGATION"
    AZIMUTH = "AZIMUTH"
    ACROSS_WAVELENGTH = "ACROSS_WAVELENGTH"
    ALONG_WAVELENGTH = "ALONG_WAVELENGTH"
    CORRECTION = "CORRECTION"

    def name(self):
        return "microlevel_grid"

    def displayName(self):
        return self.tr("Directional microleveling")

    def group(self):
        return self.tr("Survey data preparation")

    def groupId(self):
        return "survey_data_preparation"

    def initAlgorithm(self, config=None):
        del config
        self.add_raster_parameters()
        self.addParameter(
            QgsProcessingParameterNumber(
                self.AZIMUTH,
                self.tr("Traverse-line azimuth (degrees clockwise from grid north)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.0,
                minValue=0.0,
                maxValue=360.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ACROSS_WAVELENGTH,
                self.tr("Maximum across-line wavelength to remove"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=1000.0,
                minValue=0.001,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ALONG_WAVELENGTH,
                self.tr("Minimum along-line wavelength retained in correction"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=5000.0,
                minValue=0.001,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.CORRECTION, self.tr("Estimated corrugation grid")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context, require_projected=True)
        if nodata_mask(grid).any():
            raise QgsProcessingException(
                "Microleveling requires a complete grid. Fill gaps or use a survey footprint crop first."
            )
        try:
            corrected, correction = microlevel_grid(
                grid.values,
                grid.geotransform[1],
                grid.geotransform[5],
                self.parameterAsDouble(parameters, self.AZIMUTH, context),
                self.parameterAsDouble(parameters, self.ACROSS_WAVELENGTH, context),
                self.parameterAsDouble(parameters, self.ALONG_WAVELENGTH, context),
            )
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        output = self.output_path(parameters, context)
        correction_path = self.parameterAsOutputLayer(
            parameters, self.CORRECTION, context
        )
        write_geotiff(output, corrected, grid, "Microleveled field")
        write_geotiff(
            correction_path, correction, grid, "Estimated microlevel correction"
        )
        feedback.pushInfo(
            f"Correction RMS: {float(np.sqrt(np.mean(correction**2))):.4g} field units."
        )
        return {self.OUTPUT: output, self.CORRECTION: correction_path}

    def shortHelpString(self):
        return self.tr(
            "Minty-style directional frequency separation for residual line corrugation after crossover leveling. It removes short across-line wavelengths that remain long along the traverse direction. Inspect the correction grid and keep its geological amplitude small; this is not a substitute for lag, diurnal, heading or tie-line corrections."
        )

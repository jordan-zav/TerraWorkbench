"""Exploration-oriented gravity raster filters."""

import numpy as np
from qgis.core import QgsProcessingParameterNumber

from .transforms import HarmonicaTransformBase
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE


def _components(harmonica, data):
    return (
        harmonica.derivative_easting(data, order=1),
        harmonica.derivative_northing(data, order=1),
        harmonica.derivative_upward(data, order=1),
    )


def _like(data, values):
    return data.copy(data=np.asarray(values, dtype=np.float64))


class GravityFilterBase(HarmonicaTransformBase):
    """Common metadata for gravity exploration filters."""
    processing_domain = "MIXED GRID / FFT"

    def group(self):
        return self.tr("GRAV exploration filters")

    def groupId(self):
        return "grav_exploration_filters"

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()

    def shortHelpString(self):
        return self.tr(
            "Gravity exploration filter for complete, evenly spaced rasters in a "
            "projected CRS. Supports QGIS batch processing and Model Designer. "
            "Derivatives follow Harmonica's positive-upward vertical convention."
        )


class GravDxAlgorithm(GravityFilterBase):
    output_description = "Gravity DX first horizontal derivative in easting"
    processing_domain = "SPATIAL / FINITE DIFFERENCE"

    def name(self):
        return "grav_dx"

    def displayName(self):
        return self.tr("01 [SPATIAL] DX — First horizontal derivative X")

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.derivative_easting(data, order=1)


class GravDyAlgorithm(GravityFilterBase):
    output_description = "Gravity DY first horizontal derivative in northing"
    processing_domain = "SPATIAL / FINITE DIFFERENCE"

    def name(self):
        return "grav_dy"

    def displayName(self):
        return self.tr("02 [SPATIAL] DY — First horizontal derivative Y")

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.derivative_northing(data, order=1)


class GravDzAlgorithm(GravityFilterBase):
    output_description = "Gravity DZ first upward derivative"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "grav_dz"

    def displayName(self):
        return self.tr("03 [FFT] DZ — First vertical derivative")

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.derivative_upward(data, order=1)


class GravDz2Algorithm(GravityFilterBase):
    output_description = "Gravity DZ2 second upward derivative"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "grav_dz2"

    def displayName(self):
        return self.tr("04 [FFT] DZ2 — Second vertical derivative")

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.derivative_upward(data, order=2)


class GravityUpwardContinuationAlgorithm(GravityFilterBase):
    HEIGHT = "HEIGHT"
    output_description = "Gravity upward continuation"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "grav_upward_continuation"

    def displayName(self):
        return self.tr("05 [FFT] UC — Upward continuation (configurable)")

    def initAlgorithm(self, config=None):
        super().initAlgorithm(config)
        self.addParameter(
            QgsProcessingParameterNumber(
                self.HEIGHT,
                self.tr("Upward-continuation distance (CRS units)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=500.0,
                minValue=0.000001,
            )
        )

    def calculate(self, harmonica, data, parameters, context):
        height = self.parameterAsDouble(parameters, self.HEIGHT, context)
        return harmonica.upward_continuation(data, height_displacement=height)


class GravGaussianRegionalAlgorithm(GravityFilterBase):
    WAVELENGTH = "WAVELENGTH"
    output_description = "Gravity Gaussian regional field"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "grav_regional"

    def displayName(self):
        return self.tr("06 [FFT] Regional — Gaussian low-pass")

    def initAlgorithm(self, config=None):
        super().initAlgorithm(config)
        self.addParameter(
            QgsProcessingParameterNumber(
                self.WAVELENGTH,
                self.tr("Cutoff wavelength (CRS units)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=5000.0,
                minValue=0.000001,
            )
        )

    def calculate(self, harmonica, data, parameters, context):
        wavelength = self.parameterAsDouble(parameters, self.WAVELENGTH, context)
        return harmonica.gaussian_lowpass(data, wavelength=wavelength)


class GravResidualAlgorithm(GravityFilterBase):
    HEIGHT = "HEIGHT"
    output_description = "Gravity residual field"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "grav_residual"

    def displayName(self):
        return self.tr("07 [FFT] Residual — Field minus upward continuation")

    def initAlgorithm(self, config=None):
        super().initAlgorithm(config)
        self.addParameter(
            QgsProcessingParameterNumber(
                self.HEIGHT,
                self.tr("Upward-continuation distance (CRS units)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=500.0,
                minValue=0.000001,
            )
        )

    def calculate(self, harmonica, data, parameters, context):
        height = self.parameterAsDouble(parameters, self.HEIGHT, context)
        regional = harmonica.upward_continuation(data, height_displacement=height)
        return data - regional


class GravThdrAlgorithm(GravityFilterBase):
    output_description = "Gravity THDR total horizontal derivative"
    processing_domain = "SPATIAL / FINITE DIFFERENCE"

    def name(self):
        return "grav_thdr"

    def displayName(self):
        return self.tr("08 [SPATIAL] THDR — Total horizontal derivative")

    def calculate(self, harmonica, data, parameters, context):
        dx = harmonica.derivative_easting(data, order=1)
        dy = harmonica.derivative_northing(data, order=1)
        return _like(data, np.hypot(dx.values, dy.values))


class GravTiltAlgorithm(GravityFilterBase):
    output_description = "Gravity tilt angle in degrees"

    def name(self):
        return "grav_tilt"

    def displayName(self):
        return self.tr("09 [MIXED] Tilt — Tilt angle")

    def calculate(self, harmonica, data, parameters, context):
        dx, dy, dz = _components(harmonica, data)
        thdr = np.hypot(dx.values, dy.values)
        return _like(data, np.degrees(np.arctan2(dz.values, thdr)))


class GravTotalGradientAmplitudeAlgorithm(GravityFilterBase):
    output_description = "Gravity total gradient amplitude"

    def name(self):
        return "grav_tga"

    def displayName(self):
        return self.tr("10 [MIXED] TGA — Total gradient amplitude")

    def calculate(self, harmonica, data, parameters, context):
        dx, dy, dz = _components(harmonica, data)
        amplitude = np.sqrt(dx.values**2 + dy.values**2 + dz.values**2)
        return _like(data, amplitude)

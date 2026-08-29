"""Exploration-oriented magnetic raster filters."""

import numpy as np
from qgis.core import QgsProcessingParameterNumber

from .transforms import HarmonicaTransformBase
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE


def _components(harmonica, data):
    """Return first derivatives in easting, northing and upward directions."""
    return (
        harmonica.derivative_easting(data, order=1),
        harmonica.derivative_northing(data, order=1),
        harmonica.derivative_upward(data, order=1),
    )


def _like(data, values):
    """Return computed values with the source xarray coordinates."""
    return data.copy(data=np.asarray(values, dtype=np.float64))


class MagneticFilterBase(HarmonicaTransformBase):
    """Common metadata for the twelve MAG exploration filters."""
    processing_domain = "MIXED GRID / FFT"

    def group(self):
        return self.tr("MAG exploration filters")

    def groupId(self):
        return "mag_exploration_filters"

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()

    def shortHelpString(self):
        return self.tr(
            "Magnetic exploration filter for complete, evenly spaced rasters in a "
            "projected CRS. Supports QGIS batch processing and Model Designer. "
            "Derivatives follow Harmonica's positive-upward vertical convention."
        )


class DxAlgorithm(MagneticFilterBase):
    output_description = "DX first horizontal derivative in easting"
    processing_domain = "SPATIAL / FINITE DIFFERENCE"

    def name(self):
        return "mag_dx"

    def displayName(self):
        return self.tr("01 [SPATIAL] DX — First horizontal derivative X")

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.derivative_easting(data, order=1)


class DyAlgorithm(MagneticFilterBase):
    output_description = "DY first horizontal derivative in northing"
    processing_domain = "SPATIAL / FINITE DIFFERENCE"

    def name(self):
        return "mag_dy"

    def displayName(self):
        return self.tr("02 [SPATIAL] DY — First horizontal derivative Y")

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.derivative_northing(data, order=1)


class DzAlgorithm(MagneticFilterBase):
    output_description = "DZ first upward derivative"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "mag_dz"

    def displayName(self):
        return self.tr("03 [FFT] DZ — First vertical derivative")

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.derivative_upward(data, order=1)


class Dz2Algorithm(MagneticFilterBase):
    output_description = "DZ2 second upward derivative"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "mag_dz2"

    def displayName(self):
        return self.tr("04 [FFT] DZ2 — Second vertical derivative")

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.derivative_upward(data, order=2)


class MagneticUpwardContinuationAlgorithm(MagneticFilterBase):
    HEIGHT = "HEIGHT"
    output_description = "Magnetic upward continuation"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "mag_upward_continuation"

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


class ResidualEnhancementAlgorithm(MagneticFilterBase):
    HEIGHT = "HEIGHT"
    output_description = "RS residual enhancement"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "mag_rs"

    def displayName(self):
        return self.tr("06 [FFT] RS — Residual enhancement")

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


class ThdrAlgorithm(MagneticFilterBase):
    output_description = "THDR total horizontal derivative"
    processing_domain = "SPATIAL / FINITE DIFFERENCE"

    def name(self):
        return "mag_thdr"

    def displayName(self):
        return self.tr("07 [SPATIAL] THDR — Total horizontal derivative")

    def calculate(self, harmonica, data, parameters, context):
        dx = harmonica.derivative_easting(data, order=1)
        dy = harmonica.derivative_northing(data, order=1)
        return _like(data, np.hypot(dx.values, dy.values))


class TiltAlgorithm(MagneticFilterBase):
    output_description = "Tilt angle in degrees"

    def name(self):
        return "mag_tilt"

    def displayName(self):
        return self.tr("08 [MIXED] Tilt — Tilt angle")

    def calculate(self, harmonica, data, parameters, context):
        dx, dy, dz = _components(harmonica, data)
        thdr = np.hypot(dx.values, dy.values)
        return _like(data, np.degrees(np.arctan2(dz.values, thdr)))


class DirectionalHorizontalGradientAlgorithm(MagneticFilterBase):
    AZIMUTH = "AZIMUTH"
    output_description = "Directional horizontal gradient"
    processing_domain = "SPATIAL / FINITE DIFFERENCE"

    def name(self):
        return "mag_directional_horizontal_gradient"

    def displayName(self):
        return self.tr("09 [SPATIAL] HG — Directional horizontal gradient")

    def initAlgorithm(self, config=None):
        super().initAlgorithm(config)
        self.addParameter(
            QgsProcessingParameterNumber(
                self.AZIMUTH,
                self.tr("Azimuth clockwise from North (degrees)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=45.0,
                minValue=0.0,
                maxValue=360.0,
            )
        )

    def calculate(self, harmonica, data, parameters, context):
        dx = harmonica.derivative_easting(data, order=1)
        dy = harmonica.derivative_northing(data, order=1)
        azimuth = np.deg2rad(self.parameterAsDouble(parameters, self.AZIMUTH, context))
        gradient = np.sin(azimuth) * dx.values + np.cos(azimuth) * dy.values
        return _like(data, gradient)


class AnalyticSignalAlgorithm(MagneticFilterBase):
    output_description = "AS analytic signal amplitude"

    def name(self):
        return "mag_as"

    def displayName(self):
        return self.tr("10 [MIXED] AS / ASA — Analytic signal amplitude")

    def calculate(self, harmonica, data, parameters, context):
        dx, dy, dz = _components(harmonica, data)
        amplitude = np.sqrt(dx.values**2 + dy.values**2 + dz.values**2)
        return _like(data, amplitude)


class TdxAlgorithm(MagneticFilterBase):
    output_description = "TDX horizontal tilt angle in degrees"

    def name(self):
        return "mag_tdx"

    def displayName(self):
        return self.tr("11 [MIXED] TDX — Horizontal tilt angle")

    def calculate(self, harmonica, data, parameters, context):
        dx, dy, dz = _components(harmonica, data)
        thdr = np.hypot(dx.values, dy.values)
        return _like(data, np.degrees(np.arctan2(thdr, np.abs(dz.values))))


class ThetaMapAlgorithm(MagneticFilterBase):
    output_description = "Theta map angle in degrees"

    def name(self):
        return "mag_theta"

    def displayName(self):
        return self.tr("12 [MIXED] Theta — Theta angle map")

    def calculate(self, harmonica, data, parameters, context):
        dx, dy, dz = _components(harmonica, data)
        thdr = np.hypot(dx.values, dy.values)
        amplitude = np.hypot(thdr, dz.values)
        ratio = np.zeros_like(amplitude)
        np.divide(thdr, amplitude, out=ratio, where=amplitude > 0.0)
        theta = np.degrees(np.arccos(np.clip(ratio, 0.0, 1.0)))
        theta[amplitude == 0.0] = 0.0
        return _like(data, theta)

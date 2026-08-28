"""Configurable two-dimensional Fourier-domain filters."""

from __future__ import annotations

import numpy as np
from qgis.core import QgsProcessingException, QgsProcessingParameterNumber

from .base import RasterAlgorithmBase
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER
from ..raster_io import restore_raster_order, to_regular_data_array, write_geotiff
from ..spectral import (
    apply_transfer,
    butterworth_bandpass,
    butterworth_highpass,
    butterworth_lowpass,
    cosine_rolloff_lowpass,
    directional_cosine,
    frequency_grid,
    ideal_bandpass,
    integration_transfer,
    stabilized_downward_continuation,
    vertical_integration_transfer,
)


class SpectralFilterBase(RasterAlgorithmBase):
    """Base class for explicitly defined FFT transfer functions."""

    output_description = "TerraWorkbench spectral result"

    def group(self):
        return self.tr("FFT spectral filters")

    def groupId(self):
        return "fft_spectral_filters"

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_filter_parameters()

    def add_filter_parameters(self):
        pass

    def transfer(self, k_east, k_north, radial, parameters, context):
        raise NotImplementedError

    def prepare(self, grid, parameters, context, feedback):
        del grid, parameters, context, feedback

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context, require_projected=True)
        orientation = to_regular_data_array(grid)
        self.prepare(grid, parameters, context, feedback)
        data = orientation.data
        northing = np.asarray(data.coords["northing"])
        easting = np.asarray(data.coords["easting"])
        spacing_northing = abs(float(northing[1] - northing[0]))
        spacing_easting = abs(float(easting[1] - easting[0]))
        feedback.setProgress(15)
        k_east, k_north, radial = frequency_grid(
            data.shape, spacing_northing, spacing_easting
        )
        try:
            response = self.transfer(k_east, k_north, radial, parameters, context)
        except (OverflowError, ValueError) as error:
            raise QgsProcessingException(str(error)) from error
        if not np.isfinite(response).all():
            raise QgsProcessingException(
                "The spectral transfer function is not finite."
            )
        feedback.setProgress(45)
        filtered = apply_transfer(data.values, response)
        values = restore_raster_order(filtered, orientation)
        feedback.setProgress(85)
        output = self.output_path(parameters, context)
        write_geotiff(output, values, grid, self.output_description)
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr(
            "Applies an explicit two-dimensional Fourier transfer function. Input "
            "must be a complete, evenly spaced raster in a projected CRS. Wavelengths "
            "and distances use the raster CRS units. Edge tapering is not automatic."
        )


class WavelengthOrderBase(SpectralFilterBase):
    WAVELENGTH = "WAVELENGTH"
    ORDER = "ORDER"

    def add_filter_parameters(self):
        self.addParameter(
            QgsProcessingParameterNumber(
                self.WAVELENGTH,
                self.tr("Cutoff wavelength (CRS units)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=1000.0,
                minValue=0.000001,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ORDER,
                self.tr("Filter order"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=8,
                minValue=1,
                maxValue=64,
            )
        )

    def values(self, parameters, context):
        return (
            self.parameterAsDouble(parameters, self.WAVELENGTH, context),
            self.parameterAsInt(parameters, self.ORDER, context),
        )


class ButterworthLowPassAlgorithm(WavelengthOrderBase):
    output_description = "Butterworth low-pass field"

    def name(self):
        return "butterworth_lowpass"

    def displayName(self):
        return self.tr("Butterworth low-pass")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return butterworth_lowpass(radial, *self.values(parameters, context))


class ButterworthHighPassAlgorithm(WavelengthOrderBase):
    output_description = "Butterworth high-pass field"

    def name(self):
        return "butterworth_highpass"

    def displayName(self):
        return self.tr("Butterworth high-pass")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return butterworth_highpass(radial, *self.values(parameters, context))


class WavelengthBandBase(SpectralFilterBase):
    LONG_WAVELENGTH = "LONG_WAVELENGTH"
    SHORT_WAVELENGTH = "SHORT_WAVELENGTH"

    def add_band_parameters(self):
        self.addParameter(
            QgsProcessingParameterNumber(
                self.LONG_WAVELENGTH,
                self.tr("Long wavelength cutoff (CRS units)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=5000.0,
                minValue=0.000001,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SHORT_WAVELENGTH,
                self.tr("Short wavelength cutoff (CRS units)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=1000.0,
                minValue=0.000001,
            )
        )

    def band_values(self, parameters, context):
        return (
            self.parameterAsDouble(parameters, self.LONG_WAVELENGTH, context),
            self.parameterAsDouble(parameters, self.SHORT_WAVELENGTH, context),
        )


class ButterworthBandBase(WavelengthBandBase):
    ORDER = "ORDER"

    def add_filter_parameters(self):
        self.add_band_parameters()
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ORDER,
                self.tr("Filter order"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=8,
                minValue=1,
                maxValue=64,
            )
        )

    def response(self, radial, parameters, context):
        return butterworth_bandpass(
            radial,
            *self.band_values(parameters, context),
            self.parameterAsInt(parameters, self.ORDER, context),
        )


class ButterworthBandPassAlgorithm(ButterworthBandBase):
    output_description = "Butterworth band-pass field"

    def name(self):
        return "butterworth_bandpass"

    def displayName(self):
        return self.tr("Butterworth band-pass")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return self.response(radial, parameters, context)


class ButterworthNotchAlgorithm(ButterworthBandBase):
    output_description = "Butterworth notch field"

    def name(self):
        return "butterworth_notch"

    def displayName(self):
        return self.tr("Butterworth notch (band reject)")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return 1.0 - self.response(radial, parameters, context)


class IdealBandBase(WavelengthBandBase):
    def add_filter_parameters(self):
        self.add_band_parameters()

    def response(self, radial, parameters, context):
        return ideal_bandpass(radial, *self.band_values(parameters, context))

    def shortHelpString(self):
        return super().shortHelpString() + self.tr(
            " The abrupt cutoff may produce Gibbs ringing; prefer Butterworth when possible."
        )


class IdealBandPassAlgorithm(IdealBandBase):
    output_description = "Ideal band-pass field"

    def name(self):
        return "ideal_bandpass"

    def displayName(self):
        return self.tr("Ideal band-pass")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return self.response(radial, parameters, context)


class IdealBandRejectAlgorithm(IdealBandBase):
    output_description = "Ideal band-reject field"

    def name(self):
        return "ideal_band_reject"

    def displayName(self):
        return self.tr("Ideal band reject")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return 1.0 - self.response(radial, parameters, context)


class CosineRolloffBase(WavelengthBandBase):
    DEGREE = "DEGREE"

    def add_filter_parameters(self):
        self.add_band_parameters()
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DEGREE,
                self.tr("Cosine degree"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=2,
                minValue=1,
                maxValue=64,
            )
        )

    def response(self, radial, parameters, context):
        return cosine_rolloff_lowpass(
            radial,
            *self.band_values(parameters, context),
            self.parameterAsInt(parameters, self.DEGREE, context),
        )


class CosineRolloffLowPassAlgorithm(CosineRolloffBase):
    output_description = "Cosine roll-off low-pass field"

    def name(self):
        return "cosine_rolloff_lowpass"

    def displayName(self):
        return self.tr("Cosine roll-off low-pass")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return self.response(radial, parameters, context)


class CosineRolloffHighPassAlgorithm(CosineRolloffBase):
    output_description = "Cosine roll-off high-pass field"

    def name(self):
        return "cosine_rolloff_highpass"

    def displayName(self):
        return self.tr("Cosine roll-off high-pass")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return 1.0 - self.response(radial, parameters, context)


class DirectionalCosineBase(SpectralFilterBase):
    AZIMUTH = "AZIMUTH"
    DEGREE = "DEGREE"

    def add_filter_parameters(self):
        self.addParameter(
            QgsProcessingParameterNumber(
                self.AZIMUTH,
                self.tr("Geological strike azimuth, clockwise from North (degrees)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=45.0,
                minValue=0.0,
                maxValue=180.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DEGREE,
                self.tr("Cosine degree"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=2,
                minValue=1,
                maxValue=64,
            )
        )

    def response(self, k_east, k_north, parameters, context):
        return directional_cosine(
            k_east,
            k_north,
            self.parameterAsDouble(parameters, self.AZIMUTH, context),
            self.parameterAsInt(parameters, self.DEGREE, context),
        )


class DirectionalCosinePassAlgorithm(DirectionalCosineBase):
    output_description = "Directional cosine pass field"

    def name(self):
        return "directional_cosine_pass"

    def displayName(self):
        return self.tr("Directional cosine — pass")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return self.response(k_east, k_north, parameters, context)


class DirectionalCosineRejectAlgorithm(DirectionalCosineBase):
    output_description = "Directional cosine reject field"

    def name(self):
        return "directional_cosine_reject"

    def displayName(self):
        return self.tr("Directional cosine — reject")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return 1.0 - self.response(k_east, k_north, parameters, context)


class DownwardContinuationAlgorithm(SpectralFilterBase):
    HEIGHT = "HEIGHT"
    LOWPASS_WAVELENGTH = "LOWPASS_WAVELENGTH"
    ORDER = "ORDER"
    MAX_GAIN = "MAX_GAIN"
    output_description = "Stabilized downward-continued field"

    def name(self):
        return "downward_continuation"

    def displayName(self):
        return self.tr("Downward continuation — stabilized")

    def add_filter_parameters(self):
        for name, description, default, minimum in (
            (
                self.HEIGHT,
                "Downward-continuation distance (CRS units)",
                500.0,
                0.000001,
            ),
            (
                self.LOWPASS_WAVELENGTH,
                "Butterworth low-pass wavelength (CRS units)",
                750.0,
                0.000001,
            ),
            (self.MAX_GAIN, "Maximum spectral gain", 100.0, 1.000001),
        ):
            self.addParameter(
                QgsProcessingParameterNumber(
                    name,
                    self.tr(description),
                    type=PROCESSING_NUMBER_DOUBLE,
                    defaultValue=default,
                    minValue=minimum,
                )
            )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ORDER,
                self.tr("Butterworth order"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=8,
                minValue=1,
                maxValue=64,
            )
        )

    def transfer(self, k_east, k_north, radial, parameters, context):
        return stabilized_downward_continuation(
            radial,
            self.parameterAsDouble(parameters, self.HEIGHT, context),
            self.parameterAsDouble(parameters, self.LOWPASS_WAVELENGTH, context),
            self.parameterAsInt(parameters, self.ORDER, context),
            self.parameterAsDouble(parameters, self.MAX_GAIN, context),
        )

    def shortHelpString(self):
        return super().shortHelpString() + self.tr(
            " Downward continuation is inherently unstable and must not cross a "
            "potential-field source. This implementation applies a Butterworth "
            "low-pass taper and an explicit maximum-gain cap."
        )


class HorizontalIntegrationEastingAlgorithm(SpectralFilterBase):
    output_description = "Horizontal integration in easting"

    def name(self):
        return "horizontal_integration_easting"

    def displayName(self):
        return self.tr("Horizontal integration — easting")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return integration_transfer(k_east, radial)


class HorizontalIntegrationNorthingAlgorithm(SpectralFilterBase):
    output_description = "Horizontal integration in northing"

    def name(self):
        return "horizontal_integration_northing"

    def displayName(self):
        return self.tr("Horizontal integration — northing")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return integration_transfer(k_north, radial)


class VerticalIntegrationAlgorithm(SpectralFilterBase):
    output_description = "Vertical integration"

    def name(self):
        return "vertical_integration"

    def displayName(self):
        return self.tr("Vertical integration")

    def transfer(self, k_east, k_north, radial, parameters, context):
        return vertical_integration_transfer(radial)

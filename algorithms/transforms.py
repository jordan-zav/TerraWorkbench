"""FFT grid transformations backed by Harmonica."""

from qgis.core import QgsProcessingParameterNumber

from .base import RasterAlgorithmBase
from ..dependencies import import_harmonica
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER
from ..raster_io import (
    restore_raster_order,
    to_regular_data_array,
    write_geotiff,
)


class HarmonicaTransformBase(RasterAlgorithmBase):
    """Base class for complete regular-grid transformations."""

    output_description = "TerraWorkbench result"
    processing_domain = "GRID TRANSFORM"

    def calculate(self, harmonica, data, parameters, context):
        raise NotImplementedError

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context, require_projected=True)
        feedback.setProgress(10)
        orientation = to_regular_data_array(grid)
        harmonica = import_harmonica()
        feedback.setProgress(25)
        result = self.calculate(harmonica, orientation.data, parameters, context)
        values = restore_raster_order(result.values, orientation)
        feedback.setProgress(85)
        output = self.output_path(parameters, context)
        write_geotiff(output, values, grid, self.output_description)
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr(
            "Runs a Harmonica transformation on a complete, evenly spaced raster. "
            "The raster must use a projected CRS and must not contain NoData cells. "
            "The tool is available in QGIS batch processing and the Model Designer."
        )


class UpwardContinuationAlgorithm(HarmonicaTransformBase):
    HEIGHT = "HEIGHT"
    output_description = "Upward continued field"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "upward_continuation"

    def displayName(self):
        return self.tr("Upward continuation")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(
            QgsProcessingParameterNumber(
                self.HEIGHT,
                self.tr("Height displacement (CRS units)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=100.0,
                minValue=0.000001,
            )
        )

    def calculate(self, harmonica, data, parameters, context):
        height = self.parameterAsDouble(parameters, self.HEIGHT, context)
        return harmonica.upward_continuation(data, height_displacement=height)


class GaussianFilterBase(HarmonicaTransformBase):
    WAVELENGTH = "WAVELENGTH"

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(
            QgsProcessingParameterNumber(
                self.WAVELENGTH,
                self.tr("Cutoff wavelength (CRS units)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=1000.0,
                minValue=0.000001,
            )
        )

    def wavelength(self, parameters, context):
        return self.parameterAsDouble(parameters, self.WAVELENGTH, context)


class GaussianLowPassAlgorithm(GaussianFilterBase):
    output_description = "Gaussian low-pass field"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "gaussian_lowpass"

    def displayName(self):
        return self.tr("Gaussian low-pass filter")

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.gaussian_lowpass(
            data, wavelength=self.wavelength(parameters, context)
        )


class GaussianHighPassAlgorithm(GaussianFilterBase):
    output_description = "Gaussian high-pass field"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "gaussian_highpass"

    def displayName(self):
        return self.tr("Gaussian high-pass filter")

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.gaussian_highpass(
            data, wavelength=self.wavelength(parameters, context)
        )


class ReductionToPoleAlgorithm(HarmonicaTransformBase):
    INCLINATION = "INCLINATION"
    DECLINATION = "DECLINATION"
    MAGNETIZATION_INCLINATION = "MAGNETIZATION_INCLINATION"
    MAGNETIZATION_DECLINATION = "MAGNETIZATION_DECLINATION"
    output_description = "Magnetic anomaly reduced to the pole"
    processing_domain = "FFT / HARMONICA RTP"

    def name(self):
        return "reduction_to_pole"

    def displayName(self):
        return self.tr("RTP — manual Harmonica")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(
            QgsProcessingParameterNumber(
                self.INCLINATION,
                self.tr("Geomagnetic inclination (degrees)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=-20.0,
                minValue=-90.0,
                maxValue=90.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DECLINATION,
                self.tr("Geomagnetic declination (degrees)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.0,
                minValue=-360.0,
                maxValue=360.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAGNETIZATION_INCLINATION,
                self.tr("Magnetization inclination (optional)"),
                type=PROCESSING_NUMBER_DOUBLE,
                optional=True,
                minValue=-90.0,
                maxValue=90.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAGNETIZATION_DECLINATION,
                self.tr("Magnetization declination (optional)"),
                type=PROCESSING_NUMBER_DOUBLE,
                optional=True,
                minValue=-360.0,
                maxValue=360.0,
            )
        )

    def _optional_double(self, parameters, key, context):
        value = parameters.get(key)
        if value is None or value == "":
            return None
        return self.parameterAsDouble(parameters, key, context)

    def calculate(self, harmonica, data, parameters, context):
        return harmonica.reduction_to_pole(
            data,
            inclination=self.parameterAsDouble(parameters, self.INCLINATION, context),
            declination=self.parameterAsDouble(parameters, self.DECLINATION, context),
            magnetization_inclination=self._optional_double(
                parameters, self.MAGNETIZATION_INCLINATION, context
            ),
            magnetization_declination=self._optional_double(
                parameters, self.MAGNETIZATION_DECLINATION, context
            ),
        )


class DerivativeBase(HarmonicaTransformBase):
    ORDER = "ORDER"
    derivative_function = None

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ORDER,
                self.tr("Derivative order"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=1,
                minValue=1,
                maxValue=5,
            )
        )

    def calculate(self, harmonica, data, parameters, context):
        function = getattr(harmonica, self.derivative_function)
        order = self.parameterAsInt(parameters, self.ORDER, context)
        return function(data, order=order)


class DerivativeEastingAlgorithm(DerivativeBase):
    derivative_function = "derivative_easting"
    output_description = "Easting derivative"
    processing_domain = "SPATIAL / FINITE DIFFERENCE"

    def name(self):
        return "derivative_easting"

    def displayName(self):
        return self.tr("Derivative — easting (spatial finite difference)")


class DerivativeNorthingAlgorithm(DerivativeBase):
    derivative_function = "derivative_northing"
    output_description = "Northing derivative"
    processing_domain = "SPATIAL / FINITE DIFFERENCE"

    def name(self):
        return "derivative_northing"

    def displayName(self):
        return self.tr("Derivative — northing (spatial finite difference)")


class DerivativeUpwardAlgorithm(DerivativeBase):
    derivative_function = "derivative_upward"
    output_description = "Upward derivative"
    processing_domain = "FFT / HARMONICA"

    def name(self):
        return "derivative_upward"

    def displayName(self):
        return self.tr("Derivative — upward (FFT)")

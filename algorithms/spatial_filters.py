"""Mask-preserving spatial filters with explicit, independent definitions."""

import numpy as np
from qgis.core import QgsProcessingException, QgsProcessingParameterNumber

from .base import RasterAlgorithmBase
from ..basic_processing import smooth_nine_point, automatic_gain_control, circular_median
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER
from ..raster_io import nodata_mask, write_geotiff


class SpatialFilterBase(RasterAlgorithmBase):
    processing_domain = "SPACE / GRID"
    numerical_backend = "NumPy + SciPy ndimage"
    implementation_details = (
        ("Numerical backend", "TerraWorkbench definitions using NumPy and SciPy ndimage"),
        ("Host and raster I/O", "QGIS Processing and GDAL"),
        ("Compatibility", "Independent definitions; numerical equivalence to proprietary filters is not claimed"),
    )

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context)
        values = np.where(nodata_mask(grid), np.nan, grid.values)
        if feedback.isCanceled():
            return {}
        try:
            result, settings = self.calculate(values, parameters, context, feedback)
        except InterruptedError:
            return {}
        except (ValueError, ImportError) as error:
            raise QgsProcessingException(str(error)) from error
        if feedback.isCanceled():
            return {}
        import scipy
        grid.metadata = dict(grid.metadata, TW_PROCESS=self.name(), TW_PARAMETERS=settings,
                             TW_BACKEND=self.numerical_backend + "; NumPy " + np.__version__ + "; SciPy " + scipy.__version__,
                             TW_NODATA="Original footprint preserved")
        output = self.output_path(parameters, context)
        write_geotiff(output, result, grid, self.displayName(), output_nodata=np.nan)
        return {self.OUTPUT: output}


class NinePointSmoothingAlgorithm(SpatialFilterBase):
    def name(self):
        return "smooth_nine_point"

    def displayName(self):
        return self.tr("Nine-point binomial smoothing")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(QgsProcessingParameterNumber("PASSES", self.tr("Smoothing passes"),
                          type=PROCESSING_NUMBER_INTEGER, defaultValue=1, minValue=1, maxValue=100))

    def calculate(self, values, parameters, context, feedback):
        passes = self.parameterAsInt(parameters, "PASSES", context)
        return smooth_nine_point(values, passes, feedback.isCanceled), f"kernel=1,2,1;2,4,2;1,2,1; passes={passes}; valid-weight normalization"

    def shortHelpString(self):
        return self.tr("Applies a normalized 3x3 binomial kernel. Missing cells and outside edges have zero weight; original NoData cells remain missing. Each pass uses the previous result. Independent definition, not a certified equivalent of proprietary nine-point filters.")


class CircularMedianAlgorithm(SpatialFilterBase):
    numerical_backend = "NumPy nanmedian"
    implementation_details = (
        ("Numerical backend", "NumPy nanmedian with a discrete disk footprint and bounded work arrays"),
        ("Host and raster I/O", "QGIS Processing and GDAL"),
        ("Compatibility", "Independent definitions; numerical equivalence to proprietary filters is not claimed"),
    )

    def name(self):
        return "circular_median"

    def displayName(self):
        return self.tr("Circular median (2D disk)")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(QgsProcessingParameterNumber("RADIUS", self.tr("Disk radius (pixels)"),
                          type=PROCESSING_NUMBER_INTEGER, defaultValue=1, minValue=1, maxValue=50))

    def calculate(self, values, parameters, context, feedback):
        radius = self.parameterAsInt(parameters, "RADIUS", context)
        return circular_median(values, radius, feedback.isCanceled), f"radius_px={radius}; dx^2+dy^2<=radius^2; finite-neighbor median; NumPy {np.__version__}"

    def shortHelpString(self):
        return self.tr("Nonlinear spatial median inside a circular pixel footprint. Radius 1 uses the center and four axial neighbors, not a square 3x3 window. NoData and outside neighbors are ignored; original missing cells stay missing. Radius is in pixels: unequal pixel dimensions produce an ellipse in map units. This is not an angular-data median or a Fourier filter.")


class AutomaticGainControlAlgorithm(SpatialFilterBase):
    def name(self):
        return "automatic_gain_control"

    def displayName(self):
        return self.tr("Automatic gain control (local RMS)")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        for key, title, default, low, high, kind in (
            ("WINDOW", "AGC window (odd number of pixels)", 11, 3, 1001, PROCESSING_NUMBER_INTEGER),
            ("FLOOR", "RMS floor fraction", .05, .000001, 1, PROCESSING_NUMBER_DOUBLE),
            ("MAX_GAIN", "Maximum gain", 10, 1, 1000, PROCESSING_NUMBER_DOUBLE),
        ):
            self.addParameter(QgsProcessingParameterNumber(key, self.tr(title), type=kind,
                              defaultValue=default, minValue=low, maxValue=high))

    def calculate(self, values, parameters, context, feedback):
        window = self.parameterAsInt(parameters, "WINDOW", context)
        floor = self.parameterAsDouble(parameters, "FLOOR", context)
        cap = self.parameterAsDouble(parameters, "MAX_GAIN", context)
        return automatic_gain_control(values, window, floor, cap), f"window_px={window}; floor_fraction={floor}; max_gain={cap}; global_RMS/local_RMS"

    def shortHelpString(self):
        return self.tr("Scales the field by global RMS divided by local RMS in a square pixel window, with an RMS floor and gain cap. No mean subtraction; original NoData is preserved. This changes physical amplitudes: use for enhancement, not quantitative inversion. Independent definition, not a certified equivalent of proprietary AGC.")

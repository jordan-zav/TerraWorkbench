"""QGIS Processing algorithms for gamma-ray spectrometry."""

from __future__ import annotations

import json

import numpy as np
from osgeo import osr
from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterBand,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
)

from .base import RasterAlgorithmBase
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER
from ..radiometry import (
    alteration_f_parameter,
    background_correction,
    channel_qc,
    dead_time_correction,
    height_attenuation_correction,
    median_mad_despike,
    safe_ratio,
    sensitivity_calibration,
    spectral_unmix,
    terrestrial_dose_rate,
    ternary_rgb,
)
from ..raster_io import (
    nodata_mask,
    read_raster,
    write_geotiff,
    write_multiband_geotiff,
)


class RadiometryBase(RasterAlgorithmBase):
    """Shared grid validation and output handling."""

    processing_domain = "RADIOMETRY / GRID"

    def group(self):
        return self.tr("Gamma-ray spectrometry")

    def groupId(self):
        return "gamma_ray_spectrometry"

    def shortHelpString(self):
        return self.tr(
            "Processes gamma-ray spectrometry grids with explicit units and coefficients. "
            "All channel rasters must be co-registered. Products expect calibrated K (%), "
            "eU (ppm) and eTh (ppm), while raw-count corrections require calibration values "
            "from the survey report; TerraWorkbench never infers them silently."
        )

    def add_secondary_raster(self, name, band_name, label):
        self.addParameter(QgsProcessingParameterRasterLayer(name, self.tr(label)))
        self.addParameter(
            QgsProcessingParameterBand(
                band_name,
                f"{self.tr(label)} — {self.tr('Band')}",
                parentLayerParameterName=name,
                defaultValue=1,
            )
        )

    def secondary_grid(self, parameters, context, name, band_name, label):
        layer = self.parameterAsRasterLayer(parameters, name, context)
        if layer is None or not layer.isValid():
            raise QgsProcessingException(f"A valid {label} raster is required.")
        grid = read_raster(layer, self.parameterAsInt(parameters, band_name, context))
        return grid

    @staticmethod
    def require_matching(reference, *labelled_grids):
        for label, grid in labelled_grids:
            same_crs = reference.projection == grid.projection
            if reference.projection and grid.projection:
                source = osr.SpatialReference()
                target = osr.SpatialReference()
                same_crs = (
                    source.ImportFromWkt(reference.projection) == 0
                    and target.ImportFromWkt(grid.projection) == 0
                    and bool(source.IsSame(target))
                )
            if (
                reference.values.shape != grid.values.shape
                or not np.allclose(reference.geotransform, grid.geotransform, rtol=0.0, atol=1e-7)
                or not same_crs
            ):
                raise QgsProcessingException(
                    f"{label} must have the same extent, pixel grid and CRS as the K/input raster."
                )

    @staticmethod
    def values(grid):
        result = np.asarray(grid.values, dtype=np.float64).copy()
        result[nodata_mask(grid)] = np.nan
        return result

    @staticmethod
    def write(output, values, reference, description):
        result = np.asarray(values, dtype=np.float64).copy()
        result[~np.isfinite(result)] = -99999.0
        write_geotiff(output, result, reference, description, -99999.0)


class RadiometryRatioAlgorithm(RadiometryBase):
    DENOMINATOR = "DENOMINATOR"
    DENOMINATOR_BAND = "DENOMINATOR_BAND"
    MINIMUM = "MINIMUM_DENOMINATOR"

    def name(self):
        return "radiometry_ratio"

    def displayName(self):
        return self.tr("01 Radiometric ratio — configurable channels")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_secondary_raster(self.DENOMINATOR, self.DENOMINATOR_BAND, "Denominator raster")
        self.addParameter(QgsProcessingParameterNumber(
            self.MINIMUM, self.tr("Minimum absolute denominator"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0,
        ))

    def processAlgorithm(self, parameters, context, feedback):
        numerator = self.input_grid(parameters, context)
        denominator = self.secondary_grid(parameters, context, self.DENOMINATOR, self.DENOMINATOR_BAND, "denominator")
        self.require_matching(numerator, ("Denominator raster", denominator))
        result = safe_ratio(self.values(numerator), self.values(denominator), self.parameterAsDouble(parameters, self.MINIMUM, context))
        output = self.output_path(parameters, context)
        self.write(output, result, numerator, "Radiometric channel ratio")
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class RadiometryTernaryAlgorithm(RadiometryBase):
    URANIUM = "URANIUM"
    URANIUM_BAND = "URANIUM_BAND"
    THORIUM = "THORIUM"
    THORIUM_BAND = "THORIUM_BAND"
    LOWER = "LOWER_PERCENTILE"
    UPPER = "UPPER_PERCENTILE"
    NORMALIZE = "NORMALIZE"

    def name(self):
        return "radiometry_ternary"

    def displayName(self):
        return self.tr("02 Ternary image — K/eTh/eU")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_secondary_raster(self.URANIUM, self.URANIUM_BAND, "Equivalent uranium raster (ppm eU)")
        self.add_secondary_raster(self.THORIUM, self.THORIUM_BAND, "Equivalent thorium raster (ppm eTh)")
        self.addParameter(QgsProcessingParameterNumber(self.LOWER, self.tr("Lower stretch percentile"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=2.0, minValue=0.0, maxValue=99.0))
        self.addParameter(QgsProcessingParameterNumber(self.UPPER, self.tr("Upper stretch percentile"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=98.0, minValue=1.0, maxValue=100.0))
        self.addParameter(QgsProcessingParameterBoolean(self.NORMALIZE, self.tr("Normalize channel proportions"), defaultValue=False))

    def processAlgorithm(self, parameters, context, feedback):
        potassium = self.input_grid(parameters, context)
        uranium = self.secondary_grid(parameters, context, self.URANIUM, self.URANIUM_BAND, "equivalent uranium")
        thorium = self.secondary_grid(parameters, context, self.THORIUM, self.THORIUM_BAND, "equivalent thorium")
        self.require_matching(potassium, ("Equivalent uranium raster", uranium), ("Equivalent thorium raster", thorium))
        lower = self.parameterAsDouble(parameters, self.LOWER, context)
        upper = self.parameterAsDouble(parameters, self.UPPER, context)
        if upper <= lower:
            raise QgsProcessingException("Upper stretch percentile must exceed lower percentile.")
        rgb = ternary_rgb(self.values(potassium), self.values(uranium), self.values(thorium), lower, upper, self.parameterAsBool(parameters, self.NORMALIZE, context))
        output = self.output_path(parameters, context)
        write_multiband_geotiff(output, rgb, potassium, ("K — red", "eTh — green", "eU — blue"), 0.0, byte=True)
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class RadiometryDoseRateAlgorithm(RadiometryBase):
    URANIUM = "URANIUM"
    URANIUM_BAND = "URANIUM_BAND"
    THORIUM = "THORIUM"
    THORIUM_BAND = "THORIUM_BAND"
    CK = "K_COEFFICIENT"
    CU = "U_COEFFICIENT"
    CTH = "TH_COEFFICIENT"

    def name(self):
        return "radiometry_dose_rate"

    def displayName(self):
        return self.tr("03 Terrestrial absorbed dose rate")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_secondary_raster(self.URANIUM, self.URANIUM_BAND, "Equivalent uranium raster (ppm eU)")
        self.add_secondary_raster(self.THORIUM, self.THORIUM_BAND, "Equivalent thorium raster (ppm eTh)")
        for name, label, default in ((self.CK, "K dose coefficient", 13.078), (self.CU, "eU dose coefficient", 5.675), (self.CTH, "eTh dose coefficient", 2.494)):
            self.addParameter(QgsProcessingParameterNumber(name, self.tr(label), type=PROCESSING_NUMBER_DOUBLE, defaultValue=default, minValue=0.0))

    def processAlgorithm(self, parameters, context, feedback):
        k = self.input_grid(parameters, context)
        u = self.secondary_grid(parameters, context, self.URANIUM, self.URANIUM_BAND, "equivalent uranium")
        th = self.secondary_grid(parameters, context, self.THORIUM, self.THORIUM_BAND, "equivalent thorium")
        self.require_matching(k, ("Equivalent uranium raster", u), ("Equivalent thorium raster", th))
        coefficients = tuple(self.parameterAsDouble(parameters, name, context) for name in (self.CK, self.CU, self.CTH))
        result = terrestrial_dose_rate(self.values(k), self.values(u), self.values(th), coefficients)
        output = self.output_path(parameters, context)
        self.write(output, result, k, "Terrestrial absorbed dose rate (nGy/h)")
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class RadiometryFParameterAlgorithm(RadiometryDoseRateAlgorithm):
    MINIMUM = "MINIMUM_THORIUM"

    def name(self):
        return "radiometry_f_parameter"

    def displayName(self):
        return self.tr("04 Interpretive F parameter — K × eU / eTh")

    def initAlgorithm(self, config=None):
        RadiometryBase.add_raster_parameters(self)
        self.add_secondary_raster(self.URANIUM, self.URANIUM_BAND, "Equivalent uranium raster (ppm eU)")
        self.add_secondary_raster(self.THORIUM, self.THORIUM_BAND, "Equivalent thorium raster (ppm eTh)")
        self.addParameter(QgsProcessingParameterNumber(self.MINIMUM, self.tr("Minimum eTh denominator"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0))

    def processAlgorithm(self, parameters, context, feedback):
        k = self.input_grid(parameters, context)
        u = self.secondary_grid(parameters, context, self.URANIUM, self.URANIUM_BAND, "equivalent uranium")
        th = self.secondary_grid(parameters, context, self.THORIUM, self.THORIUM_BAND, "equivalent thorium")
        self.require_matching(k, ("Equivalent uranium raster", u), ("Equivalent thorium raster", th))
        result = alteration_f_parameter(self.values(k), self.values(u), self.values(th), self.parameterAsDouble(parameters, self.MINIMUM, context))
        output = self.output_path(parameters, context)
        self.write(output, result, k, "Interpretive radiometric F parameter")
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class RadiometryQcAlgorithm(RadiometryBase):
    REPORT = "REPORT"
    EXPECTED_MINIMUM = "EXPECTED_MINIMUM"

    def name(self):
        return "radiometry_channel_qc"

    def displayName(self):
        return self.tr("05 Radiometric channel quality report")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, self.tr("Input raster")))
        self.addParameter(QgsProcessingParameterBand(self.BAND, self.tr("Input band"), parentLayerParameterName=self.INPUT, defaultValue=1))
        self.addParameter(QgsProcessingParameterNumber(self.EXPECTED_MINIMUM, self.tr("Expected physical minimum"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0))
        self.addParameter(QgsProcessingParameterFileDestination(self.REPORT, self.tr("Quality-control JSON report"), "JSON (*.json)"))

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context)
        report = channel_qc(self.values(grid), self.parameterAsDouble(parameters, self.EXPECTED_MINIMUM, context))
        report.update({"source": grid.source_path, "band": self.parameterAsInt(parameters, self.BAND, context), "units_warning": "Confirm whether the channel is cps, % K, ppm eU or ppm eTh from survey metadata."})
        output = self.parameterAsFileOutput(parameters, self.REPORT, context)
        with open(output, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        feedback.setProgress(100)
        return {self.REPORT: output}


class RadiometryDespikeAlgorithm(RadiometryBase):
    RADIUS = "RADIUS"
    THRESHOLD = "MAD_THRESHOLD"

    def name(self):
        return "radiometry_despike"

    def displayName(self):
        return self.tr("06 Radiometric despike — local median/MAD")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(QgsProcessingParameterNumber(
            self.RADIUS, self.tr("Neighborhood radius (cells)"),
            type=PROCESSING_NUMBER_INTEGER, defaultValue=1, minValue=1, maxValue=10,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.THRESHOLD, self.tr("Outlier threshold (MAD sigma)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=5.0, minValue=0.1,
        ))

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context)
        try:
            result, spikes = median_mad_despike(
                self.values(grid),
                round(self.parameterAsDouble(parameters, self.RADIUS, context)),
                self.parameterAsDouble(parameters, self.THRESHOLD, context),
            )
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        feedback.pushInfo(f"Replaced {int(spikes.sum())} isolated cells.")
        output = self.output_path(parameters, context)
        self.write(output, result, grid, "Median/MAD despiked radiometric channel")
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class RadiometryDeadTimeAlgorithm(RadiometryBase):
    DEAD_TIME = "DEAD_TIME_SECONDS"

    def name(self):
        return "radiometry_dead_time"

    def displayName(self):
        return self.tr("07 Raw counts — dead-time correction")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(QgsProcessingParameterNumber(self.DEAD_TIME, self.tr("Detector dead time (seconds)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.000005, minValue=0.0))

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context)
        try:
            result = dead_time_correction(self.values(grid), self.parameterAsDouble(parameters, self.DEAD_TIME, context))
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        output = self.output_path(parameters, context)
        self.write(output, result, grid, "Dead-time corrected count rate (cps)")
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class RadiometryBackgroundAlgorithm(RadiometryBase):
    AIRCRAFT = "AIRCRAFT_BACKGROUND"
    COSMIC = "COSMIC_BACKGROUND"
    RADON = "RADON_BACKGROUND"

    def name(self):
        return "radiometry_background"

    def displayName(self):
        return self.tr("08 Raw counts — aircraft, cosmic and radon background")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        for name, label in ((self.AIRCRAFT, "Aircraft background (cps)"), (self.COSMIC, "Cosmic background (cps)"), (self.RADON, "Atmospheric radon background (cps)")):
            self.addParameter(QgsProcessingParameterNumber(name, self.tr(label), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0))

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context)
        result = background_correction(self.values(grid), *(self.parameterAsDouble(parameters, name, context) for name in (self.AIRCRAFT, self.COSMIC, self.RADON)))
        output = self.output_path(parameters, context)
        self.write(output, result, grid, "Background-corrected count rate (cps)")
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class RadiometryHeightAlgorithm(RadiometryBase):
    HEIGHT = "HEIGHT"
    HEIGHT_BAND = "HEIGHT_BAND"
    REFERENCE = "REFERENCE_HEIGHT"
    ATTENUATION = "ATTENUATION_COEFFICIENT"

    def name(self):
        return "radiometry_height_attenuation"

    def displayName(self):
        return self.tr("09 Raw counts — height attenuation correction")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_secondary_raster(self.HEIGHT, self.HEIGHT_BAND, "Terrain-clearance raster (m)")
        self.addParameter(QgsProcessingParameterNumber(self.REFERENCE, self.tr("Reference terrain clearance (m)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=100.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(self.ATTENUATION, self.tr("Channel attenuation coefficient (1/m)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.007, minValue=0.0))

    def processAlgorithm(self, parameters, context, feedback):
        counts = self.input_grid(parameters, context)
        height = self.secondary_grid(parameters, context, self.HEIGHT, self.HEIGHT_BAND, "terrain clearance")
        self.require_matching(counts, ("Terrain-clearance raster", height))
        result = height_attenuation_correction(self.values(counts), self.values(height), self.parameterAsDouble(parameters, self.REFERENCE, context), self.parameterAsDouble(parameters, self.ATTENUATION, context))
        output = self.output_path(parameters, context)
        self.write(output, result, counts, "Height-normalized count rate (cps)")
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class RadiometryCalibrationAlgorithm(RadiometryBase):
    SENSITIVITY = "SENSITIVITY"
    OFFSET = "OFFSET"

    def name(self):
        return "radiometry_sensitivity_calibration"

    def displayName(self):
        return self.tr("10 Corrected counts — sensitivity calibration")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(QgsProcessingParameterNumber(self.SENSITIVITY, self.tr("Survey sensitivity (cps per concentration unit)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=1.0, minValue=0.000000001))
        self.addParameter(QgsProcessingParameterNumber(self.OFFSET, self.tr("Calibration offset (cps)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0))

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context)
        try:
            result = sensitivity_calibration(self.values(grid), self.parameterAsDouble(parameters, self.SENSITIVITY, context), self.parameterAsDouble(parameters, self.OFFSET, context))
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        output = self.output_path(parameters, context)
        self.write(output, result, grid, "Calibrated radioelement concentration")
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class RadiometrySpectralUnmixAlgorithm(RadiometryBase):
    URANIUM = "URANIUM_WINDOW"
    URANIUM_BAND = "URANIUM_BAND"
    THORIUM = "THORIUM_WINDOW"
    THORIUM_BAND = "THORIUM_BAND"
    COEFFICIENTS = (
        ("K_FROM_U", "K-window response to U"),
        ("K_FROM_TH", "K-window response to Th"),
        ("U_FROM_K", "U-window response to K"),
        ("U_FROM_TH", "U-window response to Th"),
        ("TH_FROM_K", "Th-window response to K"),
        ("TH_FROM_U", "Th-window response to U"),
    )

    def name(self):
        return "radiometry_spectral_unmix"

    def displayName(self):
        return self.tr("11 Raw windows — calibrated spectral stripping")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_secondary_raster(self.URANIUM, self.URANIUM_BAND, "Observed uranium-window raster")
        self.add_secondary_raster(self.THORIUM, self.THORIUM_BAND, "Observed thorium-window raster")
        for name, label in self.COEFFICIENTS:
            self.addParameter(QgsProcessingParameterNumber(name, self.tr(label), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0))

    def processAlgorithm(self, parameters, context, feedback):
        k = self.input_grid(parameters, context)
        u = self.secondary_grid(parameters, context, self.URANIUM, self.URANIUM_BAND, "uranium window")
        th = self.secondary_grid(parameters, context, self.THORIUM, self.THORIUM_BAND, "thorium window")
        self.require_matching(k, ("Observed uranium-window raster", u), ("Observed thorium-window raster", th))
        values = [self.parameterAsDouble(parameters, name, context) for name, _label in self.COEFFICIENTS]
        matrix = ((1.0, values[0], values[1]), (values[2], 1.0, values[3]), (values[4], values[5], 1.0))
        try:
            corrected = spectral_unmix(self.values(k), self.values(u), self.values(th), matrix)
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        output = self.output_path(parameters, context)
        corrected[~np.isfinite(corrected)] = -99999.0
        write_multiband_geotiff(output, corrected, k, ("Stripped K window (cps)", "Stripped U window (cps)", "Stripped Th window (cps)"), -99999.0)
        feedback.setProgress(100)
        return {self.OUTPUT: output}

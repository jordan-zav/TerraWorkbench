"""Magnetic field-direction transforms with optional automatic IGRF-14."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import re

from osgeo import osr
from qgis.core import QgsProcessingException, QgsProcessingParameterNumber

from .spectral_filters import SpectralFilterBase
from ..dependencies import import_ppigrf
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER
from ..spectral import magnetic_field_transform
from ..crs_utils import grid_convergence_degrees, raster_center


class MagneticDirectionTransformBase(SpectralFilterBase):
    processing_domain = "FFT / MAGNETIC WAVENUMBER"
    restore_trend_default = True
    FIELD_MODE = "FIELD_MODE"
    INCLINATION = "INCLINATION"
    DECLINATION = "DECLINATION"
    YEAR = "YEAR"
    MONTH = "MONTH"
    DAY = "DAY"
    USE_METADATA_DATE = "USE_METADATA_DATE"
    ALTITUDE_KM = "ALTITUDE_KM"
    MAGNETIZATION_INCLINATION = "MAGNETIZATION_INCLINATION"
    MAGNETIZATION_DECLINATION = "MAGNETIZATION_DECLINATION"
    MAX_GAIN = "MAX_GAIN"

    def group(self):
        return self.tr("MAG field-direction transforms")

    def groupId(self):
        return "magnetic_field_direction"

    def add_filter_parameters(self):
        self.addParameter(
            QgsProcessingParameterNumber(
                self.FIELD_MODE,
                self.tr("Field mode: 0 = manual, 1 = automatic IGRF-14"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=1,
                minValue=0,
                maxValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.INCLINATION,
                self.tr("Manual field inclination (degrees, positive down)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=-15.0,
                minValue=-90.0,
                maxValue=90.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DECLINATION,
                self.tr("Manual field declination (degrees clockwise from North)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.0,
                minValue=-360.0,
                maxValue=360.0,
            )
        )
        now = datetime.now(timezone.utc)
        self.addParameter(
            QgsProcessingParameterNumber(
                self.USE_METADATA_DATE,
                self.tr(
                    "Survey date source: 1 = imported metadata when available, 0 = fields below"
                ),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=1,
                minValue=0,
                maxValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.YEAR,
                self.tr("Survey year (IGRF mode)"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=now.year,
                minValue=1900,
                maxValue=2035,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MONTH,
                self.tr("Survey month (IGRF mode)"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=1,
                minValue=1,
                maxValue=12,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DAY,
                self.tr("Survey day (IGRF mode)"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=1,
                minValue=1,
                maxValue=31,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ALTITUDE_KM,
                self.tr("Observation altitude above ellipsoid (km)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.0,
                minValue=-1.0,
                maxValue=1000.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAGNETIZATION_INCLINATION,
                self.tr(
                    "Remanent magnetization inclination (optional; blank = induced)"
                ),
                type=PROCESSING_NUMBER_DOUBLE,
                optional=True,
                minValue=-90.0,
                maxValue=90.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAGNETIZATION_DECLINATION,
                self.tr(
                    "Remanent magnetization declination (optional; blank = induced)"
                ),
                type=PROCESSING_NUMBER_DOUBLE,
                optional=True,
                minValue=-360.0,
                maxValue=360.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_GAIN,
                self.tr("Maximum spectral gain (stabilization)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=100.0,
                minValue=1.000001,
            )
        )
        self.add_target_parameters()

    def add_target_parameters(self):
        pass

    def prepare(self, grid, parameters, context, feedback):
        center_x, center_y = raster_center(grid)
        try:
            self._grid_convergence = grid_convergence_degrees(
                grid.projection, center_x, center_y
            )
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        mode = self.parameterAsInt(parameters, self.FIELD_MODE, context)
        if mode == 0:
            self._field_inclination = self.parameterAsDouble(
                parameters, self.INCLINATION, context
            )
            self._field_declination = self.parameterAsDouble(
                parameters, self.DECLINATION, context
            )
            feedback.pushInfo(
                f"Manual field: inclination={self._field_inclination:.3f} degrees, "
                f"geographic declination={self._field_declination:.3f} degrees, "
                f"grid convergence={self._grid_convergence:.3f} degrees."
            )
            return
        metadata_date = grid.metadata.get("SURVEY_START", "")
        date_parts = re.search(
            r"\b(\d{4})(?:[-/](\d{1,2})(?:[-/](\d{1,2}))?)?", metadata_date
        )
        use_metadata = (
            self.parameterAsInt(parameters, self.USE_METADATA_DATE, context) == 1
        )
        try:
            if use_metadata and date_parts:
                date = datetime(
                    int(date_parts.group(1)),
                    int(date_parts.group(2) or 1),
                    int(date_parts.group(3) or 1),
                )
                feedback.pushInfo(
                    f"Survey date read from raster metadata: {metadata_date}"
                )
            else:
                date = datetime(
                    self.parameterAsInt(parameters, self.YEAR, context),
                    self.parameterAsInt(parameters, self.MONTH, context),
                    self.parameterAsInt(parameters, self.DAY, context),
                )
        except ValueError as error:
            raise QgsProcessingException(f"Invalid survey date: {error}") from error
        longitude, latitude = self._grid_center_wgs84(grid)
        altitude = self.parameterAsDouble(parameters, self.ALTITUDE_KM, context)
        east, north, up = import_ppigrf().igrf(longitude, latitude, altitude, date)
        east, north, up = float(east[0]), float(north[0]), float(up[0])
        horizontal = math.hypot(east, north)
        self._field_inclination = math.degrees(math.atan2(-up, horizontal))
        self._field_declination = math.degrees(math.atan2(east, north))
        total = math.sqrt(east * east + north * north + up * up)
        feedback.pushInfo(
            "IGRF-14 (ppigrf/IAGA-VMOD) at raster center: "
            f"lon={longitude:.6f}, lat={latitude:.6f}, date={date.date()}, "
            f"altitude={altitude:.3f} km, inclination={self._field_inclination:.3f} degrees, "
            f"declination={self._field_declination:.3f} degrees, total={total:.1f} nT."
        )

    @staticmethod
    def _grid_center_wgs84(grid):
        rows, columns = grid.values.shape
        transform = grid.geotransform
        x = transform[0] + columns * 0.5 * transform[1] + rows * 0.5 * transform[2]
        y = transform[3] + columns * 0.5 * transform[4] + rows * 0.5 * transform[5]
        source = osr.SpatialReference()
        if not grid.projection or source.ImportFromWkt(grid.projection) != 0:
            raise QgsProcessingException(
                "The input raster has no usable CRS for automatic IGRF."
            )
        target = osr.SpatialReference()
        target.ImportFromEPSG(4326)
        if hasattr(source, "SetAxisMappingStrategy"):
            source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        longitude, latitude, _height = osr.CoordinateTransformation(
            source, target
        ).TransformPoint(x, y)
        return longitude, latitude

    def source_angles(self):
        return (
            self._field_inclination,
            self._field_declination + self._grid_convergence,
        )

    def magnetization_angles(self, parameters, context):
        inc = self.parameterAsDouble(
            parameters, self.MAGNETIZATION_INCLINATION, context
        )
        dec = self.parameterAsDouble(
            parameters, self.MAGNETIZATION_DECLINATION, context
        )
        raw_inc = parameters.get(self.MAGNETIZATION_INCLINATION)
        raw_dec = parameters.get(self.MAGNETIZATION_DECLINATION)
        if raw_inc in (None, "") and raw_dec in (None, ""):
            return None, None
        if raw_inc in (None, "") or raw_dec in (None, ""):
            raise QgsProcessingException(
                "Provide both remanent magnetization angles or neither."
            )
        return inc, dec + self._grid_convergence

    def target_angles(self, parameters, context):
        raise NotImplementedError

    def transfer(self, k_east, k_north, radial, parameters, context):
        source_inc, source_dec = self.source_angles()
        target_inc, target_dec = self.target_angles(parameters, context)
        target_dec += self._grid_convergence
        mag_inc, mag_dec = self.magnetization_angles(parameters, context)
        return magnetic_field_transform(
            k_east,
            k_north,
            radial,
            source_inc,
            source_dec,
            target_inc,
            target_dec,
            mag_inc,
            mag_dec,
            self.parameterAsDouble(parameters, self.MAX_GAIN, context),
        )

    def shortHelpString(self):
        return super().shortHelpString() + self.tr(
            " Automatic mode evaluates IGRF-14 at the raster center and survey date. "
            "The gain cap stabilizes low-latitude singularities. Blank remanence angles "
            "assume induced magnetization parallel to the field."
        )


class ReductionToPoleIgrfAlgorithm(MagneticDirectionTransformBase):
    output_description = "Reduction to the pole (IGRF/manual)"

    def name(self):
        return "reduction_to_pole_igrf"

    def displayName(self):
        return self.tr("RTP — automatic IGRF-14 / manual (stabilized)")

    def target_angles(self, parameters, context):
        return 90.0, 0.0


class ReductionToEquatorAlgorithm(MagneticDirectionTransformBase):
    output_description = "Reduction to the equator"

    def name(self):
        return "reduction_to_equator"

    def displayName(self):
        return self.tr("RTE — automatic IGRF-14 / manual (stabilized)")

    def target_angles(self, parameters, context):
        return 0.0, self._field_declination


class FieldDirectionTransformAlgorithm(MagneticDirectionTransformBase):
    TARGET_INCLINATION = "TARGET_INCLINATION"
    TARGET_DECLINATION = "TARGET_DECLINATION"
    output_description = "Magnetic field-direction transform"

    def add_target_parameters(self):
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TARGET_INCLINATION,
                self.tr("Target inclination (degrees, positive down)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=90.0,
                minValue=-90.0,
                maxValue=90.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TARGET_DECLINATION,
                self.tr("Target declination (degrees clockwise from North)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.0,
                minValue=-360.0,
                maxValue=360.0,
            )
        )

    def name(self):
        return "field_direction_transform"

    def displayName(self):
        return self.tr("Transform magnetic field direction")

    def target_angles(self, parameters, context):
        return (
            self.parameterAsDouble(parameters, self.TARGET_INCLINATION, context),
            self.parameterAsDouble(parameters, self.TARGET_DECLINATION, context),
        )

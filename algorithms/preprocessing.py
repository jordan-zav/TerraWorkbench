"""IGRF removal and acquisition-quality control for ordered survey points."""

from __future__ import annotations

from datetime import datetime, timezone
import math

import numpy as np
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBand,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsUnitTypes,
    QgsWkbTypes,
)

from ..crs_utils import grid_convergence_degrees
from ..dependencies import import_ppigrf
from ..i18n import translate
from ..preprocessing import (
    BASE_INVALID,
    base_station_quality,
    estimate_time_lag,
    line_spacing_quality,
    QC_INVALID,
    flight_line_metrics,
    flight_quality_flags,
    magnetic_elements,
    unwrap_time_seconds,
)
from ..qgis_compat import (
    FIELD_TYPE_BOOL,
    FIELD_TYPE_DOUBLE,
    FIELD_TYPE_INTEGER,
    FIELD_TYPE_STRING,
    PROCESSING_NUMBER_DOUBLE,
    PROCESSING_NUMBER_INTEGER,
)
from ..survey_corrections import rotate_grid_velocity_to_true


def _finite_number(feature, field_name):
    if not field_name:
        return None
    try:
        value = float(feature[field_name])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _append_fields(source, definitions):
    fields = QgsFields(source.fields())
    collisions = [name for name, _kind in definitions if fields.indexOf(name) >= 0]
    if collisions:
        raise QgsProcessingException(
            "Output fields already exist: " + ", ".join(collisions)
        )
    for name, kind in definitions:
        fields.append(QgsField(name, kind))
    return fields


class PreprocessingBase(QgsProcessingAlgorithm):
    def createInstance(self):
        return type(self)()

    def tr(self, text):
        return translate(text)

    def group(self):
        return self.tr("Survey data preparation")

    def groupId(self):
        return "survey_data_preparation"


class MagneticIgrfRemovalAlgorithm(PreprocessingBase):
    INPUT = "INPUT"
    VALUE_FIELD = "VALUE_FIELD"
    ALTITUDE_FIELD = "ALTITUDE_FIELD"
    ALTITUDE = "ALTITUDE_METRES"
    YEAR = "YEAR"
    MONTH = "MONTH"
    DAY = "DAY"
    OUTPUT = "OUTPUT"

    def name(self):
        return "remove_igrf_main_field"

    def displayName(self):
        return self.tr("Magnetic anomaly — remove IGRF-14 main field")

    def initAlgorithm(self, config=None):
        del config
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr("Magnetic survey point layer"),
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.VALUE_FIELD,
                self.tr("Total magnetic field (nT)"),
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.Numeric,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ALTITUDE_FIELD,
                self.tr("Ellipsoidal altitude field (m, optional)"),
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.Numeric,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ALTITUDE,
                self.tr("Constant ellipsoidal altitude (m; used when field is blank)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.0,
                minValue=-1000.0,
                maxValue=1_000_000.0,
            )
        )
        for name, label, default, minimum, maximum in (
            (self.YEAR, "Survey year", datetime.now(timezone.utc).year, 1900, 2035),
            (self.MONTH, "Survey month", 1, 1, 12),
            (self.DAY, "Survey day", 1, 1, 31),
        ):
            self.addParameter(
                QgsProcessingParameterNumber(
                    name,
                    self.tr(label),
                    type=PROCESSING_NUMBER_INTEGER,
                    defaultValue=default,
                    minValue=minimum,
                    maxValue=maximum,
                )
            )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, self.tr("Magnetic anomaly points with IGRF elements")
            )
        )

    @staticmethod
    def _evaluate_igrf(longitude, latitude, altitude_km, date):
        model = import_ppigrf()
        try:
            components = model.igrf(longitude, latitude, altitude_km, date)
            flattened = [np.asarray(item, dtype=float).reshape(-1) for item in components]
            if all(item.size == len(longitude) for item in flattened):
                return flattened
        except (TypeError, ValueError):
            pass
        east, north, up = [], [], []
        for lon, lat, altitude in zip(longitude, latitude, altitude_km):
            result = model.igrf(float(lon), float(lat), float(altitude), date)
            values = [float(np.asarray(item).reshape(-1)[0]) for item in result]
            east.append(values[0])
            north.append(values[1])
            up.append(values[2])
        return [np.asarray(east), np.asarray(north), np.asarray(up)]

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None or not source.sourceCrs().isValid():
            raise QgsProcessingException("A point layer with a valid CRS is required.")
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        altitude_field = self.parameterAsString(
            parameters, self.ALTITUDE_FIELD, context
        )
        default_altitude = self.parameterAsDouble(parameters, self.ALTITUDE, context)
        try:
            date = datetime(
                self.parameterAsInt(parameters, self.YEAR, context),
                self.parameterAsInt(parameters, self.MONTH, context),
                self.parameterAsInt(parameters, self.DAY, context),
            )
        except ValueError as error:
            raise QgsProcessingException(f"Invalid survey date: {error}") from error

        transform = QgsCoordinateTransform(
            source.sourceCrs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            context.transformContext(),
        )
        features = [QgsFeature(feature) for feature in source.getFeatures()]
        valid_rows = []
        for feature in features:
            observed = _finite_number(feature, value_field)
            if observed is None or not feature.hasGeometry():
                continue
            point = feature.geometry().asPoint()
            geographic = transform.transform(point.x(), point.y())
            altitude = _finite_number(feature, altitude_field)
            if altitude is None:
                altitude = default_altitude
            valid_rows.append(
                (feature.id(), observed, geographic.x(), geographic.y(), altitude)
            )
        if not valid_rows:
            raise QgsProcessingException("No finite magnetic observations were found.")

        ids, observed, longitude, latitude, altitude = map(
            np.asarray, zip(*valid_rows)
        )
        east, north, up = self._evaluate_igrf(
            longitude.astype(float),
            latitude.astype(float),
            altitude.astype(float) / 1000.0,
            date,
        )
        total, _horizontal, declination, inclination = magnetic_elements(
            east, north, up
        )
        results = {}
        for index, feature_id in enumerate(ids.astype(int)):
            finite = bool(
                np.all(
                    np.isfinite(
                        [east[index], north[index], up[index], total[index]]
                    )
                )
            )
            results[feature_id] = (
                float(east[index]) if finite else None,
                float(north[index]) if finite else None,
                float(-up[index]) if finite else None,
                float(total[index]) if finite else None,
                float(declination[index]) if finite else None,
                float(inclination[index]) if finite else None,
                float(observed[index] - total[index]) if finite else None,
                finite,
            )

        definitions = (
            ("tw_igrf_e", FIELD_TYPE_DOUBLE),
            ("tw_igrf_n", FIELD_TYPE_DOUBLE),
            ("tw_igrf_d", FIELD_TYPE_DOUBLE),
            ("tw_igrf_f", FIELD_TYPE_DOUBLE),
            ("tw_igrf_dec", FIELD_TYPE_DOUBLE),
            ("tw_igrf_inc", FIELD_TYPE_DOUBLE),
            ("tw_mag_anom", FIELD_TYPE_DOUBLE),
            ("tw_igrf_ok", FIELD_TYPE_BOOL),
        )
        output_fields = _append_fields(source, definitions)
        sink, sink_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            output_fields,
            source.wkbType(),
            source.sourceCrs(),
        )
        if sink is None:
            raise QgsProcessingException("Could not create the IGRF output layer.")
        empty = (None, None, None, None, None, None, None, False)
        for feature in features:
            output = QgsFeature(output_fields)
            if feature.hasGeometry():
                output.setGeometry(feature.geometry())
            output.setAttributes(feature.attributes() + list(results.get(feature.id(), empty)))
            if not sink.addFeature(output, QgsFeatureSink.FastInsert):
                raise QgsProcessingException(
                    "Could not write an IGRF-corrected magnetic feature. "
                    + (sink.lastError() if hasattr(sink, "lastError") else "")
                )
        feedback.pushInfo(
            f"IGRF-14 removed at {len(results)} points for {date.date()}; "
            "tw_mag_anom = observed total field - local IGRF total intensity."
        )
        return {self.OUTPUT: sink_id}

    def shortHelpString(self):
        return self.tr(
            "Evaluates IGRF-14 independently at every valid survey point and subtracts its total intensity from the observed total magnetic field. Output components are east, north and positive-down in nT, with declination, inclination, total intensity and anomaly. Coordinates are transformed to WGS84; altitude must be ellipsoidal. Apply base-station, lag, heading and despike corrections first, then remove IGRF before line leveling and gridding."
        )


class FlightLineQcAlgorithm(PreprocessingBase):
    INPUT = "INPUT"
    TIME_FIELD = "TIME_FIELD"
    LINE_FIELD = "LINE_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    CLEARANCE_FIELD = "CLEARANCE_FIELD"
    MAX_TIME_GAP = "MAX_TIME_GAP"
    MAX_SPACING = "MAX_SPACING"
    MIN_SPEED = "MIN_SPEED"
    MAX_SPEED = "MAX_SPEED"
    MAX_TURN = "MAX_TURN"
    MIN_CLEARANCE = "MIN_CLEARANCE"
    MAX_CLEARANCE = "MAX_CLEARANCE"
    MAX_VALUE_RATE = "MAX_VALUE_RATE"
    OUTPUT = "OUTPUT"
    SUMMARY = "SUMMARY"

    def name(self):
        return "flight_line_quality_control"

    def displayName(self):
        return self.tr("Flight-line QC — navigation, clearance and channel rate")

    def initAlgorithm(self, config=None):
        del config
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr("Ordered survey point layer"),
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.TIME_FIELD,
                self.tr("Numeric time field (seconds on one continuous scale)"),
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.Numeric,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.LINE_FIELD,
                self.tr("Line identifier"),
                parentLayerParameterName=self.INPUT,
            )
        )
        for name, label in (
            (self.VALUE_FIELD, "Channel for rate-of-change QC (optional)"),
            (self.CLEARANCE_FIELD, "Terrain-clearance field (m, optional)"),
        ):
            self.addParameter(
                QgsProcessingParameterField(
                    name,
                    self.tr(label),
                    parentLayerParameterName=self.INPUT,
                    type=QgsProcessingParameterField.Numeric,
                    optional=True,
                )
            )
        thresholds = (
            (self.MAX_TIME_GAP, "Maximum sample time gap (s; 0 disables)", 2.0),
            (self.MAX_SPACING, "Maximum along-line sample spacing (m; 0 disables)", 0.0),
            (self.MIN_SPEED, "Minimum platform speed (m/s; 0 disables)", 0.0),
            (self.MAX_SPEED, "Maximum platform speed (m/s; 0 disables)", 0.0),
            (self.MAX_TURN, "Maximum heading change between samples (degrees; 0 disables)", 45.0),
            (self.MIN_CLEARANCE, "Minimum terrain clearance (m; 0 disables)", 0.0),
            (self.MAX_CLEARANCE, "Maximum terrain clearance (m; 0 disables)", 0.0),
            (self.MAX_VALUE_RATE, "Maximum absolute channel change rate per second (0 disables)", 0.0),
        )
        for name, label, default in thresholds:
            self.addParameter(
                QgsProcessingParameterNumber(
                    name,
                    self.tr(label),
                    type=PROCESSING_NUMBER_DOUBLE,
                    defaultValue=default,
                    minValue=0.0,
                )
            )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, self.tr("Survey points with flight QC fields")
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.SUMMARY, self.tr("Flight-line QC summary table")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None or not source.sourceCrs().isValid() or source.sourceCrs().isGeographic():
            raise QgsProcessingException(
                "Flight-line QC requires a valid projected survey CRS."
            )
        try:
            unit_factor = QgsUnitTypes.fromUnitToUnitFactor(
                source.sourceCrs().mapUnits(), QgsUnitTypes.DistanceMeters
            )
        except AttributeError:
            unit_factor = 1.0
        if not math.isfinite(unit_factor) or unit_factor <= 0.0:
            raise QgsProcessingException("The survey CRS must use linear units.")

        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        line_field = self.parameterAsString(parameters, self.LINE_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        clearance_field = self.parameterAsString(
            parameters, self.CLEARANCE_FIELD, context
        )
        thresholds = {
            "maximum_time_gap": self.parameterAsDouble(parameters, self.MAX_TIME_GAP, context),
            "maximum_spacing": self.parameterAsDouble(parameters, self.MAX_SPACING, context),
            "minimum_speed": self.parameterAsDouble(parameters, self.MIN_SPEED, context),
            "maximum_speed": self.parameterAsDouble(parameters, self.MAX_SPEED, context),
            "maximum_turn": self.parameterAsDouble(parameters, self.MAX_TURN, context),
            "minimum_clearance": self.parameterAsDouble(parameters, self.MIN_CLEARANCE, context),
            "maximum_clearance": self.parameterAsDouble(parameters, self.MAX_CLEARANCE, context),
            "maximum_value_rate": self.parameterAsDouble(parameters, self.MAX_VALUE_RATE, context),
        }
        center = source.sourceExtent().center()
        try:
            convergence = grid_convergence_degrees(
                source.sourceCrs().toWkt(), center.x(), center.y()
            )
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error

        features = [QgsFeature(feature) for feature in source.getFeatures()]
        groups = {}
        for feature in features:
            time = _finite_number(feature, time_field)
            if time is None or not feature.hasGeometry():
                continue
            point = feature.geometry().asPoint()
            line = str(feature[line_field])
            groups.setdefault(line, []).append(
                (
                    time,
                    feature.id(),
                    float(point.x()) * unit_factor,
                    float(point.y()) * unit_factor,
                    _finite_number(feature, value_field),
                    _finite_number(feature, clearance_field),
                )
            )
        if not groups:
            raise QgsProcessingException("No finite ordered survey observations were found.")

        results = {}
        summaries = []
        for line, rows in groups.items():
            rows.sort(key=lambda row: row[0])
            time, ids, east, north, values, clearance = zip(*rows)
            true_east, true_north = rotate_grid_velocity_to_true(
                np.asarray(east), np.asarray(north), convergence
            )
            value_array = None
            if value_field:
                value_array = np.asarray(
                    [np.nan if value is None else value for value in values], dtype=float
                )
            clearance_array = None
            if clearance_field:
                clearance_array = np.asarray(
                    [np.nan if value is None else value for value in clearance], dtype=float
                )
            metrics = flight_line_metrics(
                true_east,
                true_north,
                np.asarray(time, dtype=float),
                value_array,
                clearance_array,
            )
            flags = flight_quality_flags(metrics, **thresholds)
            if value_array is not None:
                flags[~np.isfinite(value_array)] |= QC_INVALID
            if clearance_array is not None and (
                thresholds["minimum_clearance"] != 0.0
                or thresholds["maximum_clearance"] > 0.0
            ):
                flags[~np.isfinite(clearance_array)] |= QC_INVALID
            if len(rows) < 2:
                flags[:] |= QC_INVALID
            for index, feature_id in enumerate(np.asarray(ids, dtype=int)):
                results[int(feature_id)] = (
                    float(metrics["interval"][index]) if np.isfinite(metrics["interval"][index]) else None,
                    float(metrics["spacing"][index]) if np.isfinite(metrics["spacing"][index]) else None,
                    float(metrics["speed"][index]) if np.isfinite(metrics["speed"][index]) else None,
                    float(metrics["azimuth"][index]) if np.isfinite(metrics["azimuth"][index]) else None,
                    float(metrics["turn"][index]) if np.isfinite(metrics["turn"][index]) else None,
                    float(metrics["value_rate"][index]) if np.isfinite(metrics["value_rate"][index]) else None,
                    int(flags[index]),
                    bool(flags[index] == 0),
                )
            finite_speed = metrics["speed"][np.isfinite(metrics["speed"])]
            finite_interval = metrics["interval"][np.isfinite(metrics["interval"])]
            finite_spacing = metrics["spacing"][np.isfinite(metrics["spacing"])]
            finite_clearance = metrics["clearance"][np.isfinite(metrics["clearance"])]
            summaries.append(
                (
                    line,
                    len(rows),
                    int(np.count_nonzero(flags)),
                    100.0 * float(np.count_nonzero(flags == 0)) / len(rows),
                    float(np.mean(finite_speed)) if finite_speed.size else None,
                    float(np.max(finite_interval)) if finite_interval.size else None,
                    float(np.max(finite_spacing)) if finite_spacing.size else None,
                    float(np.min(finite_clearance)) if finite_clearance.size else None,
                    float(np.max(finite_clearance)) if finite_clearance.size else None,
                )
            )

        definitions = (
            ("tw_dt", FIELD_TYPE_DOUBLE),
            ("tw_dist", FIELD_TYPE_DOUBLE),
            ("tw_speed", FIELD_TYPE_DOUBLE),
            ("tw_azim", FIELD_TYPE_DOUBLE),
            ("tw_turn", FIELD_TYPE_DOUBLE),
            ("tw_dvdt", FIELD_TYPE_DOUBLE),
            ("tw_qcflag", FIELD_TYPE_INTEGER),
            ("tw_qc_ok", FIELD_TYPE_BOOL),
        )
        output_fields = _append_fields(source, definitions)
        sink, sink_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            output_fields,
            source.wkbType(),
            source.sourceCrs(),
        )
        summary_fields = QgsFields()
        for name, kind in (
            ("line", FIELD_TYPE_STRING),
            ("samples", FIELD_TYPE_INTEGER),
            ("failed", FIELD_TYPE_INTEGER),
            ("pass_pct", FIELD_TYPE_DOUBLE),
            ("mean_speed", FIELD_TYPE_DOUBLE),
            ("max_gap", FIELD_TYPE_DOUBLE),
            ("max_space", FIELD_TYPE_DOUBLE),
            ("min_clear", FIELD_TYPE_DOUBLE),
            ("max_clear", FIELD_TYPE_DOUBLE),
        ):
            summary_fields.append(QgsField(name, kind))
        summary_sink, summary_id = self.parameterAsSink(
            parameters,
            self.SUMMARY,
            context,
            summary_fields,
            QgsWkbTypes.NoGeometry,
            source.sourceCrs(),
        )
        if sink is None or summary_sink is None:
            raise QgsProcessingException("Could not create flight-QC outputs.")
        invalid = (None, None, None, None, None, None, QC_INVALID, False)
        for feature in features:
            output = QgsFeature(output_fields)
            if feature.hasGeometry():
                output.setGeometry(feature.geometry())
            output.setAttributes(feature.attributes() + list(results.get(feature.id(), invalid)))
            if not sink.addFeature(output, QgsFeatureSink.FastInsert):
                raise QgsProcessingException("Could not write a flight-QC point.")
        for values in summaries:
            output = QgsFeature(summary_fields)
            output.setAttributes(list(values))
            if not summary_sink.addFeature(output, QgsFeatureSink.FastInsert):
                raise QgsProcessingException("Could not write a flight-QC summary row.")
        feedback.pushInfo(
            "QC flag bits: 1 invalid, 2 time gap, 4 spacing, 8 speed, "
            "16 heading change, 32 clearance, 64 channel rate. "
            f"Grid-to-true convergence: {convergence:.6f} degrees."
        )
        return {self.OUTPUT: sink_id, self.SUMMARY: summary_id}

    def shortHelpString(self):
        return self.tr(
            "Audits ordered flight-line points without deleting observations. It appends time interval, spacing, speed, true-north azimuth, heading change, channel change rate, a bit-mask and pass flag, plus a per-line summary table. Threshold value 0 disables that test. Bit values are 1 invalid, 2 time gap, 4 spacing, 8 speed, 16 heading change, 32 clearance and 64 channel rate. Review flags before corrections, leveling and gridding."
        )


class RepeatLineQcAlgorithm(PreprocessingBase):
    INPUT = "INPUT"
    VALUE_FIELD = "VALUE_FIELD"
    LINE_FIELD = "LINE_FIELD"
    REPEAT_GROUP_FIELD = "REPEAT_GROUP_FIELD"
    MAX_DISTANCE = "MAX_DISTANCE"
    APPLY_CORRECTION = "APPLY_CORRECTION"
    OUTPUT = "OUTPUT"
    SUMMARY = "SUMMARY"

    def name(self):
        return "repeat_line_quality_control"

    def displayName(self):
        return self.tr("Repeat-line QC and median offset correction")

    def initAlgorithm(self, config=None):
        del config
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr("Survey point layer with repeated lines"),
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.VALUE_FIELD,
                self.tr("Observed field channel"),
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.Numeric,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.LINE_FIELD,
                self.tr("Line identifier"),
                parentLayerParameterName=self.INPUT,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.REPEAT_GROUP_FIELD,
                self.tr("Repeat group identifier"),
                parentLayerParameterName=self.INPUT,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_DISTANCE,
                self.tr("Maximum nearest-reference match distance (m)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=50.0,
                minValue=0.000001,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.APPLY_CORRECTION,
                self.tr("Apply robust median offset to repeated lines"),
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, self.tr("Repeat-line comparison points")
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.SUMMARY, self.tr("Repeat-line QC summary table")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None or not source.sourceCrs().isValid() or source.sourceCrs().isGeographic():
            raise QgsProcessingException(
                "Repeat-line QC requires a valid projected survey CRS."
            )
        try:
            unit_factor = QgsUnitTypes.fromUnitToUnitFactor(
                source.sourceCrs().mapUnits(), QgsUnitTypes.DistanceMeters
            )
        except AttributeError:
            unit_factor = 1.0
        if not math.isfinite(unit_factor) or unit_factor <= 0.0:
            raise QgsProcessingException("The survey CRS must use linear units.")
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        line_field = self.parameterAsString(parameters, self.LINE_FIELD, context)
        group_field = self.parameterAsString(
            parameters, self.REPEAT_GROUP_FIELD, context
        )
        maximum_distance = self.parameterAsDouble(
            parameters, self.MAX_DISTANCE, context
        )
        apply_correction = self.parameterAsBool(
            parameters, self.APPLY_CORRECTION, context
        )
        features = [QgsFeature(feature) for feature in source.getFeatures()]
        groups = {}
        for feature in features:
            value = _finite_number(feature, value_field)
            if value is None or not feature.hasGeometry():
                continue
            point = feature.geometry().asPoint()
            group = str(feature[group_field])
            line = str(feature[line_field])
            groups.setdefault(group, {}).setdefault(line, []).append(
                (
                    feature.id(),
                    float(point.x()) * unit_factor,
                    float(point.y()) * unit_factor,
                    value,
                )
            )
        comparable = {
            group: lines for group, lines in groups.items() if len(lines) >= 2
        }
        if not comparable:
            raise QgsProcessingException(
                "No repeat group contains at least two valid survey lines."
            )

        results = {}
        summaries = []
        for group, lines in comparable.items():
            reference_name = sorted(
                lines, key=lambda name: (-len(lines[name]), name)
            )[0]
            reference = np.asarray(lines[reference_name], dtype=float)
            reference_xy = reference[:, 1:3]
            cell_size = maximum_distance
            reference_bins = {}
            for reference_index, (east, north) in enumerate(reference_xy):
                key = (math.floor(east / cell_size), math.floor(north / cell_size))
                reference_bins.setdefault(key, []).append(reference_index)
            for feature_id, _east, _north, value in lines[reference_name]:
                results[int(feature_id)] = (
                    reference_name,
                    0.0,
                    0.0,
                    0.0,
                    float(value),
                    True,
                )
            summaries.append(
                (group, reference_name, reference_name, len(reference), 0.0, 0.0, 0.0)
            )
            for line_name, line_rows in sorted(lines.items()):
                if line_name == reference_name:
                    continue
                residual_rows = []
                for feature_id, east, north, value in line_rows:
                    east_bin = math.floor(east / cell_size)
                    north_bin = math.floor(north / cell_size)
                    candidates = [
                        index
                        for delta_east in (-1, 0, 1)
                        for delta_north in (-1, 0, 1)
                        for index in reference_bins.get(
                            (east_bin + delta_east, north_bin + delta_north), ()
                        )
                    ]
                    if not candidates:
                        distance = None
                        nearest = None
                    else:
                        candidate_array = np.asarray(candidates, dtype=int)
                        distances = np.hypot(
                            reference_xy[candidate_array, 0] - east,
                            reference_xy[candidate_array, 1] - north,
                        )
                        nearest_offset = int(np.argmin(distances))
                        nearest = int(candidate_array[nearest_offset])
                        distance = float(distances[nearest_offset])
                    if distance is None or distance > maximum_distance:
                        results[int(feature_id)] = (
                            reference_name,
                            distance,
                            None,
                            0.0,
                            float(value),
                            False,
                        )
                        continue
                    residual = float(value - reference[nearest, 3])
                    residual_rows.append((int(feature_id), distance, residual, float(value)))
                residuals = np.asarray(
                    [row[2] for row in residual_rows], dtype=float
                )
                median = float(np.median(residuals)) if residuals.size else 0.0
                mad = (
                    1.4826 * float(np.median(np.abs(residuals - median)))
                    if residuals.size
                    else 0.0
                )
                correction = -median if apply_correction else 0.0
                for feature_id, distance, residual, value in residual_rows:
                    results[feature_id] = (
                        reference_name,
                        distance,
                        residual,
                        correction,
                        value + correction,
                        True,
                    )
                rms = (
                    float(np.sqrt(np.mean((residuals + correction) ** 2)))
                    if residuals.size
                    else None
                )
                summaries.append(
                    (
                        group,
                        line_name,
                        reference_name,
                        int(residuals.size),
                        median if residuals.size else None,
                        mad if residuals.size else None,
                        rms,
                    )
                )

        definitions = (
            ("tw_rep_ref", FIELD_TYPE_STRING),
            ("tw_rep_dst", FIELD_TYPE_DOUBLE),
            ("tw_rep_res", FIELD_TYPE_DOUBLE),
            ("tw_rep_cor", FIELD_TYPE_DOUBLE),
            ("tw_rep_val", FIELD_TYPE_DOUBLE),
            ("tw_rep_ok", FIELD_TYPE_BOOL),
        )
        output_fields = _append_fields(source, definitions)
        sink, sink_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            output_fields,
            source.wkbType(),
            source.sourceCrs(),
        )
        summary_fields = QgsFields()
        for name, kind in (
            ("group", FIELD_TYPE_STRING),
            ("line", FIELD_TYPE_STRING),
            ("reference", FIELD_TYPE_STRING),
            ("matched", FIELD_TYPE_INTEGER),
            ("median", FIELD_TYPE_DOUBLE),
            ("mad_sigma", FIELD_TYPE_DOUBLE),
            ("rms_after", FIELD_TYPE_DOUBLE),
        ):
            summary_fields.append(QgsField(name, kind))
        summary_sink, summary_id = self.parameterAsSink(
            parameters,
            self.SUMMARY,
            context,
            summary_fields,
            QgsWkbTypes.NoGeometry,
            source.sourceCrs(),
        )
        if sink is None or summary_sink is None:
            raise QgsProcessingException("Could not create repeat-line QC outputs.")
        empty = (None, None, None, 0.0, None, False)
        for feature in features:
            output = QgsFeature(output_fields)
            if feature.hasGeometry():
                output.setGeometry(feature.geometry())
            output.setAttributes(feature.attributes() + list(results.get(feature.id(), empty)))
            if not sink.addFeature(output, QgsFeatureSink.FastInsert):
                raise QgsProcessingException("Could not write a repeat-line QC point.")
        for values in summaries:
            output = QgsFeature(summary_fields)
            output.setAttributes(list(values))
            if not summary_sink.addFeature(output, QgsFeatureSink.FastInsert):
                raise QgsProcessingException("Could not write a repeat-line summary row.")
        feedback.pushInfo(
            "The line with most valid samples in each repeat group is the reference; ties use "
            "the first line identifier. Corrections are robust median offsets only."
        )
        return {self.OUTPUT: sink_id, self.SUMMARY: summary_id}

    def shortHelpString(self):
        return self.tr(
            "Compares repeated survey lines by nearest-reference matches inside a user-defined distance. The line with most valid samples in each repeat group is the reference. It reports match distance, residual, robust median, MAD sigma and RMS; an optional median offset can be applied without overwriting the original channel. Do not use this correction where repeat lines sample different geology or altitude conditions."
        )


class AutomaticLagAlgorithm(PreprocessingBase):
    INPUT = "INPUT"
    TIME_FIELD = "TIME_FIELD"
    RESPONSE_FIELD = "RESPONSE_FIELD"
    REFERENCE_FIELD = "REFERENCE_FIELD"
    MAXIMUM_LAG = "MAXIMUM_LAG"
    LAG_STEP = "LAG_STEP"
    USE_DERIVATIVE = "USE_DERIVATIVE"
    OUTPUT = "OUTPUT"
    CURVE = "CURVE"

    def name(self):
        return "automatic_channel_lag"

    def displayName(self):
        return self.tr("Automatic channel-lag estimation")

    def initAlgorithm(self, config=None):
        del config
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr("Ordered survey point layer")))
        for name, label in (
            (self.TIME_FIELD, "Numeric time field (seconds)"),
            (self.RESPONSE_FIELD, "Delayed response channel"),
            (self.REFERENCE_FIELD, "Reference channel"),
        ):
            self.addParameter(QgsProcessingParameterField(name, self.tr(label), parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterNumber(self.MAXIMUM_LAG, self.tr("Maximum absolute lag (s)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=5.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(self.LAG_STEP, self.tr("Lag search step (s)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.1, minValue=0.000001))
        self.addParameter(QgsProcessingParameterBoolean(self.USE_DERIVATIVE, self.tr("Correlate channel derivatives"), defaultValue=False))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr("Survey points with estimated lag")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.CURVE, self.tr("Lag-correlation curve")))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("A survey layer is required.")
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        response_field = self.parameterAsString(parameters, self.RESPONSE_FIELD, context)
        reference_field = self.parameterAsString(parameters, self.REFERENCE_FIELD, context)
        features = [QgsFeature(feature) for feature in source.getFeatures()]
        rows = []
        for feature in features:
            time = _finite_number(feature, time_field)
            response = _finite_number(feature, response_field)
            reference = _finite_number(feature, reference_field)
            if time is not None and response is not None and reference is not None:
                rows.append((time, feature.id(), response, reference))
        if len(rows) < 3:
            raise QgsProcessingException("At least three finite paired samples are required.")
        rows.sort(key=lambda row: row[0])
        time, ids, response, reference = map(np.asarray, zip(*rows))
        try:
            estimate = estimate_time_lag(
                time.astype(float), response.astype(float), time.astype(float), reference.astype(float),
                maximum_lag=self.parameterAsDouble(parameters, self.MAXIMUM_LAG, context),
                lag_step=self.parameterAsDouble(parameters, self.LAG_STEP, context),
                use_derivative=self.parameterAsBool(parameters, self.USE_DERIVATIVE, context),
            )
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        corrected_time = {int(fid): float(value - estimate["lag"]) for fid, value in zip(ids, time)}
        output_fields = _append_fields(source, (("tw_lag_s", FIELD_TYPE_DOUBLE), ("tw_timecor", FIELD_TYPE_DOUBLE), ("tw_lag_r", FIELD_TYPE_DOUBLE)))
        sink, sink_id = self.parameterAsSink(parameters, self.OUTPUT, context, output_fields, source.wkbType(), source.sourceCrs())
        curve_fields = QgsFields()
        for name, kind in (("lag_s", FIELD_TYPE_DOUBLE), ("correlation", FIELD_TYPE_DOUBLE), ("overlap", FIELD_TYPE_INTEGER), ("selected", FIELD_TYPE_BOOL)):
            curve_fields.append(QgsField(name, kind))
        curve_sink, curve_id = self.parameterAsSink(parameters, self.CURVE, context, curve_fields, QgsWkbTypes.NoGeometry, source.sourceCrs())
        if sink is None or curve_sink is None:
            raise QgsProcessingException("Could not create lag outputs.")
        for feature in features:
            output = QgsFeature(output_fields)
            if feature.hasGeometry():
                output.setGeometry(feature.geometry())
            corrected = corrected_time.get(feature.id())
            output.setAttributes(feature.attributes() + [estimate["lag"], corrected, estimate["correlation"]])
            if not sink.addFeature(output, QgsFeatureSink.FastInsert):
                raise QgsProcessingException("Could not write a lag-corrected feature.")
        for lag, correlation, overlap in zip(estimate["lags"], estimate["correlations"], estimate["counts"]):
            output = QgsFeature(curve_fields)
            output.setAttributes([float(lag), float(correlation) if np.isfinite(correlation) else None, int(overlap), bool(np.isclose(lag, estimate["lag"]))])
            curve_sink.addFeature(output, QgsFeatureSink.FastInsert)
        feedback.pushInfo(f"Estimated lag: {estimate['lag']:.6g} s; correlation {estimate['correlation']:.6g}; overlap {estimate['overlap']} samples. Positive lag shifts response timestamps earlier.")
        return {self.OUTPUT: sink_id, self.CURVE: curve_id}

    def shortHelpString(self):
        return self.tr("Searches a configurable time-lag range and maximizes absolute Pearson correlation between a delayed response channel and a reference channel. Positive lag means the response occurs late; tw_timecor equals original time minus lag. The complete correlation curve is returned for inspection. This estimates instrumental/channel delay only when the two channels represent the same physical variations; it must not be interpreted as base-station correction or geological validation.")


class BaseStationQcAlgorithm(PreprocessingBase):
    INPUT = "INPUT"
    TIME_FIELD = "TIME_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    UNWRAP = "UNWRAP"
    MAX_GAP = "MAX_GAP"
    SPIKE_WINDOW = "SPIKE_WINDOW"
    SPIKE_SIGMA = "SPIKE_SIGMA"
    MAX_RATE = "MAX_RATE"
    MAX_DRIFT = "MAX_DRIFT"
    OUTPUT = "OUTPUT"
    SUMMARY = "SUMMARY"

    def name(self):
        return "base_station_quality_control"

    def displayName(self):
        return self.tr("Magnetic base-station QC")

    def initAlgorithm(self, config=None):
        del config
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr("Base-station observations")))
        self.addParameter(QgsProcessingParameterField(self.TIME_FIELD, self.tr("Numeric UTC/time-of-day field (s)"), parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterField(self.VALUE_FIELD, self.tr("Base magnetic field (nT)"), parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterBoolean(self.UNWRAP, self.tr("Unwrap midnight rollover (86400 s)"), defaultValue=True))
        for name, label, default, number_type in (
            (self.MAX_GAP, "Maximum time gap (s; 0 disables)", 2.0, PROCESSING_NUMBER_DOUBLE),
            (self.SPIKE_WINDOW, "Robust spike half-window (samples)", 5, PROCESSING_NUMBER_INTEGER),
            (self.SPIKE_SIGMA, "Spike threshold (MAD sigma; 0 disables)", 5.0, PROCESSING_NUMBER_DOUBLE),
            (self.MAX_RATE, "Maximum absolute field rate (nT/s; 0 disables)", 0.0, PROCESSING_NUMBER_DOUBLE),
            (self.MAX_DRIFT, "Maximum absolute linear drift (nT/s; 0 disables)", 0.0, PROCESSING_NUMBER_DOUBLE),
        ):
            self.addParameter(QgsProcessingParameterNumber(name, self.tr(label), type=number_type, defaultValue=default, minValue=0.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr("Base observations with QC fields")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.SUMMARY, self.tr("Base-station QC summary")))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("A base-station layer is required.")
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        features = [QgsFeature(feature) for feature in source.getFeatures()]
        rows = [(feature.id(), _finite_number(feature, time_field), _finite_number(feature, value_field)) for feature in features]
        valid_rows = [(fid, time, value) for fid, time, value in rows if time is not None and value is not None]
        if len(valid_rows) < 3:
            raise QgsProcessingException("At least three finite base-station observations are required.")
        ids, raw_time, values = map(np.asarray, zip(*valid_rows))
        time = unwrap_time_seconds(raw_time) if self.parameterAsBool(parameters, self.UNWRAP, context) else raw_time.astype(float)
        order = np.argsort(time)
        ids, time, values = ids[order], time[order], values[order]
        metrics = base_station_quality(
            time.astype(float), values.astype(float),
            maximum_time_gap=self.parameterAsDouble(parameters, self.MAX_GAP, context),
            spike_window=self.parameterAsInt(parameters, self.SPIKE_WINDOW, context),
            spike_sigma=self.parameterAsDouble(parameters, self.SPIKE_SIGMA, context),
            maximum_rate=self.parameterAsDouble(parameters, self.MAX_RATE, context),
            maximum_drift_rate=self.parameterAsDouble(parameters, self.MAX_DRIFT, context),
        )
        result = {}
        for index, fid in enumerate(ids.astype(int)):
            result[int(fid)] = (float(time[index]), _optional(metrics["interval"][index]), _optional(metrics["rate"][index]), _optional(metrics["local_median"][index]), _optional(metrics["residual"][index]), int(metrics["flags"][index]), bool(metrics["flags"][index] == 0))
        output_fields = _append_fields(source, (("tw_base_t", FIELD_TYPE_DOUBLE), ("tw_base_dt", FIELD_TYPE_DOUBLE), ("tw_base_rate", FIELD_TYPE_DOUBLE), ("tw_base_med", FIELD_TYPE_DOUBLE), ("tw_base_res", FIELD_TYPE_DOUBLE), ("tw_base_qc", FIELD_TYPE_INTEGER), ("tw_base_ok", FIELD_TYPE_BOOL)))
        sink, sink_id = self.parameterAsSink(parameters, self.OUTPUT, context, output_fields, source.wkbType(), source.sourceCrs())
        summary_fields = QgsFields()
        for name, kind in (("samples", FIELD_TYPE_INTEGER), ("flagged", FIELD_TYPE_INTEGER), ("coverage_s", FIELD_TYPE_DOUBLE), ("max_gap_s", FIELD_TYPE_DOUBLE), ("drift_nt_s", FIELD_TYPE_DOUBLE)):
            summary_fields.append(QgsField(name, kind))
        summary_sink, summary_id = self.parameterAsSink(parameters, self.SUMMARY, context, summary_fields, QgsWkbTypes.NoGeometry, source.sourceCrs())
        if sink is None or summary_sink is None:
            raise QgsProcessingException("Could not create base-station QC outputs.")
        empty = (None, None, None, None, None, BASE_INVALID, False)
        for feature in features:
            output = QgsFeature(output_fields)
            if feature.hasGeometry():
                output.setGeometry(feature.geometry())
            output.setAttributes(feature.attributes() + list(result.get(feature.id(), empty)))
            sink.addFeature(output, QgsFeatureSink.FastInsert)
        summary = QgsFeature(summary_fields)
        finite_interval = metrics["interval"][np.isfinite(metrics["interval"])]
        summary.setAttributes([len(ids), int(np.count_nonzero(metrics["flags"])), float(time[-1] - time[0]), float(np.max(finite_interval)) if finite_interval.size else None, _optional(metrics["drift_rate"])])
        summary_sink.addFeature(summary, QgsFeatureSink.FastInsert)
        feedback.pushInfo("QC bits: 1 invalid, 2 time gap, 4 robust local spike, 8 field rate, 16 whole-record linear drift. Geomagnetic-storm status requires an external observatory/index and is intentionally not inferred here.")
        return {self.OUTPUT: sink_id, self.SUMMARY: summary_id}

    def shortHelpString(self):
        return self.tr("Audits magnetic base-station samples for invalid/reversed time, gaps, robust local spikes, field-change rate and whole-record linear drift. It can unwrap seconds-of-day across midnight. Original values are preserved; a bit mask, residuals and summary are appended. Magnetic-storm classification is not produced without an external Kp/observatory source.")


def _optional(value):
    return float(value) if np.isfinite(value) else None


class InterlineSpacingQcAlgorithm(PreprocessingBase):
    INPUT = "INPUT"
    LINE_FIELD = "LINE_FIELD"
    EXPECTED = "EXPECTED"
    TOLERANCE = "TOLERANCE"
    OUTPUT = "OUTPUT"

    def name(self):
        return "interline_spacing_quality_control"

    def displayName(self):
        return self.tr("Flight-line spacing and missing-line QC")

    def initAlgorithm(self, config=None):
        del config
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr("Survey point layer"), [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.LINE_FIELD, self.tr("Line identifier"), parentLayerParameterName=self.INPUT))
        self.addParameter(QgsProcessingParameterNumber(self.EXPECTED, self.tr("Expected line spacing (m; 0 = robust automatic)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(self.TOLERANCE, self.tr("Allowed spacing deviation (%)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=25.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr("Per-line spacing QC points")))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None or not source.sourceCrs().isValid() or source.sourceCrs().isGeographic():
            raise QgsProcessingException("Line-spacing QC requires a projected survey CRS.")
        unit_factor = QgsUnitTypes.fromUnitToUnitFactor(source.sourceCrs().mapUnits(), QgsUnitTypes.DistanceMeters)
        line_field = self.parameterAsString(parameters, self.LINE_FIELD, context)
        groups = {}
        for feature in source.getFeatures():
            if feature.hasGeometry():
                point = feature.geometry().asPoint()
                groups.setdefault(str(feature[line_field]), []).append((point.x() * unit_factor, point.y() * unit_factor, point.x(), point.y()))
        if len(groups) < 2:
            raise QgsProcessingException("At least two flight lines with geometry are required.")
        names, centers, display_centers, azimuths, counts = [], [], [], [], []
        for name, rows in sorted(groups.items()):
            array = np.asarray(rows, dtype=float)
            if len(array) < 2:
                continue
            centered = array[:, :2] - np.mean(array[:, :2], axis=0)
            _values, vectors = np.linalg.eigh(centered.T @ centered)
            vector = vectors[:, -1]
            names.append(name)
            centers.append(np.mean(array[:, :2], axis=0))
            display_centers.append(np.mean(array[:, 2:4], axis=0))
            azimuths.append(np.rad2deg(np.arctan2(vector[0], vector[1])) % 180.0)
            counts.append(len(array))
        if len(names) < 2:
            raise QgsProcessingException("At least two lines need two or more points each.")
        quality = line_spacing_quality(centers, azimuths, self.parameterAsDouble(parameters, self.EXPECTED, context), self.parameterAsDouble(parameters, self.TOLERANCE, context) / 100.0)
        fields = QgsFields()
        for name, kind in (("line", FIELD_TYPE_STRING), ("samples", FIELD_TYPE_INTEGER), ("azimuth", FIELD_TYPE_DOUBLE), ("offset_m", FIELD_TYPE_DOUBLE), ("spacing_m", FIELD_TYPE_DOUBLE), ("nominal_m", FIELD_TYPE_DOUBLE), ("gap_ratio", FIELD_TYPE_DOUBLE), ("qc_flag", FIELD_TYPE_BOOL)):
            fields.append(QgsField(name, kind))
        sink, sink_id = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.Point, source.sourceCrs())
        if sink is None:
            raise QgsProcessingException("Could not create line-spacing output.")
        for index, name in enumerate(names):
            output = QgsFeature(fields)
            from qgis.core import QgsGeometry, QgsPointXY
            output.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*display_centers[index])))
            spacing = quality["spacing"][index]
            ratio = spacing / quality["nominal"] if np.isfinite(spacing) and np.isfinite(quality["nominal"]) and quality["nominal"] > 0 else np.nan
            output.setAttributes([name, counts[index], float(azimuths[index]), float(quality["offset"][index]), _optional(spacing), _optional(quality["nominal"]), _optional(ratio), bool(quality["flag"][index])])
            sink.addFeature(output, QgsFeatureSink.FastInsert)
        feedback.pushInfo(f"Survey line azimuth {quality['survey_azimuth']:.3f} degrees; nominal spacing {quality['nominal']:.3f} m. A ratio near 2 commonly indicates one missing line, but the flag only reports spacing deviation.")
        return {self.OUTPUT: sink_id}

    def shortHelpString(self):
        return self.tr("Estimates each flight-line direction by PCA, derives the survey direction as an axial circular mean, orders line centers across strike and reports adjacent spacing. Expected spacing may be supplied or estimated as the median. Large gaps are flagged and gap_ratio helps identify likely missing lines; tie lines must be excluded or processed separately.")


class DrapeDemQcAlgorithm(PreprocessingBase):
    INPUT = "INPUT"
    ALTITUDE_FIELD = "ALTITUDE_FIELD"
    DEM = "DEM"
    BAND = "BAND"
    TARGET = "TARGET"
    TOLERANCE = "TOLERANCE"
    MINIMUM = "MINIMUM"
    MAXIMUM = "MAXIMUM"
    OUTPUT = "OUTPUT"
    SUMMARY = "SUMMARY"

    def name(self):
        return "drape_dem_quality_control"

    def displayName(self):
        return self.tr("Drape and terrain-clearance QC against DEM")

    def initAlgorithm(self, config=None):
        del config
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr("Survey point layer"), [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ALTITUDE_FIELD, self.tr("Platform altitude field (m)"), parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterRasterLayer(self.DEM, self.tr("Terrain DEM (m, same vertical datum as altitude)")))
        self.addParameter(QgsProcessingParameterBand(self.BAND, self.tr("DEM band"), parentLayerParameterName=self.DEM, defaultValue=1))
        for name, label, default in ((self.TARGET, "Target clearance (m; 0 disables target test)", 0.0), (self.TOLERANCE, "Target-clearance tolerance (m)", 25.0), (self.MINIMUM, "Minimum clearance (m; 0 disables)", 0.0), (self.MAXIMUM, "Maximum clearance (m; 0 disables)", 0.0)):
            self.addParameter(QgsProcessingParameterNumber(name, self.tr(label), type=PROCESSING_NUMBER_DOUBLE, defaultValue=default, minValue=0.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr("Survey points with DEM clearance QC")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.SUMMARY, self.tr("Drape QC summary")))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        dem = self.parameterAsRasterLayer(parameters, self.DEM, context)
        if source is None or dem is None or not source.sourceCrs().isValid() or not dem.crs().isValid():
            raise QgsProcessingException("Valid survey and DEM CRS definitions are required.")
        altitude_field = self.parameterAsString(parameters, self.ALTITUDE_FIELD, context)
        band = self.parameterAsInt(parameters, self.BAND, context)
        target = self.parameterAsDouble(parameters, self.TARGET, context)
        tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context)
        minimum = self.parameterAsDouble(parameters, self.MINIMUM, context)
        maximum = self.parameterAsDouble(parameters, self.MAXIMUM, context)
        transform = QgsCoordinateTransform(source.sourceCrs(), dem.crs(), context.transformContext())
        features = [QgsFeature(feature) for feature in source.getFeatures()]
        results, clearances = {}, []
        for feature in features:
            altitude = _finite_number(feature, altitude_field)
            if altitude is None or not feature.hasGeometry():
                results[feature.id()] = (None, None, None, 1, False)
                continue
            point = feature.geometry().asPoint()
            dem_point = transform.transform(point.x(), point.y())
            elevation, ok = dem.dataProvider().sample(dem_point, band)
            if not ok or elevation is None or not math.isfinite(float(elevation)):
                results[feature.id()] = (None, None, None, 1, False)
                continue
            clearance = altitude - float(elevation)
            residual = clearance - target if target > 0.0 else None
            flag = 0
            if target > 0.0 and abs(residual) > tolerance:
                flag |= 2
            if minimum > 0.0 and clearance < minimum:
                flag |= 4
            if maximum > 0.0 and clearance > maximum:
                flag |= 8
            clearances.append(clearance)
            results[feature.id()] = (float(elevation), float(clearance), residual, flag, flag == 0)
        output_fields = _append_fields(source, (("tw_dem_z", FIELD_TYPE_DOUBLE), ("tw_clear", FIELD_TYPE_DOUBLE), ("tw_drape_res", FIELD_TYPE_DOUBLE), ("tw_drape_qc", FIELD_TYPE_INTEGER), ("tw_drape_ok", FIELD_TYPE_BOOL)))
        sink, sink_id = self.parameterAsSink(parameters, self.OUTPUT, context, output_fields, source.wkbType(), source.sourceCrs())
        summary_fields = QgsFields()
        for name, kind in (("samples", FIELD_TYPE_INTEGER), ("valid", FIELD_TYPE_INTEGER), ("flagged", FIELD_TYPE_INTEGER), ("mean_clear", FIELD_TYPE_DOUBLE), ("min_clear", FIELD_TYPE_DOUBLE), ("max_clear", FIELD_TYPE_DOUBLE), ("rmse_target", FIELD_TYPE_DOUBLE)):
            summary_fields.append(QgsField(name, kind))
        summary_sink, summary_id = self.parameterAsSink(parameters, self.SUMMARY, context, summary_fields, QgsWkbTypes.NoGeometry, source.sourceCrs())
        if sink is None or summary_sink is None:
            raise QgsProcessingException("Could not create drape QC outputs.")
        for feature in features:
            output = QgsFeature(output_fields)
            if feature.hasGeometry():
                output.setGeometry(feature.geometry())
            output.setAttributes(feature.attributes() + list(results[feature.id()]))
            sink.addFeature(output, QgsFeatureSink.FastInsert)
        values = np.asarray(clearances, dtype=float)
        flagged = sum(1 for row in results.values() if row[3] != 0)
        rmse = float(np.sqrt(np.mean((values - target) ** 2))) if values.size and target > 0.0 else None
        summary = QgsFeature(summary_fields)
        summary.setAttributes([len(features), len(values), flagged, float(np.mean(values)) if values.size else None, float(np.min(values)) if values.size else None, float(np.max(values)) if values.size else None, rmse])
        summary_sink.addFeature(summary, QgsFeatureSink.FastInsert)
        feedback.pushInfo("Drape QC bits: 1 invalid/DEM nodata, 2 outside target tolerance, 4 below minimum, 8 above maximum. Altitude and DEM must share the same vertical datum and units.")
        return {self.OUTPUT: sink_id, self.SUMMARY: summary_id}

    def shortHelpString(self):
        return self.tr("Samples a terrain DEM at every survey point, computes platform altitude minus terrain elevation, and reports target-clearance residuals plus configurable minimum/maximum flags. Horizontal CRS transformation is automatic. Vertical datum conversion is not automatic: platform altitude and DEM elevations must already use the same vertical datum and metres.")

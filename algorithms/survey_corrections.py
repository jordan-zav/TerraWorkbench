"""QGIS wrappers for moving-platform MAG and GRAV line corrections."""

from __future__ import annotations

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
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsUnitTypes,
)

from ..i18n import translate
from ..crs_utils import grid_convergence_degrees
from ..qgis_compat import FIELD_TYPE_BOOL, FIELD_TYPE_DOUBLE, PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER
from ..survey_corrections import (
    azimuth_from_velocity,
    eotvos_correction,
    hampel_filter_1d,
    heading_correction,
    interpolate_base_variation,
    lag_shift,
    linear_drift,
    rotate_grid_velocity_to_true,
    segment_velocity,
)


def _number(feature, field):
    try:
        value = float(feature[field])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _line_rows(source, line_field, time_field, value_field):
    groups = {}
    features = []
    for feature in source.getFeatures():
        copy = QgsFeature(feature)
        features.append(copy)
        value = _number(feature, value_field)
        time = _number(feature, time_field)
        if value is None or time is None or not feature.hasGeometry():
            continue
        point = feature.geometry().asPoint()
        line = str(feature[line_field]) if line_field else "__all__"
        groups.setdefault(line, []).append(
            (time, feature.id(), float(point.x()), float(point.y()), value)
        )
    return features, groups


class SurveyCorrectionBase(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    VALUE_FIELD = "VALUE_FIELD"
    TIME_FIELD = "TIME_FIELD"
    LINE_FIELD = "LINE_FIELD"
    OUTPUT = "OUTPUT"

    def createInstance(self):
        return type(self)()

    def tr(self, text):
        return translate(text)

    def group(self):
        return self.tr("Survey data preparation")

    def groupId(self):
        return "survey_data_preparation"

    def add_survey_parameters(self, value_label):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Ordered survey point layer"),
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.VALUE_FIELD, self.tr(value_label), parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.TIME_FIELD, self.tr("Numeric time field (seconds on one continuous scale)"),
            parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.LINE_FIELD, self.tr("Line identifier"), parentLayerParameterName=self.INPUT,
        ))

    @staticmethod
    def output_fields(source, names):
        fields = QgsFields(source.fields())
        collisions = [name for name, _field_type in names if fields.indexOf(name) >= 0]
        if collisions:
            raise QgsProcessingException("Output fields already exist: " + ", ".join(collisions))
        for name, field_type in names:
            fields.append(QgsField(name, field_type))
        return fields


class MagneticSurveyCorrectionAlgorithm(SurveyCorrectionBase):
    BASE = "BASE"
    BASE_TIME = "BASE_TIME_FIELD"
    BASE_VALUE = "BASE_VALUE_FIELD"
    LAG = "SIGNED_LAG_SECONDS"
    HEADING_COS = "HEADING_COSINE"
    HEADING_SIN = "HEADING_SINE"
    HAMPEL_RADIUS = "HAMPEL_RADIUS"
    HAMPEL_THRESHOLD = "HAMPEL_THRESHOLD"

    def name(self):
        return "correct_magnetic_survey_lines"

    def displayName(self):
        return self.tr("Magnetic line correction — base, lag, heading and despike")

    def initAlgorithm(self, config=None):
        del config
        self.add_survey_parameters("Observed magnetic field (nT)")
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.BASE, self.tr("Base-station point/table layer (optional)"), optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.BASE_TIME, self.tr("Base-station numeric time field"),
            parentLayerParameterName=self.BASE, type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.BASE_VALUE, self.tr("Base-station magnetic field (nT)"),
            parentLayerParameterName=self.BASE, type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.LAG, self.tr("Signed lag (seconds; samples input at time + lag)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.HEADING_COS, self.tr("Heading cosine coefficient (nT)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.HEADING_SIN, self.tr("Heading sine coefficient (nT)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.HAMPEL_RADIUS, self.tr("Along-line Hampel radius (samples; 0 disables)"),
            type=PROCESSING_NUMBER_INTEGER, defaultValue=3, minValue=0, maxValue=100,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.HAMPEL_THRESHOLD, self.tr("Along-line Hampel threshold (MAD sigma)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=4.5, minValue=0.1,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Corrected magnetic survey points")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("A valid magnetic survey layer is required.")
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        line_field = self.parameterAsString(parameters, self.LINE_FIELD, context)
        features, groups = _line_rows(source, line_field, time_field, value_field)
        if not groups:
            raise QgsProcessingException("No finite ordered magnetic observations were found.")

        base_source = self.parameterAsSource(parameters, self.BASE, context)
        base_time = base_values = None
        if base_source is not None:
            base_time_field = self.parameterAsString(parameters, self.BASE_TIME, context)
            base_value_field = self.parameterAsString(parameters, self.BASE_VALUE, context)
            base_rows = [
                (_number(feature, base_time_field), _number(feature, base_value_field))
                for feature in base_source.getFeatures()
            ]
            base_rows = [row for row in base_rows if None not in row]
            if len(base_rows) < 2:
                raise QgsProcessingException("The base-station layer needs at least two finite observations.")
            base_time, base_values = np.asarray(base_rows, dtype=float).T

        lag = self.parameterAsDouble(parameters, self.LAG, context)
        cosine = self.parameterAsDouble(parameters, self.HEADING_COS, context)
        sine = self.parameterAsDouble(parameters, self.HEADING_SIN, context)
        radius = self.parameterAsInt(parameters, self.HAMPEL_RADIUS, context)
        threshold = self.parameterAsDouble(parameters, self.HAMPEL_THRESHOLD, context)
        if (cosine != 0.0 or sine != 0.0) and source.sourceCrs().isGeographic():
            raise QgsProcessingException("Heading correction requires a projected survey CRS.")
        convergence = 0.0
        if cosine != 0.0 or sine != 0.0:
            center = source.sourceExtent().center()
            try:
                convergence = grid_convergence_degrees(
                    source.sourceCrs().toWkt(), center.x(), center.y()
                )
            except ValueError as error:
                raise QgsProcessingException(str(error)) from error

        corrections = {}
        spike_count = 0
        for rows in groups.values():
            rows.sort(key=lambda row: row[0])
            time, ids, east, north, observed = map(np.asarray, zip(*rows))
            shifted = lag_shift(time.astype(float), observed.astype(float), lag)
            if radius > 0:
                shifted, spikes = hampel_filter_1d(shifted, radius, threshold)
            else:
                spikes = np.zeros(shifted.shape, dtype=bool)
            east_velocity, north_velocity = segment_velocity(
                east.astype(float), north.astype(float), time.astype(float)
            )
            true_east, true_north = rotate_grid_velocity_to_true(
                east_velocity, north_velocity, convergence
            )
            heading = azimuth_from_velocity(true_east, true_north)
            head_term = heading_correction(heading, cosine, sine)
            if base_time is not None:
                base_term = interpolate_base_variation(time.astype(float), base_time, base_values)
            else:
                base_term = np.zeros(time.shape, dtype=float)
            corrected = shifted - base_term + head_term
            for index, feature_id in enumerate(ids.astype(int)):
                valid = bool(np.isfinite(corrected[index]))
                corrections[feature_id] = (
                    base_term[index], shifted[index], heading[index], head_term[index],
                    corrected[index], bool(spikes[index]), valid,
                )
            spike_count += int(spikes.sum())

        names = (
            ("tw_base", FIELD_TYPE_DOUBLE), ("tw_lagged", FIELD_TYPE_DOUBLE),
            ("tw_azimuth", FIELD_TYPE_DOUBLE), ("tw_heading", FIELD_TYPE_DOUBLE),
            ("tw_mag", FIELD_TYPE_DOUBLE), ("tw_spike", FIELD_TYPE_BOOL),
            ("tw_mag_ok", FIELD_TYPE_BOOL),
        )
        output_fields = self.output_fields(source, names)
        sink, sink_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, output_fields,
            source.wkbType(), source.sourceCrs(),
        )
        if sink is None:
            raise QgsProcessingException("Could not create corrected magnetic output.")
        for feature in features:
            values = corrections.get(feature.id(), (None, None, None, None, None, False, False))
            output = QgsFeature(output_fields)
            if feature.hasGeometry():
                output.setGeometry(feature.geometry())
            output.setAttributes(feature.attributes() + list(values))
            sink.addFeature(output, QgsFeatureSink.FastInsert)
        feedback.pushInfo(f"Corrected {len(corrections)} observations; replaced {spike_count} spikes.")
        if cosine != 0.0 or sine != 0.0:
            feedback.pushInfo(
                f"Heading directions converted from grid axes to true north using "
                f"{convergence:.6f} degrees convergence at the survey centre."
            )
        return {self.OUTPUT: sink_id}

    def shortHelpString(self):
        return self.tr("Corrects ordered magnetic lines before crossover leveling and gridding. A signed lag samples the input at time + lag; base-station variation is interpolated only inside its time coverage; heading uses explicit cosine/sine coefficients; Hampel despiking preserves the raw field. Inspect the appended correction terms and validity flag.")


class GravitySurveyCorrectionAlgorithm(SurveyCorrectionBase):
    TIDE_FIELD = "TIDE_FIELD"
    DRIFT_RATE = "DRIFT_RATE"
    EOTVOS_MODE = "EOTVOS_MODE"

    def name(self):
        return "correct_moving_gravity_survey"

    def displayName(self):
        return self.tr("Moving gravity correction — drift, tide field and Eötvös")

    def initAlgorithm(self, config=None):
        del config
        self.add_survey_parameters("Observed moving-platform gravity (mGal)")
        self.addParameter(QgsProcessingParameterField(
            self.TIDE_FIELD, self.tr("Precomputed Earth/ocean tide field (mGal, optional)"),
            parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.DRIFT_RATE, self.tr("Instrument drift rate (mGal/hour; subtracted)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.EOTVOS_MODE, self.tr("Eötvös term convention"),
            options=["Subtract term", "Add term", "Do not apply"], defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Corrected moving-gravity survey points")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None or not source.sourceCrs().isValid() or source.sourceCrs().isGeographic():
            raise QgsProcessingException("Moving-gravity correction requires a projected survey CRS.")
        try:
            unit_factor = QgsUnitTypes.fromUnitToUnitFactor(
                source.sourceCrs().mapUnits(), QgsUnitTypes.DistanceMeters
            )
        except AttributeError:
            unit_factor = 1.0
        if not math.isfinite(unit_factor) or unit_factor <= 0.0:
            raise QgsProcessingException("The survey CRS must use convertible linear units.")
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        line_field = self.parameterAsString(parameters, self.LINE_FIELD, context)
        tide_field = self.parameterAsString(parameters, self.TIDE_FIELD, context)
        features, groups = _line_rows(source, line_field, time_field, value_field)
        drift_rate = self.parameterAsDouble(parameters, self.DRIFT_RATE, context)
        mode = self.parameterAsInt(parameters, self.EOTVOS_MODE, context)
        eotvos_sign = -1.0 if mode == 0 else 1.0 if mode == 1 else 0.0
        to_geographic = QgsCoordinateTransform(
            source.sourceCrs(), QgsCoordinateReferenceSystem("EPSG:4326"),
            context.transformContext(),
        )
        corrections = {}
        feature_by_id = {feature.id(): feature for feature in features}
        all_times = [row[0] for rows in groups.values() for row in rows]
        drift_reference = float(np.min(all_times))
        center = source.sourceExtent().center()
        try:
            convergence = grid_convergence_degrees(
                source.sourceCrs().toWkt(), center.x(), center.y()
            )
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        for rows in groups.values():
            rows.sort(key=lambda row: row[0])
            time, ids, east, north, observed = map(np.asarray, zip(*rows))
            east = east.astype(float) * unit_factor
            north = north.astype(float) * unit_factor
            east_velocity, north_velocity = segment_velocity(east, north, time.astype(float))
            east_velocity, north_velocity = rotate_grid_velocity_to_true(
                east_velocity, north_velocity, convergence
            )
            latitude = []
            for row in rows:
                point = to_geographic.transform(float(row[2]), float(row[3]))
                latitude.append(point.y())
            eotvos = eotvos_correction(latitude, east_velocity, north_velocity)
            drift = linear_drift(
                time.astype(float), drift_rate, reference_time=drift_reference
            )
            for index, feature_id in enumerate(ids.astype(int)):
                feature = feature_by_id[feature_id]
                tide = _number(feature, tide_field) if tide_field else 0.0
                valid = tide is not None and np.isfinite(eotvos[index])
                corrected = (
                    float(observed[index]) - drift[index] - float(tide)
                    + eotvos_sign * eotvos[index]
                    if valid else None
                )
                corrections[feature_id] = (
                    drift[index], tide, eotvos[index], corrected, bool(valid)
                )
        feedback.pushInfo(
            f"Drift uses one survey-wide reference time ({drift_reference:g}); "
            f"velocities use true east/north ({convergence:.6f} degrees grid convergence)."
        )
        names = (
            ("tw_drift", FIELD_TYPE_DOUBLE), ("tw_tide", FIELD_TYPE_DOUBLE),
            ("tw_eotvos", FIELD_TYPE_DOUBLE), ("tw_gravity", FIELD_TYPE_DOUBLE),
            ("tw_grav_ok", FIELD_TYPE_BOOL),
        )
        output_fields = self.output_fields(source, names)
        sink, sink_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, output_fields,
            source.wkbType(), source.sourceCrs(),
        )
        if sink is None:
            raise QgsProcessingException("Could not create corrected gravity output.")
        for feature in features:
            values = corrections.get(feature.id(), (None, None, None, None, False))
            output = QgsFeature(output_fields)
            if feature.hasGeometry():
                output.setGeometry(feature.geometry())
            output.setAttributes(feature.attributes() + list(values))
            sink.addFeature(output, QgsFeatureSink.FastInsert)
        return {self.OUTPUT: sink_id}

    def shortHelpString(self):
        return self.tr("Corrects ordered moving-platform gravity observations before gridding. Linear instrument drift and an optional externally modelled tide field are subtracted. Eötvös acceleration is calculated from projected trajectory, numeric time and latitude; its add/subtract convention is explicit because meter reductions differ. This does not synthesize Earth, ocean or atmospheric tide models.")

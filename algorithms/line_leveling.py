"""Traverse/tie crossover QC and robust constant line leveling."""

from __future__ import annotations

import math
import numpy as np

from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsWkbTypes,
)
from ..line_processing import (
    evaluate_polynomial_correction,
    polynomial_residual_statistics,
    residual_statistics,
    robust_line_corrections,
    robust_polynomial_line_corrections,
)
from ..i18n import translate
from ..qgis_compat import (
    FIELD_TYPE_BOOL,
    FIELD_TYPE_DOUBLE,
    FIELD_TYPE_INTEGER,
    FIELD_TYPE_STRING,
    PROCESSING_NUMBER_DOUBLE,
    PROCESSING_NUMBER_INTEGER,
)


def _is_tie(value, requested):
    text = str(value).strip().casefold()
    choices = {item.strip().casefold() for item in requested.split(",") if item.strip()}
    if text in choices:
        return True
    try:
        return float(value) != 0.0 if choices.intersection({"1", "nonzero"}) else False
    except (TypeError, ValueError):
        return any(token in text for token in ("tie", "control", "base"))


def _intersection_points(geometry):
    if geometry.isEmpty():
        return []
    if QgsWkbTypes.geometryType(geometry.wkbType()) == QgsWkbTypes.PointGeometry:
        return [QgsPointXY(vertex) for vertex in geometry.vertices()]
    return [QgsPointXY(vertex) for vertex in geometry.vertices()]


class CrossoverLevelingAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    VALUE_FIELD = "VALUE_FIELD"
    LINE_FIELD = "LINE_FIELD"
    LINE_TYPE_FIELD = "LINE_TYPE_FIELD"
    ORDER_FIELD = "ORDER_FIELD"
    TIE_VALUES = "TIE_VALUES"
    OUTLIER_SIGMA = "OUTLIER_SIGMA"
    CORRECTION_ORDER = "CORRECTION_ORDER"
    HIGH_ORDER_DAMPING = "HIGH_ORDER_DAMPING"
    CORRECTED = "CORRECTED"
    CROSSOVERS = "CROSSOVERS"
    CORRECTIONS = "CORRECTIONS"

    def name(self):
        return "crossover_line_leveling"

    def displayName(self):
        return self.tr("Crossover QC and tie-line leveling")

    def group(self):
        return self.tr("Survey data preparation")

    def groupId(self):
        return "survey_data_preparation"

    def createInstance(self):
        return type(self)()

    def tr(self, text):
        return translate(text)

    def initAlgorithm(self, config=None):
        del config
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr("Survey point layer"),
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
                self.LINE_TYPE_FIELD,
                self.tr("Line type field"),
                parentLayerParameterName=self.INPUT,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ORDER_FIELD,
                self.tr("Along-line order/fiducial field (optional)"),
                parentLayerParameterName=self.INPUT,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.TIE_VALUES,
                self.tr("Values identifying tie lines (comma separated)"),
                defaultValue="1,tie,tie line,control",
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.OUTLIER_SIGMA,
                self.tr("Robust crossover rejection threshold (MAD sigma)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=4.5,
                minValue=0.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CORRECTION_ORDER,
                self.tr("Along-line correction order: 0 constant, 1 linear, 2 quadratic"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=0,
                minValue=0,
                maxValue=2,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.HIGH_ORDER_DAMPING,
                self.tr("Linear/quadratic coefficient damping"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.01,
                minValue=0.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.CORRECTED, self.tr("Leveled survey points")
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.CROSSOVERS, self.tr("Crossover QC points")
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.CORRECTIONS, self.tr("Line corrections table")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("A valid survey point layer is required.")
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        line_field = self.parameterAsString(parameters, self.LINE_FIELD, context)
        type_field = self.parameterAsString(parameters, self.LINE_TYPE_FIELD, context)
        order_field = self.parameterAsString(parameters, self.ORDER_FIELD, context)
        tie_values = self.parameterAsString(parameters, self.TIE_VALUES, context)
        groups = {}
        originals = []
        for feature in source.getFeatures():
            if feedback.isCanceled():
                return {}
            try:
                value = float(feature[value_field])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value) or not feature.hasGeometry():
                continue
            point = feature.geometry().asPoint()
            name = str(feature[line_field])
            order = feature[order_field] if order_field else feature.id()
            try:
                order = float(order)
            except (TypeError, ValueError):
                order = float(feature.id())
            row = (order, QgsPointXY(point), value, QgsFeature(feature))
            groups.setdefault(
                name, {"tie": _is_tie(feature[type_field], tie_values), "rows": []}
            )["rows"].append(row)
            originals.append((name, QgsFeature(feature)))
        lines = []
        for name, group in groups.items():
            rows = sorted(group["rows"], key=lambda row: row[0])
            points, values = [], []
            for _, point, value, _ in rows:
                if not points or point != points[-1]:
                    points.append(point)
                    values.append(value)
            if len(points) < 2:
                continue
            geometry = QgsGeometry.fromPolylineXY(points)
            distances = np.r_[
                0.0,
                np.cumsum(
                    [points[i].distance(points[i - 1]) for i in range(1, len(points))]
                ),
            ]
            lines.append(
                {
                    "name": name,
                    "tie": group["tie"],
                    "geometry": geometry,
                    "distance": distances,
                    "values": np.asarray(values),
                    "length": float(geometry.length()),
                }
            )
        line_by_name = {line["name"]: line for line in lines}
        traverses = [line for line in lines if not line["tie"]]
        ties = [line for line in lines if line["tie"]]
        if not traverses or not ties:
            raise QgsProcessingException(
                "Both traverse and tie lines are required. Check the line type field and tie values."
            )
        rows = []
        for traverse in traverses:
            for tie in ties:
                if (
                    not traverse["geometry"]
                    .boundingBox()
                    .intersects(tie["geometry"].boundingBox())
                ):
                    continue
                intersection = traverse["geometry"].intersection(tie["geometry"])
                for point in _intersection_points(intersection):
                    point_geometry = QgsGeometry.fromPointXY(point)
                    dt = traverse["geometry"].lineLocatePoint(point_geometry)
                    di = tie["geometry"].lineLocatePoint(point_geometry)
                    if dt < 0 or di < 0:
                        continue
                    vt = float(np.interp(dt, traverse["distance"], traverse["values"]))
                    vi = float(np.interp(di, tie["distance"], tie["values"]))
                    position_traverse = (
                        2.0 * dt / traverse["length"] - 1.0
                        if traverse["length"] > 0.0
                        else 0.0
                    )
                    position_tie = (
                        2.0 * di / tie["length"] - 1.0
                        if tie["length"] > 0.0
                        else 0.0
                    )
                    rows.append(
                        (
                            traverse["name"],
                            tie["name"],
                            vt - vi,
                            point,
                            vt,
                            vi,
                            position_traverse,
                            position_tie,
                        )
                    )
        if not rows:
            raise QgsProcessingException("No traverse/tie intersections were found.")
        order = self.parameterAsInt(parameters, self.CORRECTION_ORDER, context)
        outlier_sigma = self.parameterAsDouble(parameters, self.OUTLIER_SIGMA, context)
        compact = [(row[0], row[1], row[2]) for row in rows]
        polynomial_rows = [
            (row[0], row[1], row[2], row[6], row[7]) for row in rows
        ]
        if order == 0:
            constant_corrections, keep = robust_line_corrections(
                compact, outlier_sigma
            )
            corrections = {
                name: np.asarray([value], dtype=float)
                for name, value in constant_corrections.items()
            }
            stats = residual_statistics(compact, constant_corrections, keep)
        else:
            corrections, keep = robust_polynomial_line_corrections(
                polynomial_rows,
                order=order,
                outlier_sigma=outlier_sigma,
                damping=self.parameterAsDouble(
                    parameters, self.HIGH_ORDER_DAMPING, context
                ),
            )
            stats = polynomial_residual_statistics(
                polynomial_rows, corrections, keep
            )
        if not corrections:
            raise QgsProcessingException(
                "No crossover solution remained after robust rejection."
            )

        corrected_fields = QgsFields(source.fields())
        corrected_fields.append(QgsField("tw_line_corr", FIELD_TYPE_DOUBLE))
        corrected_fields.append(QgsField("tw_corrected", FIELD_TYPE_DOUBLE))
        corrected_sink, corrected_id = self.parameterAsSink(
            parameters,
            self.CORRECTED,
            context,
            corrected_fields,
            source.wkbType(),
            source.sourceCrs(),
        )
        cross_fields = QgsFields()
        for name, variant in (
            ("traverse", FIELD_TYPE_STRING),
            ("tie", FIELD_TYPE_STRING),
            ("trav_value", FIELD_TYPE_DOUBLE),
            ("tie_value", FIELD_TYPE_DOUBLE),
            ("res_before", FIELD_TYPE_DOUBLE),
            ("res_after", FIELD_TYPE_DOUBLE),
            ("accepted", FIELD_TYPE_BOOL),
        ):
            cross_fields.append(QgsField(name, variant))
        cross_sink, cross_id = self.parameterAsSink(
            parameters,
            self.CROSSOVERS,
            context,
            cross_fields,
            QgsWkbTypes.Point,
            source.sourceCrs(),
        )
        correction_fields = QgsFields()
        correction_fields.append(QgsField("line", FIELD_TYPE_STRING))
        correction_fields.append(QgsField("constant", FIELD_TYPE_DOUBLE))
        correction_fields.append(QgsField("linear", FIELD_TYPE_DOUBLE))
        correction_fields.append(QgsField("quadratic", FIELD_TYPE_DOUBLE))
        correction_fields.append(QgsField("order", FIELD_TYPE_INTEGER))
        correction_fields.append(QgsField("crossovers", FIELD_TYPE_INTEGER))
        correction_sink, correction_id = self.parameterAsSink(
            parameters,
            self.CORRECTIONS,
            context,
            correction_fields,
            QgsWkbTypes.NoGeometry,
            source.sourceCrs(),
        )
        if not corrected_sink or not cross_sink or not correction_sink:
            raise QgsProcessingException("Could not create one or more output layers.")
        for name, feature in originals:
            coefficients = corrections.get(name, np.zeros(order + 1, dtype=float))
            line = line_by_name.get(name)
            distance = (
                line["geometry"].lineLocatePoint(feature.geometry())
                if line is not None
                else -1.0
            )
            position = (
                2.0 * distance / line["length"] - 1.0
                if line is not None and line["length"] > 0.0 and distance >= 0.0
                else 0.0
            )
            correction = float(
                evaluate_polynomial_correction(coefficients, position)
            )
            value = float(feature[value_field])
            attributes = feature.attributes()
            output_feature = QgsFeature(corrected_fields)
            output_feature.setGeometry(feature.geometry())
            output_feature.setAttributes(attributes + [correction, value + correction])
            corrected_sink.addFeature(output_feature, QgsFeatureSink.FastInsert)
        counts = {name: 0 for name in corrections}
        for accepted, row in zip(keep, rows):
            traverse, tie, residual, point, vt, vi, position_traverse, position_tie = row
            if accepted:
                counts[traverse] += 1
                counts[tie] += 1
            feature = QgsFeature(cross_fields)
            feature.setGeometry(QgsGeometry.fromPointXY(point))
            feature.setAttributes(
                [
                    traverse,
                    tie,
                    vt,
                    vi,
                    residual,
                    residual
                    + float(
                        evaluate_polynomial_correction(
                            corrections.get(traverse, np.zeros(order + 1)),
                            position_traverse,
                        )
                    )
                    - float(
                        evaluate_polynomial_correction(
                            corrections.get(tie, np.zeros(order + 1)), position_tie
                        )
                    ),
                    bool(accepted),
                ]
            )
            cross_sink.addFeature(feature, QgsFeatureSink.FastInsert)
        for name, coefficients in sorted(corrections.items()):
            feature = QgsFeature(correction_fields)
            padded = np.pad(
                np.asarray(coefficients, dtype=float),
                (0, max(0, 3 - len(coefficients))),
            )
            feature.setAttributes(
                [name, float(padded[0]), float(padded[1]), float(padded[2]), order, counts[name]]
            )
            correction_sink.addFeature(feature, QgsFeatureSink.FastInsert)
        feedback.pushInfo(
            f"Accepted crossovers: {stats['count']}; RMS {stats['rms_before']:.4g} -> {stats['rms_after']:.4g} field units."
        )
        return {
            self.CORRECTED: corrected_id,
            self.CROSSOVERS: cross_id,
            self.CORRECTIONS: correction_id,
        }

    def shortHelpString(self):
        return self.tr(
            "Finds traverse/tie intersections, interpolates observations at each crossover, rejects robust MAD outliers, and solves zero-mean constant, linear or damped quadratic corrections for every connected line. Polynomial positions are normalized independently along each line; damping limits unsupported end-of-line swings. The output preserves raw values and adds tw_line_corr and tw_corrected. Apply lag, base-station and IGRF corrections before this step; inspect RMS, coefficients and crossover maps before gridding."
        )

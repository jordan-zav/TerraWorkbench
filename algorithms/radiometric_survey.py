"""Line-domain correction chain for raw airborne radiometric channels."""

from __future__ import annotations

import math

import numpy as np
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
)

from ..i18n import translate
from ..qgis_compat import FIELD_TYPE_BOOL, FIELD_TYPE_DOUBLE, PROCESSING_NUMBER_DOUBLE
from ..radiometry import (
    background_correction,
    dead_time_correction,
    height_attenuation_correction,
    sensitivity_calibration,
    spectral_unmix,
    terrestrial_dose_rate,
)


class RadiometricSurveyCorrectionAlgorithm(QgsProcessingAlgorithm):
    """Apply an explicit calibration sequence before line leveling and gridding."""

    INPUT = "INPUT"
    K_FIELD = "K_WINDOW_FIELD"
    U_FIELD = "U_WINDOW_FIELD"
    TH_FIELD = "TH_WINDOW_FIELD"
    TOTAL_FIELD = "TOTAL_COUNT_FIELD"
    HEIGHT_FIELD = "CLEARANCE_FIELD"
    DEAD_TIME = "DEAD_TIME_SECONDS"
    REFERENCE_HEIGHT = "REFERENCE_HEIGHT"
    OUTPUT = "OUTPUT"

    BACKGROUNDS = (
        ("K_BACKGROUND", "K-window total background (cps)"),
        ("U_BACKGROUND", "U-window total background (cps)"),
        ("TH_BACKGROUND", "Th-window total background (cps)"),
    )
    RESPONSE = (
        ("K_FROM_U", "K-window response to U"),
        ("K_FROM_TH", "K-window response to Th"),
        ("U_FROM_K", "U-window response to K"),
        ("U_FROM_TH", "U-window response to Th"),
        ("TH_FROM_K", "Th-window response to K"),
        ("TH_FROM_U", "Th-window response to U"),
    )
    ATTENUATION = (
        ("K_ATTENUATION", "K attenuation coefficient (1/m)"),
        ("U_ATTENUATION", "U attenuation coefficient (1/m)"),
        ("TH_ATTENUATION", "Th attenuation coefficient (1/m)"),
    )
    SENSITIVITY = (
        ("K_SENSITIVITY", "K sensitivity (cps per % K)"),
        ("U_SENSITIVITY", "U sensitivity (cps per ppm eU)"),
        ("TH_SENSITIVITY", "Th sensitivity (cps per ppm eTh)"),
    )

    def name(self):
        return "radiometry_correct_survey_channels"

    def displayName(self):
        return self.tr("Radiometric survey correction — raw windows to K/eU/eTh")

    def group(self):
        return self.tr("Gamma-ray spectrometry")

    def groupId(self):
        return "gamma_ray_spectrometry"

    def createInstance(self):
        return type(self)()

    def tr(self, text):
        return translate(text)

    def initAlgorithm(self, config=None):
        del config
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Radiometric survey point layer"),
            [QgsProcessing.TypeVectorPoint],
        ))
        for name, label in (
            (self.K_FIELD, "Raw K-window count-rate field"),
            (self.U_FIELD, "Raw U-window count-rate field"),
            (self.TH_FIELD, "Raw Th-window count-rate field"),
        ):
            self.addParameter(QgsProcessingParameterField(
                name, self.tr(label), parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.Numeric,
            ))
        self.addParameter(QgsProcessingParameterField(
            self.HEIGHT_FIELD, self.tr("Terrain-clearance field (m, optional)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.TOTAL_FIELD, self.tr("Total-count field for dead-time correction (optional if dead time is zero)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.DEAD_TIME, self.tr("Detector dead time (seconds)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.000005, minValue=0.0,
        ))
        for name, label in self.BACKGROUNDS:
            self.addParameter(QgsProcessingParameterNumber(
                name, self.tr(label), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0,
            ))
        for name, label in self.RESPONSE:
            self.addParameter(QgsProcessingParameterNumber(
                name, self.tr(label), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0,
            ))
        self.addParameter(QgsProcessingParameterNumber(
            self.REFERENCE_HEIGHT, self.tr("Reference terrain clearance (m)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=100.0, minValue=0.0,
        ))
        for name, label in self.ATTENUATION:
            self.addParameter(QgsProcessingParameterNumber(
                name, self.tr(label), type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.007, minValue=0.0,
            ))
        for name, label in self.SENSITIVITY:
            self.addParameter(QgsProcessingParameterNumber(
                name, self.tr(label), type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=1.0, minValue=1e-12,
            ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Corrected radiometric survey points")
        ))

    @staticmethod
    def _numeric(feature, field):
        try:
            value = float(feature[field])
        except (TypeError, ValueError, KeyError):
            return None
        return value if math.isfinite(value) else None

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("A valid radiometric point layer is required.")
        fields = {
            "k": self.parameterAsString(parameters, self.K_FIELD, context),
            "u": self.parameterAsString(parameters, self.U_FIELD, context),
            "th": self.parameterAsString(parameters, self.TH_FIELD, context),
            "height": self.parameterAsString(parameters, self.HEIGHT_FIELD, context),
            "total": self.parameterAsString(parameters, self.TOTAL_FIELD, context),
        }
        response_values = [
            self.parameterAsDouble(parameters, name, context)
            for name, _label in self.RESPONSE
        ]
        response = np.asarray(
            (
                (1.0, response_values[0], response_values[1]),
                (response_values[2], 1.0, response_values[3]),
                (response_values[4], response_values[5], 1.0),
            )
        )
        # Validate the calibration system before creating a partial output.
        try:
            spectral_unmix([1.0], [1.0], [1.0], response)
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        dead_time = self.parameterAsDouble(parameters, self.DEAD_TIME, context)
        if dead_time > 0.0 and not fields["total"]:
            raise QgsProcessingException(
                "A total-count field is required when detector dead time is non-zero."
            )
        backgrounds = [
            self.parameterAsDouble(parameters, name, context)
            for name, _label in self.BACKGROUNDS
        ]
        reference_height = self.parameterAsDouble(
            parameters, self.REFERENCE_HEIGHT, context
        )
        attenuation = [
            self.parameterAsDouble(parameters, name, context)
            for name, _label in self.ATTENUATION
        ]
        sensitivities = [
            self.parameterAsDouble(parameters, name, context)
            for name, _label in self.SENSITIVITY
        ]

        output_fields = QgsFields(source.fields())
        new_names = (
            "tw_k_cps",
            "tw_u_cps",
            "tw_th_cps",
            "tw_k_pct",
            "tw_eu_ppm",
            "tw_eth_ppm",
            "tw_dose",
            "tw_rad_ok",
        )
        collisions = [name for name in new_names if output_fields.indexOf(name) >= 0]
        if collisions:
            raise QgsProcessingException(
                "Output fields already exist: " + ", ".join(collisions)
            )
        for name in new_names[:-1]:
            output_fields.append(QgsField(name, FIELD_TYPE_DOUBLE))
        output_fields.append(QgsField(new_names[-1], FIELD_TYPE_BOOL))
        sink, sink_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, output_fields,
            source.wkbType(), source.sourceCrs(),
        )
        if sink is None:
            raise QgsProcessingException("Could not create the corrected survey layer.")

        corrected_count = 0
        invalid_count = 0
        total = max(source.featureCount(), 1)
        for index, feature in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                return {}
            raw = [self._numeric(feature, fields[name]) for name in ("k", "u", "th")]
            height = self._numeric(feature, fields["height"]) if fields["height"] else None
            total_count = self._numeric(feature, fields["total"]) if fields["total"] else None
            values = [None] * 7
            valid = all(value is not None for value in raw) and (
                not fields["height"] or height is not None
            ) and (dead_time <= 0.0 or (total_count is not None and total_count > 0.0))
            if valid:
                try:
                    if dead_time > 0.0:
                        corrected_total = dead_time_correction([total_count], dead_time)[0]
                        counts = np.asarray(raw) * (corrected_total / total_count)
                    else:
                        counts = np.asarray(raw, dtype=np.float64)
                    counts = np.asarray(
                        [background_correction([value], background)[0] for value, background in zip(counts, backgrounds)]
                    )
                    counts = spectral_unmix(
                        [counts[0]], [counts[1]], [counts[2]], response
                    )[:, 0]
                    if fields["height"]:
                        counts = np.asarray(
                            [height_attenuation_correction([value], [height], reference_height, coefficient)[0] for value, coefficient in zip(counts, attenuation)]
                        )
                    concentrations = np.asarray(
                        [sensitivity_calibration([value], sensitivity)[0] for value, sensitivity in zip(counts, sensitivities)]
                    )
                    dose = terrestrial_dose_rate(
                        [concentrations[0]], [concentrations[1]], [concentrations[2]]
                    )[0]
                    values = [*counts.tolist(), *concentrations.tolist(), float(dose)]
                    valid = bool(np.all(np.isfinite(values)))
                except (ValueError, FloatingPointError):
                    valid = False
            output_feature = QgsFeature(output_fields)
            if feature.hasGeometry():
                output_feature.setGeometry(feature.geometry())
            output_feature.setAttributes(feature.attributes() + values + [valid])
            sink.addFeature(output_feature, QgsFeatureSink.FastInsert)
            corrected_count += int(valid)
            invalid_count += int(not valid)
            feedback.setProgress(100.0 * (index + 1) / total)
        feedback.pushInfo(
            f"Corrected points: {corrected_count}; invalid/unprocessed points: {invalid_count}."
        )
        return {self.OUTPUT: sink_id}

    def shortHelpString(self):
        return self.tr(
            "Applies total-count dead-time correction, explicit per-window background subtraction, calibrated 3x3 spectral stripping, optional terrain-clearance normalization and sensitivity conversion before gridding. Original fields are preserved and corrected cps, K (%), eU (ppm), eTh (ppm), dose and a validity flag are appended. Every coefficient must come from the detector and survey calibration report."
        )

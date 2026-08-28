"""QGIS Processing wrappers for optional SimPEG 3D inversions."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import numpy as np

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsWkbTypes,
)

from ..dependencies import import_simpeg_stack
from ..inversion_core import (
    full_model,
    joint_full_models,
    run_joint_cross_gradient_inversion,
    run_potential_field_inversion,
    write_mesh_vtk,
)
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER


class PotentialFieldInversionBase(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    DATA_FIELD = "DATA_FIELD"
    UNCERTAINTY_FIELD = "UNCERTAINTY_FIELD"
    ELEVATION_FIELD = "ELEVATION_FIELD"
    TOPOGRAPHY_FIELD = "TOPOGRAPHY_FIELD"
    CELL_XY = "CELL_XY"
    CELL_Z = "CELL_Z"
    DEPTH = "DEPTH"
    PADDING = "PADDING"
    MESH_TYPE = "MESH_TYPE"
    REFINEMENT_LEVELS = "REFINEMENT_LEVELS"
    MAX_CELLS = "MAX_CELLS"
    ITERATIONS = "ITERATIONS"
    LOWER = "LOWER"
    UPPER = "UPPER"
    FIELD_AMPLITUDE = "FIELD_AMPLITUDE"
    FIELD_INCLINATION = "FIELD_INCLINATION"
    FIELD_DECLINATION = "FIELD_DECLINATION"
    DISK_SENSITIVITIES = "DISK_SENSITIVITIES"
    OUTPUT = "OUTPUT"
    KIND = ""

    def group(self):
        return self.tr("3D potential-field inversion")

    def groupId(self):
        return "inversion_3d"

    def createInstance(self):
        return type(self)()

    def tr(self, text):
        return text

    def initAlgorithm(self, config=None):
        del config
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr("Observation point layer"),
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.DATA_FIELD,
                self.tr("Observed data field"),
                parentLayerParameterName=self.INPUT,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.UNCERTAINTY_FIELD,
                self.tr("Standard deviation field (optional)"),
                parentLayerParameterName=self.INPUT,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ELEVATION_FIELD,
                self.tr(
                    "Receiver elevation field (optional; geometry Z or 0 otherwise)"
                ),
                parentLayerParameterName=self.INPUT,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.TOPOGRAPHY_FIELD,
                self.tr("Ground/topographic elevation field (optional)"),
                parentLayerParameterName=self.INPUT,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CELL_XY,
                self.tr("Horizontal cell size"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=250.0,
                minValue=0.001,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.MESH_TYPE,
                self.tr("Mesh type"),
                options=["TensorMesh (uniform)", "TreeMesh (adaptive OcTree)"],
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.REFINEMENT_LEVELS,
                self.tr("TreeMesh padding/refinement levels"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=2,
                minValue=1,
                maxValue=6,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CELL_Z,
                self.tr("Vertical cell size"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=125.0,
                minValue=0.001,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DEPTH,
                self.tr("Model depth"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=3000.0,
                minValue=0.001,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PADDING,
                self.tr("Horizontal padding cells"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=2,
                minValue=0,
                maxValue=20,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_CELLS,
                self.tr("Safety limit: active cells"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=250000,
                minValue=100,
                maxValue=5000000,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ITERATIONS,
                self.tr("Maximum inversion iterations"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=20,
                minValue=1,
                maxValue=100,
            )
        )
        defaults = {
            "gravity": (-1.5, 1.5),
            "susceptibility": (0.0, 1.0),
            "mvi": (-1.0, 1.0),
        }[self.KIND]
        self.addParameter(
            QgsProcessingParameterNumber(
                self.LOWER,
                self.tr("Lower model bound"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=defaults[0],
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.UPPER,
                self.tr("Upper model bound"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=defaults[1],
            )
        )
        if self.KIND != "gravity":
            self.addParameter(
                QgsProcessingParameterNumber(
                    self.FIELD_AMPLITUDE,
                    self.tr("Inducing field intensity (nT)"),
                    type=PROCESSING_NUMBER_DOUBLE,
                    defaultValue=50000.0,
                    minValue=1.0,
                )
            )
            self.addParameter(
                QgsProcessingParameterNumber(
                    self.FIELD_INCLINATION,
                    self.tr("Inducing field inclination (degrees)"),
                    type=PROCESSING_NUMBER_DOUBLE,
                    defaultValue=60.0,
                    minValue=-90.0,
                    maxValue=90.0,
                )
            )
            self.addParameter(
                QgsProcessingParameterNumber(
                    self.FIELD_DECLINATION,
                    self.tr("Inducing field declination (degrees)"),
                    type=PROCESSING_NUMBER_DOUBLE,
                    defaultValue=0.0,
                    minValue=-360.0,
                    maxValue=360.0,
                )
            )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DISK_SENSITIVITIES,
                self.tr(
                    "Store sensitivity matrix on disk (recommended for large jobs)"
                ),
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT, self.tr("Inversion output directory")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        import_simpeg_stack()
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("A valid point observation layer is required.")
        if source.sourceCrs().isGeographic():
            raise QgsProcessingException(
                "3D inversion requires projected metric coordinates. Reproject observations to a local UTM CRS first."
            )
        data_field = self.parameterAsString(parameters, self.DATA_FIELD, context)
        sigma_field = self.parameterAsString(
            parameters, self.UNCERTAINTY_FIELD, context
        )
        elevation_field = self.parameterAsString(
            parameters, self.ELEVATION_FIELD, context
        )
        topography_field = self.parameterAsString(
            parameters, self.TOPOGRAPHY_FIELD, context
        )
        xyz, values, sigmas = [], [], []
        topography = []
        for feature in source.getFeatures():
            if feedback.isCanceled():
                return {}
            try:
                value = float(feature[data_field])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value) or not feature.hasGeometry():
                continue
            point = feature.geometry().asPoint()
            if elevation_field:
                try:
                    elevation = float(feature[elevation_field])
                except (TypeError, ValueError):
                    continue
            else:
                elevation = (
                    float(point.z())
                    if QgsWkbTypes.hasZ(feature.geometry().wkbType())
                    else 0.0
                )
            if sigma_field:
                try:
                    sigma = float(feature[sigma_field])
                except (TypeError, ValueError):
                    continue
            else:
                sigma = max(float(np.nanstd([value])) * 0.05, abs(value) * 0.05, 1.0)
            if sigma <= 0.0 or not math.isfinite(sigma):
                continue
            xyz.append((point.x(), point.y(), elevation))
            if topography_field:
                try:
                    ground = float(feature[topography_field])
                except (TypeError, ValueError):
                    ground = float("nan")
                if math.isfinite(ground):
                    topography.append((point.x(), point.y(), ground))
            values.append(value)
            sigmas.append(sigma)
        if len(values) < 5:
            raise QgsProcessingException(
                "At least five finite observations with positive uncertainty are required."
            )
        values = np.asarray(values, dtype=float)
        if not sigma_field:
            default_sigma = max(float(np.std(values)) * 0.05, 1e-6)
            sigmas = np.full(values.size, default_sigma)
            feedback.pushInfo(
                f"No uncertainty field: using 5% of data standard deviation ({default_sigma:.4g})."
            )
        output = Path(self.parameterAsString(parameters, self.OUTPUT, context))
        output.mkdir(parents=True, exist_ok=True)
        sensitivity_path = (
            output / "sensitivities"
            if self.parameterAsBool(parameters, self.DISK_SENSITIVITIES, context)
            else None
        )
        feedback.pushWarning(
            "Inversion is compute intensive. QGIS may appear busy; the active-cell guard prevents accidental oversized meshes."
        )
        try:
            result = run_potential_field_inversion(
                self.KIND,
                np.asarray(xyz),
                values,
                np.asarray(sigmas),
                cell_xy=self.parameterAsDouble(parameters, self.CELL_XY, context),
                cell_z=self.parameterAsDouble(parameters, self.CELL_Z, context),
                depth=self.parameterAsDouble(parameters, self.DEPTH, context),
                padding=self.parameterAsInt(parameters, self.PADDING, context),
                max_cells=self.parameterAsInt(parameters, self.MAX_CELLS, context),
                iterations=self.parameterAsInt(parameters, self.ITERATIONS, context),
                lower=self.parameterAsDouble(parameters, self.LOWER, context),
                upper=self.parameterAsDouble(parameters, self.UPPER, context),
                field_amplitude=self.parameterAsDouble(
                    parameters, self.FIELD_AMPLITUDE, context
                )
                if self.KIND != "gravity"
                else 50000.0,
                field_inclination=self.parameterAsDouble(
                    parameters, self.FIELD_INCLINATION, context
                )
                if self.KIND != "gravity"
                else 60.0,
                field_declination=self.parameterAsDouble(
                    parameters, self.FIELD_DECLINATION, context
                )
                if self.KIND != "gravity"
                else 0.0,
                sensitivity_path=sensitivity_path,
                topography=np.asarray(topography) if topography else None,
                mesh_type="tree"
                if self.parameterAsInt(parameters, self.MESH_TYPE, context) == 1
                else "tensor",
                refinement_levels=self.parameterAsInt(
                    parameters, self.REFINEMENT_LEVELS, context
                ),
                cancel_callback=feedback.isCanceled,
                progress_callback=lambda iteration: feedback.setProgress(
                    min(
                        99.0,
                        100.0
                        * iteration
                        / max(
                            1, self.parameterAsInt(parameters, self.ITERATIONS, context)
                        ),
                    )
                ),
            )
        except Exception as error:
            raise QgsProcessingException(f"SimPEG inversion failed: {error}") from error
        vtk_base = output / f"{self.KIND}_model"
        write_mesh_vtk(vtk_base, result.mesh, full_model(result))
        with (output / "observed_predicted_residual.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "x",
                    "y",
                    "z",
                    "observed",
                    "standard_deviation",
                    "predicted",
                    "residual",
                ]
            )
            for location, observed, sigma, predicted in zip(
                xyz, values, sigmas, result.predicted
            ):
                writer.writerow(
                    [*location, observed, sigma, predicted, observed - predicted]
                )
        np.savez_compressed(
            output / "inversion_model.npz",
            model=result.model,
            active=result.active,
            predicted=result.predicted,
            observed=values,
            xyz=np.asarray(xyz),
        )
        normalized_rms = float(
            np.sqrt(np.mean(((values - result.predicted) / np.asarray(sigmas)) ** 2))
        )
        summary = {
            "inversion": self.KIND,
            "mesh_type": type(result.mesh).__name__,
            "mesh_cells": int(result.mesh.nC),
            "active_cells": int(np.count_nonzero(result.active)),
            "observations": int(values.size),
            "normalized_rms": normalized_rms,
            "cell_xy": self.parameterAsDouble(parameters, self.CELL_XY, context),
            "cell_z": self.parameterAsDouble(parameters, self.CELL_Z, context),
            "model_depth": self.parameterAsDouble(parameters, self.DEPTH, context),
            "iterations_requested": self.parameterAsInt(
                parameters, self.ITERATIONS, context
            ),
            "bounds": [
                self.parameterAsDouble(parameters, self.LOWER, context),
                self.parameterAsDouble(parameters, self.UPPER, context),
            ],
        }
        (output / "inversion_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        feedback.setProgress(100.0)
        feedback.pushInfo(
            f"Finished {self.KIND}: {np.count_nonzero(result.active):,} active cells; normalized RMS {normalized_rms:.4g}."
        )
        return {self.OUTPUT: str(output)}

    def shortHelpString(self):
        return self.tr(
            "Runs a bounded SimPEG 3D integral inversion on a TensorMesh or adaptive TreeMesh. Outputs VTK, NPZ, JSON QC and observed/predicted/residual CSV. Coordinates must be projected. A ground/topographic elevation field defines active cells; otherwise a flat surface is placed below the lowest receiver. Cancellation is checked between inversion iterations. Treat results as preliminary and test cell size, depth, uncertainty and bounds. SimPEG is an optional open-source dependency installed from requirements-inversion.txt."
        )


class GravityDensityInversionAlgorithm(PotentialFieldInversionBase):
    KIND = "gravity"

    def name(self):
        return "invert_gravity_density_3d"

    def displayName(self):
        return self.tr("3D gravity density inversion (SimPEG)")


class MagneticSusceptibilityInversionAlgorithm(PotentialFieldInversionBase):
    KIND = "susceptibility"

    def name(self):
        return "invert_magnetic_susceptibility_3d"

    def displayName(self):
        return self.tr("3D magnetic susceptibility inversion (SimPEG)")


class MagneticVectorInversionAlgorithm(PotentialFieldInversionBase):
    KIND = "mvi"

    def name(self):
        return "invert_magnetic_vector_3d"

    def displayName(self):
        return self.tr("3D magnetic vector inversion — MVI (SimPEG)")


def _extract_joint_observations(
    source, data_field, sigma_field, elevation_field, feedback
):
    xyz, values, sigmas = [], [], []
    for feature in source.getFeatures():
        if feedback.isCanceled():
            return np.empty((0, 3)), np.empty(0), np.empty(0)
        try:
            value = float(feature[data_field])
        except (TypeError, ValueError):
            continue
        if not feature.hasGeometry() or not math.isfinite(value):
            continue
        point = feature.geometry().asPoint()
        if elevation_field:
            try:
                elevation = float(feature[elevation_field])
            except (TypeError, ValueError):
                continue
        else:
            elevation = (
                float(point.z())
                if QgsWkbTypes.hasZ(feature.geometry().wkbType())
                else 0.0
            )
        if sigma_field:
            try:
                sigma = float(feature[sigma_field])
            except (TypeError, ValueError):
                continue
        else:
            sigma = float("nan")
        xyz.append((point.x(), point.y(), elevation))
        values.append(value)
        sigmas.append(sigma)
    values = np.asarray(values, dtype=float)
    sigmas = np.asarray(sigmas, dtype=float)
    if not sigma_field and values.size:
        sigmas[:] = max(float(np.std(values)) * 0.05, 1e-6)
    valid = np.isfinite(sigmas) & (sigmas > 0.0)
    return np.asarray(xyz, dtype=float)[valid], values[valid], sigmas[valid]


class JointGravityMagneticInversionAlgorithm(QgsProcessingAlgorithm):
    GRAVITY_INPUT = "GRAVITY_INPUT"
    GRAVITY_DATA = "GRAVITY_DATA"
    GRAVITY_SIGMA = "GRAVITY_SIGMA"
    GRAVITY_ELEVATION = "GRAVITY_ELEVATION"
    MAGNETIC_INPUT = "MAGNETIC_INPUT"
    MAGNETIC_DATA = "MAGNETIC_DATA"
    MAGNETIC_SIGMA = "MAGNETIC_SIGMA"
    MAGNETIC_ELEVATION = "MAGNETIC_ELEVATION"
    TOPOGRAPHY_FIELD = "TOPOGRAPHY_FIELD"
    CELL_XY = "CELL_XY"
    CELL_Z = "CELL_Z"
    DEPTH = "DEPTH"
    PADDING = "PADDING"
    MESH_TYPE = "MESH_TYPE"
    REFINEMENT_LEVELS = "REFINEMENT_LEVELS"
    MAX_CELLS = "MAX_CELLS"
    ITERATIONS = "ITERATIONS"
    COUPLING = "COUPLING"
    DENSITY_MIN = "DENSITY_MIN"
    DENSITY_MAX = "DENSITY_MAX"
    SUSCEPTIBILITY_MIN = "SUSCEPTIBILITY_MIN"
    SUSCEPTIBILITY_MAX = "SUSCEPTIBILITY_MAX"
    FIELD_AMPLITUDE = "FIELD_AMPLITUDE"
    FIELD_INCLINATION = "FIELD_INCLINATION"
    FIELD_DECLINATION = "FIELD_DECLINATION"
    DISK_SENSITIVITIES = "DISK_SENSITIVITIES"
    OUTPUT = "OUTPUT"

    def name(self):
        return "invert_joint_gravity_magnetics_3d"

    def displayName(self):
        return self.tr("Joint 3D gravity–magnetics inversion (cross-gradient)")

    def group(self):
        return self.tr("3D potential-field inversion")

    def groupId(self):
        return "inversion_3d"

    def createInstance(self):
        return type(self)()

    def tr(self, text):
        return text

    def initAlgorithm(self, config=None):
        del config
        for prefix, label in (("GRAVITY", "Gravity"), ("MAGNETIC", "Magnetic")):
            input_name = getattr(self, f"{prefix}_INPUT")
            self.addParameter(
                QgsProcessingParameterFeatureSource(
                    input_name,
                    self.tr(f"{label} observation points"),
                    [QgsProcessing.TypeVectorPoint],
                )
            )
            self.addParameter(
                QgsProcessingParameterField(
                    getattr(self, f"{prefix}_DATA"),
                    self.tr(f"{label} observed data field"),
                    parentLayerParameterName=input_name,
                )
            )
            self.addParameter(
                QgsProcessingParameterField(
                    getattr(self, f"{prefix}_SIGMA"),
                    self.tr(f"{label} standard deviation field (optional)"),
                    parentLayerParameterName=input_name,
                    optional=True,
                )
            )
            self.addParameter(
                QgsProcessingParameterField(
                    getattr(self, f"{prefix}_ELEVATION"),
                    self.tr(f"{label} receiver elevation field (optional)"),
                    parentLayerParameterName=input_name,
                    optional=True,
                )
            )
        self.addParameter(
            QgsProcessingParameterField(
                self.TOPOGRAPHY_FIELD,
                self.tr("Ground elevation field from gravity layer (optional)"),
                parentLayerParameterName=self.GRAVITY_INPUT,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CELL_XY,
                self.tr("Horizontal cell size"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=250.0,
                minValue=0.001,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CELL_Z,
                self.tr("Vertical cell size"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=125.0,
                minValue=0.001,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DEPTH,
                self.tr("Model depth"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=3000.0,
                minValue=0.001,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PADDING,
                self.tr("Horizontal padding cells"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=2,
                minValue=0,
                maxValue=20,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.MESH_TYPE,
                self.tr("Mesh type"),
                options=["TensorMesh (uniform)", "TreeMesh (adaptive OcTree)"],
                defaultValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.REFINEMENT_LEVELS,
                self.tr("TreeMesh padding/refinement levels"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=2,
                minValue=1,
                maxValue=6,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_CELLS,
                self.tr("Safety limit: active cells"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=250000,
                minValue=100,
                maxValue=5000000,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ITERATIONS,
                self.tr("Maximum joint iterations"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=10,
                minValue=1,
                maxValue=100,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.COUPLING,
                self.tr("Cross-gradient coupling weight"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=2e12,
                minValue=0.0,
            )
        )
        for name, label, default in (
            (self.DENSITY_MIN, "Minimum density contrast (g/cc)", -1.5),
            (self.DENSITY_MAX, "Maximum density contrast (g/cc)", 1.5),
            (self.SUSCEPTIBILITY_MIN, "Minimum susceptibility (SI)", 0.0),
            (self.SUSCEPTIBILITY_MAX, "Maximum susceptibility (SI)", 1.0),
            (self.FIELD_AMPLITUDE, "Inducing field intensity (nT)", 50000.0),
            (self.FIELD_INCLINATION, "Inducing field inclination (degrees)", 60.0),
            (self.FIELD_DECLINATION, "Inducing field declination (degrees)", 0.0),
        ):
            self.addParameter(
                QgsProcessingParameterNumber(
                    name,
                    self.tr(label),
                    type=PROCESSING_NUMBER_DOUBLE,
                    defaultValue=default,
                )
            )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DISK_SENSITIVITIES,
                self.tr("Store sensitivity matrices on disk"),
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT, self.tr("Joint inversion output directory")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        import_simpeg_stack()
        gravity_source = self.parameterAsSource(parameters, self.GRAVITY_INPUT, context)
        magnetic_source = self.parameterAsSource(
            parameters, self.MAGNETIC_INPUT, context
        )
        if gravity_source is None or magnetic_source is None:
            raise QgsProcessingException(
                "Both gravity and magnetic point layers are required."
            )
        if (
            gravity_source.sourceCrs().isGeographic()
            or magnetic_source.sourceCrs().isGeographic()
        ):
            raise QgsProcessingException(
                "Joint inversion requires projected metric coordinates."
            )
        if gravity_source.sourceCrs() != magnetic_source.sourceCrs():
            raise QgsProcessingException(
                "Gravity and magnetic layers must use the same projected CRS."
            )
        gravity_xyz, gravity_values, gravity_sigma = _extract_joint_observations(
            gravity_source,
            self.parameterAsString(parameters, self.GRAVITY_DATA, context),
            self.parameterAsString(parameters, self.GRAVITY_SIGMA, context),
            self.parameterAsString(parameters, self.GRAVITY_ELEVATION, context),
            feedback,
        )
        magnetic_xyz, magnetic_values, magnetic_sigma = _extract_joint_observations(
            magnetic_source,
            self.parameterAsString(parameters, self.MAGNETIC_DATA, context),
            self.parameterAsString(parameters, self.MAGNETIC_SIGMA, context),
            self.parameterAsString(parameters, self.MAGNETIC_ELEVATION, context),
            feedback,
        )
        if min(gravity_values.size, magnetic_values.size) < 5:
            raise QgsProcessingException(
                "At least five valid observations are required in each dataset."
            )
        topography_field = self.parameterAsString(
            parameters, self.TOPOGRAPHY_FIELD, context
        )
        topography = []
        if topography_field:
            for feature in gravity_source.getFeatures():
                if not feature.hasGeometry():
                    continue
                try:
                    ground = float(feature[topography_field])
                except (TypeError, ValueError):
                    continue
                if math.isfinite(ground):
                    point = feature.geometry().asPoint()
                    topography.append((point.x(), point.y(), ground))
        output = Path(self.parameterAsString(parameters, self.OUTPUT, context))
        output.mkdir(parents=True, exist_ok=True)
        iterations = self.parameterAsInt(parameters, self.ITERATIONS, context)
        try:
            result = run_joint_cross_gradient_inversion(
                gravity_xyz,
                gravity_values,
                gravity_sigma,
                magnetic_xyz,
                magnetic_values,
                magnetic_sigma,
                cell_xy=self.parameterAsDouble(parameters, self.CELL_XY, context),
                cell_z=self.parameterAsDouble(parameters, self.CELL_Z, context),
                depth=self.parameterAsDouble(parameters, self.DEPTH, context),
                padding=self.parameterAsInt(parameters, self.PADDING, context),
                max_cells=self.parameterAsInt(parameters, self.MAX_CELLS, context),
                iterations=iterations,
                coupling_weight=self.parameterAsDouble(
                    parameters, self.COUPLING, context
                ),
                density_bounds=(
                    self.parameterAsDouble(parameters, self.DENSITY_MIN, context),
                    self.parameterAsDouble(parameters, self.DENSITY_MAX, context),
                ),
                susceptibility_bounds=(
                    self.parameterAsDouble(
                        parameters, self.SUSCEPTIBILITY_MIN, context
                    ),
                    self.parameterAsDouble(
                        parameters, self.SUSCEPTIBILITY_MAX, context
                    ),
                ),
                field_amplitude=self.parameterAsDouble(
                    parameters, self.FIELD_AMPLITUDE, context
                ),
                field_inclination=self.parameterAsDouble(
                    parameters, self.FIELD_INCLINATION, context
                ),
                field_declination=self.parameterAsDouble(
                    parameters, self.FIELD_DECLINATION, context
                ),
                topography=np.asarray(topography) if topography else None,
                mesh_type="tree"
                if self.parameterAsInt(parameters, self.MESH_TYPE, context) == 1
                else "tensor",
                refinement_levels=self.parameterAsInt(
                    parameters, self.REFINEMENT_LEVELS, context
                ),
                sensitivity_path=output / "sensitivities"
                if self.parameterAsBool(parameters, self.DISK_SENSITIVITIES, context)
                else None,
                cancel_callback=feedback.isCanceled,
                progress_callback=lambda iteration: feedback.setProgress(
                    min(99.0, 100.0 * iteration / max(1, iterations))
                ),
            )
        except Exception as error:
            raise QgsProcessingException(
                f"Joint SimPEG inversion failed: {error}"
            ) from error
        write_mesh_vtk(
            output / "joint_density_susceptibility",
            result.mesh,
            joint_full_models(result),
        )
        np.savez_compressed(
            output / "joint_inversion_model.npz",
            density=result.density,
            susceptibility=result.susceptibility,
            active=result.active,
            gravity_predicted=result.predicted_gravity,
            magnetic_predicted=result.predicted_magnetics,
        )
        for name, xyz, observed, sigma, predicted in (
            (
                "gravity",
                gravity_xyz,
                gravity_values,
                gravity_sigma,
                result.predicted_gravity,
            ),
            (
                "magnetics",
                magnetic_xyz,
                magnetic_values,
                magnetic_sigma,
                result.predicted_magnetics,
            ),
        ):
            with (output / f"{name}_observed_predicted_residual.csv").open(
                "w", encoding="utf-8-sig", newline=""
            ) as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    [
                        "x",
                        "y",
                        "z",
                        "observed",
                        "standard_deviation",
                        "predicted",
                        "residual",
                    ]
                )
                for location, datum, uncertainty, prediction in zip(
                    xyz, observed, sigma, predicted
                ):
                    writer.writerow(
                        [*location, datum, uncertainty, prediction, datum - prediction]
                    )
        summary = {
            "mesh_type": type(result.mesh).__name__,
            "mesh_cells": int(result.mesh.nC),
            "active_cells": int(np.count_nonzero(result.active)),
            "gravity_normalized_rms": float(
                np.sqrt(
                    np.mean(
                        ((gravity_values - result.predicted_gravity) / gravity_sigma)
                        ** 2
                    )
                )
            ),
            "magnetic_normalized_rms": float(
                np.sqrt(
                    np.mean(
                        (
                            (magnetic_values - result.predicted_magnetics)
                            / magnetic_sigma
                        )
                        ** 2
                    )
                )
            ),
            "cross_gradient_weight": self.parameterAsDouble(
                parameters, self.COUPLING, context
            ),
        }
        (output / "joint_inversion_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        feedback.setProgress(100.0)
        feedback.pushInfo(
            f"Joint inversion completed: {summary['active_cells']:,} active cells; gravity nRMS {summary['gravity_normalized_rms']:.4g}; magnetics nRMS {summary['magnetic_normalized_rms']:.4g}."
        )
        return {self.OUTPUT: str(output)}

    def shortHelpString(self):
        return self.tr(
            "Simultaneously inverts gravity density contrast and magnetic susceptibility on one TensorMesh or adaptive TreeMesh. A cross-gradient term encourages structural similarity without forcing a fixed density-susceptibility ratio. Use compatible projected CRS, defensible uncertainties and several coupling-weight sensitivity runs. Outputs VTK, NPZ, JSON QC and separate residual CSV files."
        )

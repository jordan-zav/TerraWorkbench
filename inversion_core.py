"""Optional SimPEG potential-field inversion engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np


@dataclass
class InversionResult:
    mesh: object
    active: np.ndarray
    model: np.ndarray
    predicted: np.ndarray
    kind: str
    history: list


@dataclass
class JointInversionResult:
    mesh: object
    active: np.ndarray
    density: np.ndarray
    susceptibility: np.ndarray
    predicted_gravity: np.ndarray
    predicted_magnetics: np.ndarray
    history: list


def _next_power_of_two(value):
    return 1 << max(1, int(np.ceil(np.log2(max(2, value)))))


def _mesh_from_data(
    xyz,
    cell_xy,
    cell_z,
    depth,
    padding,
    topography=None,
    mesh_type="tensor",
    refinement_levels=2,
):
    from discretize import TensorMesh, TreeMesh
    from discretize.utils import active_from_xyz

    minimum = np.min(xyz[:, :2], axis=0)
    maximum = np.max(xyz[:, :2], axis=0)
    nx = max(3, int(np.ceil((maximum[0] - minimum[0]) / cell_xy)) + 1 + 2 * padding)
    ny = max(3, int(np.ceil((maximum[1] - minimum[1]) / cell_xy)) + 1 + 2 * padding)
    nz = max(2, int(np.ceil(depth / cell_z)))
    x0 = minimum[0] - padding * cell_xy
    y0 = minimum[1] - padding * cell_xy
    if topography is None:
        surface = float(np.min(xyz[:, 2]) - 0.5 * cell_z)
        topography = np.array(
            [
                [minimum[0], minimum[1], surface],
                [minimum[0], maximum[1], surface],
                [maximum[0], minimum[1], surface],
                [maximum[0], maximum[1], surface],
            ]
        )
    else:
        topography = np.asarray(topography, dtype=float)
        surface = float(np.max(topography[:, 2]) + 0.5 * cell_z)
    z0 = float(np.min(topography[:, 2]) - depth)
    nz = max(nz, int(np.ceil((surface - z0) / cell_z)))
    if mesh_type == "tree":
        nx_tree = _next_power_of_two(nx)
        ny_tree = _next_power_of_two(ny)
        nz_tree = _next_power_of_two(nz)
        mesh = TreeMesh(
            [
                [(cell_xy, nx_tree)],
                [(cell_xy, ny_tree)],
                [(cell_z, nz_tree)],
            ],
            origin=[x0, y0, z0],
            diagonal_balance=True,
        )
        surface_padding = [
            [max(1, int(refinement_levels) - level)] * 3
            for level in range(max(1, int(refinement_levels)))
        ]
        point_padding = [
            max(1, int(refinement_levels) - level)
            for level in range(max(1, int(refinement_levels)))
        ]
        mesh.refine_surface(
            topography,
            level=-1,
            padding_cells_by_level=surface_padding,
            finalize=False,
        )
        mesh.refine_points(
            xyz,
            level=-1,
            padding_cells_by_level=point_padding,
            finalize=True,
        )
    else:
        mesh = TensorMesh(
            [[(cell_xy, nx)], [(cell_xy, ny)], [(cell_z, nz)]],
            origin=[x0, y0, z0],
        )
    active = active_from_xyz(mesh, topography, grid_reference="CC")
    return mesh, active


def run_potential_field_inversion(
    kind,
    xyz,
    observed,
    standard_deviation,
    *,
    cell_xy,
    cell_z,
    depth,
    padding=2,
    max_cells=250_000,
    iterations=20,
    lower=None,
    upper=None,
    field_amplitude=50_000.0,
    field_inclination=60.0,
    field_declination=0.0,
    sensitivity_path=None,
    topography=None,
    mesh_type="tensor",
    refinement_levels=2,
    cancel_callback=None,
    progress_callback=None,
    regularization_norm=2.0,
    irls_iterations=0,
    reference_value=0.0,
):
    """Run compact TensorMesh gravity, susceptibility, or Cartesian MVI."""
    from simpeg import (
        data,
        data_misfit,
        directives,
        inverse_problem,
        inversion,
        maps,
        optimization,
        regularization,
    )
    from simpeg.potential_fields import gravity, magnetics

    xyz = np.asarray(xyz, dtype=float)
    observed = np.asarray(observed, dtype=float)
    standard_deviation = np.asarray(standard_deviation, dtype=float)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or xyz.shape[0] != observed.size:
        raise ValueError("Observation coordinates and data have incompatible shapes.")
    if observed.size < 5:
        raise ValueError("At least five observations are required for inversion.")
    if not np.isfinite(xyz).all() or not np.isfinite(observed).all():
        raise ValueError("Coordinates and observations must be finite.")
    if np.any(~np.isfinite(standard_deviation)) or np.any(standard_deviation <= 0.0):
        raise ValueError("All standard deviations must be finite and positive.")
    if standard_deviation.shape != observed.shape:
        raise ValueError("Standard deviations and observations must have the same shape.")
    if int(iterations) < 1:
        raise ValueError("At least one inversion iteration is required.")
    regularization_norm = float(regularization_norm)
    irls_iterations = int(irls_iterations)
    reference_value = float(reference_value)
    if not 0.0 <= regularization_norm <= 2.0:
        raise ValueError("Regularization norm p must be between 0 and 2.")
    if irls_iterations < 0:
        raise ValueError("IRLS iterations cannot be negative.")
    if regularization_norm < 2.0 and irls_iterations == 0:
        raise ValueError(
            "A regularization norm below 2 requires at least one IRLS iteration."
        )
    mesh, active = _mesh_from_data(
        xyz,
        cell_xy,
        cell_z,
        depth,
        int(padding),
        topography=topography,
        mesh_type=mesh_type,
        refinement_levels=refinement_levels,
    )
    n_active = int(np.count_nonzero(active))
    if n_active == 0:
        raise ValueError("The mesh contains no active cells below topography.")
    if n_active > int(max_cells):
        raise ValueError(
            f"The requested mesh has {n_active:,} active cells; increase cell size or reduce depth (limit {int(max_cells):,})."
        )
    storage = "disk" if sensitivity_path else "ram"
    common = {
        "mesh": mesh,
        "active_cells": active,
        "engine": "choclo",
        "store_sensitivities": storage,
    }
    if sensitivity_path:
        common["sensitivity_path"] = str(sensitivity_path)

    if kind == "gravity":
        receiver = gravity.receivers.Point(xyz, components="gz")
        survey = gravity.survey.Survey(
            gravity.sources.SourceField(receiver_list=[receiver])
        )
        model_map = maps.IdentityMap(nP=n_active)
        simulation = gravity.simulation.Simulation3DIntegral(
            survey=survey, rhoMap=model_map, **common
        )
        regularization_term = regularization.Sparse(
            mesh, active_cells=active, mapping=model_map,
            norms=[regularization_norm] * 4,
            reference_model=np.full(n_active, reference_value),
        ) if irls_iterations > 0 else regularization.WeightedLeastSquares(
            mesh, active_cells=active, mapping=model_map,
            reference_model=np.full(n_active, reference_value),
        )
        default_lower, default_upper = -1.5, 1.5
        start_default = 0.0
    else:
        receiver = magnetics.receivers.Point(xyz, components="tmi")
        source = magnetics.sources.UniformBackgroundField(
            receiver_list=[receiver],
            amplitude=float(field_amplitude),
            inclination=float(field_inclination),
            declination=float(field_declination),
        )
        survey = magnetics.survey.Survey(source)
        if kind == "susceptibility":
            model_map = maps.IdentityMap(nP=n_active)
            simulation = magnetics.simulation.Simulation3DIntegral(
                survey=survey, chiMap=model_map, model_type="scalar", **common
            )
            regularization_term = regularization.Sparse(
                mesh, active_cells=active, mapping=model_map,
                norms=[regularization_norm] * 4,
                reference_model=np.full(n_active, reference_value),
            ) if irls_iterations > 0 else regularization.WeightedLeastSquares(
                mesh, active_cells=active, mapping=model_map,
                reference_model=np.full(n_active, reference_value),
            )
            default_lower, default_upper = 0.0, 1.0
            start_default = 1e-4
        elif kind == "mvi":
            model_map = maps.IdentityMap(nP=3 * n_active)
            simulation = magnetics.simulation.Simulation3DIntegral(
                survey=survey, chiMap=model_map, model_type="vector", **common
            )
            regularization_term = regularization.VectorAmplitude(
                mesh, active_cells=active, mapping=model_map
            )
            start = np.zeros(3 * n_active)
            default_lower, default_upper = -1.0, 1.0
        else:
            raise ValueError(f"Unknown inversion kind: {kind}")

    resolved_lower = default_lower if lower is None else float(lower)
    resolved_upper = default_upper if upper is None else float(upper)
    if not resolved_lower < resolved_upper:
        raise ValueError("The lower model bound must be smaller than the upper bound.")
    if kind != "mvi":
        if not resolved_lower <= reference_value <= resolved_upper:
            raise ValueError("The scalar reference model must lie inside the bounds.")
        start_value = reference_value if reference_value != 0.0 else start_default
        start = np.full(n_active, start_value)

    data_object = data.Data(
        survey, dobs=observed, standard_deviation=standard_deviation
    )
    misfit = data_misfit.L2DataMisfit(data=data_object, simulation=simulation)
    optimizer = optimization.ProjectedGNCG(
        maxIter=int(iterations),
        lower=resolved_lower,
        upper=resolved_upper,
        maxIterLS=20,
        cg_maxiter=20,
        cg_rtol=1e-3,
    )
    problem = inverse_problem.BaseInvProblem(misfit, regularization_term, optimizer)
    directive_list = [
        directives.UpdateSensitivityWeights(every_iteration=False),
        directives.BetaEstimate_ByEig(beta0_ratio=1.0, random_seed=0),
        directives.UpdatePreconditioner(),
        directives.TargetMisfit(chifact=1.0),
    ]
    if kind != "mvi" and irls_iterations > 0:
        directive_list.insert(
            2,
            directives.UpdateIRLS(
                max_irls_iterations=irls_iterations,
                chifact_start=1.0,
                chifact_target=1.0,
            ),
        )
    history = []

    class DiagnosticsDirective(directives.InversionDirective):
        def endIter(self):
            iteration = int(getattr(self.opt, "iter", 0))
            history.append(
                {
                    "iteration": iteration,
                    "phi_d": float(self.invProb.phi_d),
                    "phi_m": float(self.invProb.phi_m),
                    "beta": float(self.invProb.beta),
                }
            )
            if progress_callback is not None:
                progress_callback(iteration)
            if cancel_callback is not None and cancel_callback():
                raise RuntimeError("Inversion canceled by user.")

    directive_list.append(DiagnosticsDirective())
    recovered = inversion.BaseInversion(problem, directiveList=directive_list).run(
        start
    )
    predicted = np.asarray(simulation.dpred(recovered), dtype=float)
    return InversionResult(
        mesh, active, np.asarray(recovered), predicted, kind, history
    )


def run_joint_cross_gradient_inversion(
    gravity_xyz,
    gravity_data,
    gravity_std,
    magnetic_xyz,
    magnetic_data,
    magnetic_std,
    *,
    cell_xy,
    cell_z,
    depth,
    padding=2,
    max_cells=250_000,
    iterations=10,
    coupling_weight=2e12,
    density_bounds=(-1.5, 1.5),
    susceptibility_bounds=(0.0, 1.0),
    field_amplitude=50_000.0,
    field_inclination=60.0,
    field_declination=0.0,
    topography=None,
    mesh_type="tensor",
    refinement_levels=2,
    sensitivity_path=None,
    cancel_callback=None,
    progress_callback=None,
):
    """Jointly invert gravity and TMI using structural cross-gradient coupling."""
    from simpeg import (
        data,
        data_misfit,
        directives,
        inverse_problem,
        inversion,
        maps,
        optimization,
        regularization,
    )
    from simpeg.potential_fields import gravity, magnetics

    gravity_xyz = np.asarray(gravity_xyz, dtype=float)
    magnetic_xyz = np.asarray(magnetic_xyz, dtype=float)
    gravity_data = np.asarray(gravity_data, dtype=float)
    magnetic_data = np.asarray(magnetic_data, dtype=float)
    gravity_std = np.asarray(gravity_std, dtype=float)
    magnetic_std = np.asarray(magnetic_std, dtype=float)
    for label, coordinates, values, uncertainties in (
        ("gravity", gravity_xyz, gravity_data, gravity_std),
        ("magnetic", magnetic_xyz, magnetic_data, magnetic_std),
    ):
        if (
            coordinates.ndim != 2
            or coordinates.shape[1] != 3
            or coordinates.shape[0] != values.size
            or uncertainties.shape != values.shape
        ):
            raise ValueError(f"Incompatible {label} observation array shapes.")
        if (
            not np.isfinite(coordinates).all()
            or not np.isfinite(values).all()
            or not np.isfinite(uncertainties).all()
            or np.any(uncertainties <= 0.0)
        ):
            raise ValueError(
                f"{label.capitalize()} coordinates, data and positive uncertainties must be finite."
            )
    if min(gravity_data.size, magnetic_data.size) < 5:
        raise ValueError(
            "At least five gravity and five magnetic observations are required."
        )
    if int(iterations) < 1:
        raise ValueError("At least one joint inversion iteration is required.")
    if not density_bounds[0] < density_bounds[1]:
        raise ValueError("Density lower bound must be smaller than its upper bound.")
    if not susceptibility_bounds[0] < susceptibility_bounds[1]:
        raise ValueError(
            "Susceptibility lower bound must be smaller than its upper bound."
        )
    combined_xyz = np.vstack([gravity_xyz, magnetic_xyz])
    mesh, active = _mesh_from_data(
        combined_xyz,
        cell_xy,
        cell_z,
        depth,
        int(padding),
        topography=topography,
        mesh_type=mesh_type,
        refinement_levels=refinement_levels,
    )
    n_active = int(np.count_nonzero(active))
    if n_active == 0:
        raise ValueError("The joint mesh contains no active cells below topography.")
    if n_active > int(max_cells):
        raise ValueError(
            f"The requested mesh has {n_active:,} active cells; limit is {int(max_cells):,}."
        )
    wires = maps.Wires(("density", n_active), ("susceptibility", n_active))
    receiver_gravity = gravity.receivers.Point(gravity_xyz, components="gz")
    survey_gravity = gravity.survey.Survey(
        gravity.sources.SourceField(receiver_list=[receiver_gravity])
    )
    receiver_magnetic = magnetics.receivers.Point(magnetic_xyz, components="tmi")
    survey_magnetic = magnetics.survey.Survey(
        magnetics.sources.UniformBackgroundField(
            receiver_list=[receiver_magnetic],
            amplitude=float(field_amplitude),
            inclination=float(field_inclination),
            declination=float(field_declination),
        )
    )
    common = {
        "mesh": mesh,
        "active_cells": active,
        "engine": "choclo",
        "store_sensitivities": "disk" if sensitivity_path else "ram",
    }
    gravity_common = dict(common)
    magnetic_common = dict(common)
    if sensitivity_path:
        gravity_common["sensitivity_path"] = str(sensitivity_path) + "_gravity"
        magnetic_common["sensitivity_path"] = str(sensitivity_path) + "_magnetic"
    simulation_gravity = gravity.simulation.Simulation3DIntegral(
        survey=survey_gravity, rhoMap=wires.density, **gravity_common
    )
    simulation_magnetic = magnetics.simulation.Simulation3DIntegral(
        survey=survey_magnetic,
        chiMap=wires.susceptibility,
        model_type="scalar",
        **magnetic_common,
    )
    gravity_object = data.Data(
        survey_gravity, dobs=gravity_data, standard_deviation=gravity_std
    )
    magnetic_object = data.Data(
        survey_magnetic, dobs=magnetic_data, standard_deviation=magnetic_std
    )
    misfit = data_misfit.L2DataMisfit(
        data=gravity_object, simulation=simulation_gravity
    ) + data_misfit.L2DataMisfit(data=magnetic_object, simulation=simulation_magnetic)
    reg_density = regularization.WeightedLeastSquares(
        mesh, active_cells=active, mapping=wires.density
    )
    reg_susceptibility = regularization.WeightedLeastSquares(
        mesh, active_cells=active, mapping=wires.susceptibility
    )
    coupling = regularization.CrossGradient(mesh, wires, active_cells=active)
    regularization_term = (
        reg_density + reg_susceptibility + float(coupling_weight) * coupling
    )
    lower = np.r_[
        np.full(n_active, float(density_bounds[0])),
        np.full(n_active, float(susceptibility_bounds[0])),
    ]
    upper = np.r_[
        np.full(n_active, float(density_bounds[1])),
        np.full(n_active, float(susceptibility_bounds[1])),
    ]
    start = np.r_[np.zeros(n_active), np.full(n_active, 1e-4)]
    optimizer = optimization.ProjectedGNCG(
        maxIter=int(iterations),
        lower=lower,
        upper=upper,
        maxIterLS=20,
        cg_maxiter=100,
        cg_rtol=1e-3,
        tolX=1e-3,
    )
    problem = inverse_problem.BaseInvProblem(misfit, regularization_term, optimizer)
    directive_list = [
        directives.SimilarityMeasureInversionDirective(),
        directives.UpdateSensitivityWeights(every_iteration=False),
        directives.MovingAndMultiTargetStopping(tol=1e-6),
        directives.PairedBetaEstimate_ByEig(beta0_ratio=1.0),
        directives.PairedBetaSchedule(cooling_factor=5, cooling_rate=1),
        directives.UpdatePreconditioner(),
    ]
    history = []

    class JointProgressDirective(directives.InversionDirective):
        def endIter(self):
            iteration = int(getattr(self.opt, "iter", 0))
            history.append(
                {
                    "iteration": iteration,
                    "phi_d": float(self.invProb.phi_d),
                    "phi_m": float(self.invProb.phi_m),
                }
            )
            if progress_callback is not None:
                progress_callback(iteration)
            if cancel_callback is not None and cancel_callback():
                raise RuntimeError("Joint inversion canceled by user.")

    directive_list.append(JointProgressDirective())
    recovered = inversion.BaseInversion(problem, directiveList=directive_list).run(
        start
    )
    return JointInversionResult(
        mesh=mesh,
        active=active,
        density=np.asarray(wires.density * recovered),
        susceptibility=np.asarray(wires.susceptibility * recovered),
        predicted_gravity=np.asarray(simulation_gravity.dpred(recovered)),
        predicted_magnetics=np.asarray(simulation_magnetic.dpred(recovered)),
        history=history,
    )


def full_model(result, inactive_value=np.nan):
    """Expand an active-cell model to mesh cells; MVI returns amplitude and vectors."""
    count = result.mesh.nC
    if result.kind != "mvi":
        output = np.full(count, inactive_value, dtype=float)
        output[result.active] = result.model
        return {result.kind: output}
    n_active = int(np.count_nonzero(result.active))
    vectors = np.asarray(result.model).reshape((n_active, 3), order="F")
    outputs = {}
    for index, name in enumerate(
        ("magnetization_x", "magnetization_y", "magnetization_z")
    ):
        values = np.full(count, inactive_value, dtype=float)
        values[result.active] = vectors[:, index]
        outputs[name] = values
    amplitude = np.full(count, inactive_value, dtype=float)
    amplitude[result.active] = np.linalg.norm(vectors, axis=1)
    outputs["magnetization_amplitude"] = amplitude
    return outputs


def joint_full_models(result, inactive_value=np.nan):
    """Expand joint active-cell models for VTK export."""
    density = np.full(result.mesh.nC, inactive_value, dtype=float)
    susceptibility = np.full(result.mesh.nC, inactive_value, dtype=float)
    density[result.active] = result.density
    susceptibility[result.active] = result.susceptibility
    return {"density": density, "susceptibility": susceptibility}


def write_mesh_vtk(output_base, mesh, models):
    """Write TensorMesh through discretize or dependency-free TreeMesh legacy VTK."""
    if type(mesh).__name__ != "TreeMesh":
        mesh.write_vtk(str(output_base), models=models)
        return str(output_base)

    path = Path(output_base).with_suffix(".vtk")
    centers = np.asarray(mesh.cell_centers, dtype=float)
    widths = np.asarray(mesh.h_gridded, dtype=float)
    count = int(mesh.nC)
    offsets = np.asarray(
        [
            [-1, -1, -1],
            [1, -1, -1],
            [1, 1, -1],
            [-1, 1, -1],
            [-1, -1, 1],
            [1, -1, 1],
            [1, 1, 1],
            [-1, 1, 1],
        ],
        dtype=float,
    )
    with path.open("w", encoding="ascii", newline="\n") as stream:
        stream.write("# vtk DataFile Version 3.0\n")
        stream.write("TerraWorkbench adaptive TreeMesh\n")
        stream.write("ASCII\nDATASET UNSTRUCTURED_GRID\n")
        stream.write(f"POINTS {count * 8} double\n")
        block_size = 10_000
        for start in range(0, count, block_size):
            end = min(count, start + block_size)
            points = (
                centers[start:end, None, :]
                + 0.5 * widths[start:end, None, :] * offsets[None, :, :]
            ).reshape(-1, 3)
            np.savetxt(stream, points, fmt="%.12g %.12g %.12g")
        stream.write(f"CELLS {count} {count * 9}\n")
        for start in range(0, count, block_size):
            end = min(count, start + block_size)
            indices = np.arange(start * 8, end * 8, dtype=np.int64).reshape(-1, 8)
            cells = np.column_stack([np.full(end - start, 8, dtype=np.int64), indices])
            np.savetxt(stream, cells, fmt="%d")
        stream.write(f"CELL_TYPES {count}\n")
        for start in range(0, count, block_size):
            end = min(count, start + block_size)
            np.savetxt(stream, np.full(end - start, 12, dtype=np.int32), fmt="%d")
        stream.write(f"CELL_DATA {count}\n")
        for name, values in models.items():
            safe_name = "_".join(str(name).split()) or "model"
            array = np.asarray(values, dtype=float).reshape(-1)
            if array.size != count:
                raise ValueError(
                    f"VTK model {name!r} has {array.size} values; expected {count}."
                )
            stream.write(f"SCALARS {safe_name} double 1\nLOOKUP_TABLE default\n")
            np.savetxt(stream, array, fmt="%.12g")
    return str(path)

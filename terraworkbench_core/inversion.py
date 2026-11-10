"""Host-independent, optional SimPEG potential-field inversion engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from ._array_contract import as_array


@dataclass
class InversionResult:
    mesh: object
    active: np.ndarray
    model: np.ndarray
    predicted: np.ndarray
    kind: str
    history: list
    diagnostics: dict = field(default_factory=dict)


@dataclass
class JointInversionResult:
    mesh: object
    active: np.ndarray
    density: np.ndarray
    susceptibility: np.ndarray
    predicted_gravity: np.ndarray
    predicted_magnetics: np.ndarray
    history: list
    diagnostics: dict = field(default_factory=dict)


def _jacobi_optimizer(cancel_callback=None, **kwargs):
    """Require the explicit Jacobi preconditioner, never the BFGS fallback."""
    from simpeg import optimization

    class JacobiProjectedGNCG(optimization.ProjectedGNCG):
        def findSearchDirection(self):
            if cancel_callback is not None and cancel_callback():
                raise RuntimeError("Inversion canceled by user.")
            if getattr(self, "_approxHinv", None) is None:
                raise RuntimeError("Jacobi preconditioner was not initialized.")
            # SimPEG 0.25 scales the active gradient by the inactive CG step.
            # If every cell starts on a bound, that CG step is zero and the
            # optimizer cannot enter the feasible interior. Take a Jacobi
            # preconditioned descent step; line search/projection still apply.
            active = self.activeSet(self.xc)
            if np.all(active) or not np.any(self.g[~active]):
                bound = self.bindingSet(self.xc)
                direction = np.asarray(self.approxHinv * (-self.g)).copy()
                direction[bound] = 0.
                if np.any(direction):
                    self.bound_start_restarts = getattr(self, "bound_start_restarts", 0) + 1
                self.cg_count = 0
                self.cg_abs_resid = float(np.linalg.norm(self.g[~bound]))
                self.cg_rel_resid = 1. if np.any(direction) else 0.
                self.cg_solver_mode = "bound_start_descent" if np.any(direction) else "stationary_no_cg"
                self.cg_true_rel_resid = None
                return direction
            if cancel_callback is None:
                direction = super().findSearchDirection()
                self._record_true_cg_residual(direction, active)
                return direction
            from scipy.sparse.linalg import LinearOperator
            original = self.H

            def product(vector):
                if cancel_callback():
                    raise RuntimeError("Inversion canceled by user during CG.")
                return original @ vector
            self.H = LinearOperator(original.shape, matvec=product, dtype=float)
            try:
                direction = super().findSearchDirection()
                self._record_true_cg_residual(direction, active)
                return direction
            finally:
                self.H = original

        def _record_true_cg_residual(self, direction, active):
            # The SDK adds a separate active-bound gradient step after CG.
            # Audit the inactive CG subproblem, excluding that extra step.
            inactive = ~active
            rhs = (-self.g)*inactive
            residual = (self.H @ (direction*inactive)+self.g)*inactive
            denominator = float(np.linalg.norm(rhs))
            self.cg_solver_mode = "projected_cg"
            self.cg_true_rel_resid = (float(np.linalg.norm(residual)/denominator)
                                      if denominator else None)

    kwargs.setdefault("cg_rtol", 1e-3)
    kwargs.setdefault("cg_atol", 0.0)
    # The SDK also stops at 1000*eps (normally 0.01), regardless of tolG.
    # Respect a tighter requested tolerance; explicit eps remains available
    # for controlled legacy diagnostics.
    requested_g = float(kwargs.get("tolG", JacobiProjectedGNCG.tolG))
    kwargs.setdefault("eps", min(1e-5, requested_g/1000.))
    return JacobiProjectedGNCG(**kwargs)


def _cg_metrics(optimizer):
    """Report inner solve quality separately from outer data fit; JSON safe."""
    relative = float(getattr(optimizer, "cg_rel_resid", np.nan))
    actual = getattr(optimizer, "cg_true_rel_resid", None)
    valid = actual is not None and np.isfinite(actual)
    return {"cg_iterations": int(getattr(optimizer, "cg_count", 0)),
            "cg_relative_residual": relative if np.isfinite(relative) else None,
            "cg_tolerance_met": bool(relative <= optimizer.cg_rtol) if np.isfinite(relative) else None,
            "cg_solver_mode": getattr(optimizer, "cg_solver_mode", None),
            "cg_true_relative_residual": float(actual) if valid else None,
            "cg_true_tolerance_met": bool(valid and actual <= optimizer.cg_rtol) if actual is not None else None}


def _solver_history_metrics(history):
    """Audit every recorded residual norm, separately from outer convergence.

    Preserve raw-only counts for scalar callers. Spherical solves also record
    a Jacobi-energy norm: either failure invalidates the combined summary.
    Missing norms and non-CG bound steps do not imply a successful solve.
    """
    checked = [row["cg_true_tolerance_met"] for row in history
               if row.get("cg_true_tolerance_met") is not None]
    scaled = [row["cg_scaled_tolerance_met"] for row in history
              if row.get("cg_scaled_tolerance_met") is not None]
    combined = [all(norms) for row in history
                if (norms := [row[key] for key in
                              ("cg_true_tolerance_met", "cg_scaled_tolerance_met")
                              if row.get(key) is not None])]
    return {"cg_audited_solves": len(checked),
            "cg_failed_true_tolerance_count": sum(not item for item in checked),
            "cg_audited_scaled_solves": len(scaled),
            "cg_failed_scaled_tolerance_count": sum(not item for item in scaled),
            "cg_failed_either_tolerance_count": sum(not item for item in combined),
            "all_audited_cg_tolerances_met": all(combined) if combined else None,
            "bound_descent_step_count": sum(row.get("cg_solver_mode") == "bound_start_descent"
                                            for row in history),
            "stationary_no_cg_step_count": sum(row.get("cg_solver_mode") == "stationary_no_cg"
                                              for row in history)}


def _joint_hessian_diagonal(problem):
    model = problem.model
    diagonal = problem.beta * problem.reg.deriv2(model).diagonal()
    for weight, misfit in zip(problem.dmisfit.multipliers, problem.dmisfit.objfcts):
        diagonal += 2. * weight * misfit.simulation.getJtJdiag(model, W=misfit.W)
    if not np.isfinite(diagonal).all() or np.any(diagonal <= 0):
        raise RuntimeError("Joint Hessian diagonal must be finite and positive.")
    return diagonal


def _weighted_joint_preconditioner():
    """Use the Hessian's current paired betas and coupling, including L2's 2."""
    from scipy.sparse import diags
    from simpeg import directives

    class WeightedJointPreconditioner(directives.UpdatePreconditioner):
        def initialize(self):
            diagonal = _joint_hessian_diagonal(self.invProb)
            self.opt.approxHinv = diags(1. / diagonal, format="csr")

        def endIter(self):
            self.initialize()

    return WeightedJointPreconditioner()


def _single_hessian_diagonal(problem):
    """Jacobi diagonal of the actual single-data L2 plus current prior Hessian."""
    if hasattr(problem.dmisfit, "objfcts"):
        return _joint_hessian_diagonal(problem)
    diagonal = (2. * problem.dmisfit.simulation.getJtJdiag(problem.model, W=problem.dmisfit.W)
                + problem.beta * problem.reg.deriv2(problem.model).diagonal())
    if not np.isfinite(diagonal).all() or np.any(diagonal <= 0):
        raise RuntimeError("Inversion Hessian diagonal must be finite and positive.")
    return diagonal


def _weighted_single_preconditioner():
    from scipy.sparse import diags
    from simpeg import directives

    class WeightedSinglePreconditioner(directives.UpdatePreconditioner):
        def initialize(self):
            self.opt.approxHinv = diags(1. / _single_hessian_diagonal(self.invProb), format="csr")

        def endIter(self):
            self.initialize()
    return WeightedSinglePreconditioner()


def _cross_gradient(mesh, wires, active, hessian):
    """Keep SimPEG's objective/gradient; use 2 J.T J of its face-pair residuals."""
    from scipy import sparse
    from simpeg.regularization import CrossGradient

    if hessian == "simpeg":
        return CrossGradient(mesh, wires, active_cells=active)

    class GaussNewtonCrossGradient(CrossGradient):
        def deriv2(self, model, v=None):
            if not hasattr(self, "_gn_model") or not np.array_equal(model, self._gn_model):
                u, w = [self._G @ value for value in self.wire_map * model]
                A, G = self._Av, self._G
                P = A @ sparse.diags(w) @ G
                Q = A @ sparse.diags(u) @ G
                # sum_i<j a_i a_j (u_i w_j - u_j w_i)^2 equals the
                # existing cell objective. Differentiate those residuals.
                H11 = G.T @ sparse.diags(A.T @ (A @ w**2)) @ G - P.T @ P
                H22 = G.T @ sparse.diags(A.T @ (A @ u**2)) @ G - Q.T @ Q
                H12 = Q.T @ P - G.T @ sparse.diags(A.T @ (A @ (u*w))) @ G
                self._gn_hessian = 2 * sparse.bmat([[H11, H12], [H12.T, H22]], format="csr")
                self._gn_model = model.copy()
            return self._gn_hessian if v is None else self._gn_hessian @ v

    return GaussNewtonCrossGradient(mesh, wires, active_cells=active)


def _joint_outer_metrics(optimizer, misfits, targets):
    previous = float(np.linalg.norm(optimizer.x_last))
    change = float(np.linalg.norm(optimizer.xc - optimizer.x_last))
    relative = change / previous if previous > 0 else (0. if change == 0 else None)
    target_met = bool(np.all(np.abs(np.asarray(misfits) / targets - 1.) < 0.1))
    converged = (relative is not None and relative <= 1e-6 and target_met
                 and _cg_metrics(optimizer)["cg_tolerance_met"] is True)
    return {"relative_model_change": relative, "data_target_tolerance_met": target_met,
            "outer_convergence_met": bool(converged)}


def _joint_stopping():
    from simpeg import directives

    class JointStopping(directives.MovingAndMultiTargetStopping):
        def endIter(self):
            metrics = _joint_outer_metrics(self.opt, self.invProb.phi_d_list, self.target)
            if metrics["outer_convergence_met"]:
                self.opt.stopNextIteration = True

    return JointStopping(tol=1e-6)


def _model_array(value, count, label):
    array = as_array(value, dtype=float)
    if array.ndim == 0:
        array = np.full(count, float(array))
    if array.shape != (count,) or not np.isfinite(array).all():
        raise ValueError(f"{label} must be finite and scalar or have {count} active-cell values.")
    return array


def _property_bound(value, count, kind, label):
    """Scalar/per-cell bounds; MVI also accepts cell-major Cartesian triples."""
    array = as_array(value, float)
    if kind == "mvi":
        if array.shape == (count,):
            array = np.tile(array, 3)
        elif array.shape == (count, 3):
            array = array.ravel(order="F")
    return _model_array(array, count * (3 if kind == "mvi" else 1), label)


def _scalar_regularizer(mesh, active, mapping, reference, norms, irls_iterations, convention, alphas):
    from simpeg import directives, regularization

    if convention == "cell_difference":
        from .regularization_profiles import build_cell_difference_prior
        return build_cell_difference_prior(mesh, active, reference, norms, alphas)
    term = regularization.Sparse(
        mesh, active_cells=active, mapping=mapping, norms=norms, reference_model=reference,
    ) if irls_iterations > 0 else regularization.WeightedLeastSquares(
        mesh, active_cells=active, mapping=mapping, reference_model=reference,
    )
    return term, directives.UpdateSensitivityWeights(every_iteration=False)


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
    max_mesh_cells=2_000_000,
):
    from discretize import TensorMesh, TreeMesh
    from discretize.utils import active_from_xyz
    from ._calibration import integer_budget

    integer_budget(max_mesh_cells, "max_mesh_cells")

    if mesh_type not in ("tensor", "tree"):
        raise ValueError("Mesh type must be tensor or tree.")
    if any(not np.isfinite(v) or v <= 0 for v in (cell_xy, cell_z, depth)):
        raise ValueError("Cell dimensions and depth must be finite and positive.")
    if padding < 0:
        raise ValueError("Padding cannot be negative.")

    minimum = np.min(xyz[:, :2], axis=0)
    maximum = np.max(xyz[:, :2], axis=0)
    nx = max(3, int(np.ceil((maximum[0] - minimum[0]) / cell_xy)) + 1 + 2 * padding)
    ny = max(3, int(np.ceil((maximum[1] - minimum[1]) / cell_xy)) + 1 + 2 * padding)
    nz = max(2, int(np.ceil(depth / cell_z)))
    x0 = minimum[0] - padding * cell_xy
    y0 = minimum[1] - padding * cell_xy
    if topography is None:
        surface = float(np.min(xyz[:, 2]) - 0.5 * cell_z)
        corner_min = minimum.copy()
        corner_max = maximum.copy()
        degenerate = corner_max == corner_min
        corner_min[degenerate] -= 0.5 * cell_xy
        corner_max[degenerate] += 0.5 * cell_xy
        topography = np.array(
            [
                [corner_min[0], corner_min[1], surface],
                [corner_min[0], corner_max[1], surface],
                [corner_max[0], corner_min[1], surface],
                [corner_max[0], corner_max[1], surface],
            ]
        )
    else:
        topography = as_array(topography, dtype=float)
        if topography.ndim != 2 or topography.shape[1] != 3 or not np.isfinite(topography).all():
            raise ValueError("Topography must contain finite XYZ coordinates.")
        surface = float(np.max(topography[:, 2]) + 0.5 * cell_z)
    z0 = float(np.min(topography[:, 2]) - depth)
    nz = max(nz, int(np.ceil((surface - z0) / cell_z)))
    if mesh_type == "tensor" and nx * ny * nz > max_mesh_cells:
        raise ValueError("Tensor mesh allocation exceeds max_mesh_cells before construction.")
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
    if mesh.nC > max_mesh_cells:
        raise ValueError("Mesh exceeds max_mesh_cells before topographic activation.")
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
    reference_model=None,
    starting_model=None,
    regularization_norms=None,
    beta_cooling_factor=2.0,
    beta_cooling_rate=1,
    target_chi=1.0,
    mesh=None,
    active_cells=None,
    sensitivity_dtype="float64",
    max_sensitivity_bytes=512 * 1024**2,
    regularization_weights=None,
    reference_in_smooth=False,
    beta0_ratio=1.0,
    cg_maxiter=20,
    gravity_component="up",
    cg_rtol=1e-3,
    mvi_regularization="amplitude",
    max_mesh_cells=2_000_000,
    sensitivity_mode="auto",
    cell_weights=None,
    optimizer_tol_f=1e-6,
    optimizer_tol_x=1e-8,
    optimizer_tol_g=1e-6,
    beta_seed=0,
    regularization_convention="physical_gradient",
    mvi_parameterization="cartesian",
    mvi_cartesian_iterations=20,
    mvi_amplitude_max=1.0,
    mvi_angle_norms=None,
    mvi_sensitivity_weights="component_approximation",
    mvi_irls_update="adaptive",
):
    """Run gravity, susceptibility, Cartesian or staged spherical MVI.

    Gravity observations and returned predictions use gravity_component. The
    default is the historical SimPEG positive-up convention; down is explicit.
    """
    if mvi_parameterization not in ("cartesian", "spherical") or (kind != "mvi" and mvi_parameterization != "cartesian"):
        raise ValueError("Spherical parameterization applies only to MVI.")
    if mvi_parameterization == "spherical":
        parameters = locals().copy()
        for key in ("kind", "xyz", "observed", "standard_deviation", "mvi_parameterization"):
            parameters.pop(key)
        from .spherical_mvi import run_spherical_mvi
        return run_spherical_mvi(xyz, observed, standard_deviation, **parameters)
    if (mvi_angle_norms is not None or mvi_irls_update != "adaptive" or mvi_sensitivity_weights != "component_approximation" or mvi_cartesian_iterations != 20
            or np.ndim(mvi_amplitude_max) != 0 or mvi_amplitude_max != 1.0):
        raise ValueError("Spherical controls require mvi_parameterization spherical.")
    from ._calibration import integer_budget
    integer_budget(max_mesh_cells, "max_mesh_cells")
    integer_budget(beta_seed, "beta_seed", 0)
    if regularization_convention not in ("physical_gradient", "cell_difference"):
        raise ValueError("Unknown regularization convention.")
    if regularization_convention == "cell_difference" and (kind not in ("gravity", "susceptibility") or regularization_weights is None):
        raise ValueError("Cell-difference regularization requires a scalar inversion and four explicit alpha coefficients.")
    optimizer_tolerances = dict(f=optimizer_tol_f, x=optimizer_tol_x, g=optimizer_tol_g)
    if not all(isinstance(value, (int, float, np.integer, np.floating))
               and not isinstance(value, (bool, np.bool_))
               and np.isfinite(value) and value > 0
               for value in optimizer_tolerances.values()):
        raise ValueError("Optimizer tolerances must be finite positive numbers.")
    if max_sensitivity_bytes is not None:
        integer_budget(max_sensitivity_bytes, "max_sensitivity_bytes", 0)
    from simpeg import (
        data,
        data_misfit,
        directives,
        inverse_problem,
        inversion,
        maps,
        regularization,
    )
    from simpeg.potential_fields import gravity, magnetics

    xyz = as_array(xyz, dtype=float)
    if mvi_regularization not in ("amplitude", "vector_smooth", "componentwise") or (kind != "mvi" and mvi_regularization != "amplitude"):
        raise ValueError("MVI regularization must be amplitude, vector_smooth or componentwise, and applies only to MVI.")
    observed = as_array(observed, dtype=float)
    if gravity_component not in ("up", "down") or (kind != "gravity" and gravity_component != "up"):
        raise ValueError("gravity_component must be up/down for gravity; other kinds use the default up.")
    gravity_sign = -1.0 if kind == "gravity" and gravity_component == "down" else 1.0
    standard_deviation = as_array(standard_deviation, dtype=float)
    if observed.ndim != 1 or xyz.ndim != 2 or xyz.shape[1] != 3 or xyz.shape[0] != observed.size:
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
    norms = as_array([regularization_norm] * 4 if regularization_norms is None else regularization_norms, dtype=float)
    if norms.shape != (4,) or not np.isfinite(norms).all() or np.any((norms < 0) | (norms > 2)):
        raise ValueError("Regularization norms must be four finite values between 0 and 2.")
    if not 0.0 <= regularization_norm <= 2.0:
        raise ValueError("Regularization norm p must be between 0 and 2.")
    if irls_iterations < 0:
        raise ValueError("IRLS iterations cannot be negative.")
    if np.any(norms < 2.0) and irls_iterations == 0:
        raise ValueError(
            "A regularization norm below 2 requires at least one IRLS iteration."
        )
    if not np.isfinite(target_chi) or target_chi <= 0:
        raise ValueError("Target chi must be finite and positive.")
    if not np.isfinite(beta_cooling_factor) or beta_cooling_factor <= 1 or int(beta_cooling_rate) < 1:
        raise ValueError("Beta cooling requires a factor above one and positive rate.")
    if cancel_callback is not None and cancel_callback():
        raise RuntimeError("Inversion canceled by user.")
    weights = as_array([1., 1., 1., 1.] if regularization_weights is None else regularization_weights, dtype=float)
    if weights.shape != (4,) or not np.isfinite(weights).all() or np.any(weights < 0) or not np.any(weights > 0):
        raise ValueError("Regularization weights must be four nonnegative finite values with at least one positive.")
    if not np.isfinite(beta0_ratio) or beta0_ratio <= 0 or int(cg_maxiter) < 1:
        raise ValueError("Beta ratio and CG iteration limit must be positive.")
    if not np.isfinite(cg_rtol) or not 0 < cg_rtol <= 1:
        raise ValueError("CG relative tolerance must be finite and in (0, 1].")
    if mesh is None:
        if active_cells is not None:
            raise ValueError("Active cells require a supplied mesh.")
        mesh, active = _mesh_from_data(
            xyz, cell_xy, cell_z, depth, int(padding), topography=topography,
            mesh_type=mesh_type, refinement_levels=refinement_levels, max_mesh_cells=max_mesh_cells,
        )
    else:
        active = as_array(active_cells)
        if active.dtype != np.dtype(bool) or active.shape != (mesh.nC,):
            raise ValueError("A supplied mesh requires a boolean active_cells mask of mesh.nC values.")
    if mesh.dim != 3 or mesh.nC > max_mesh_cells:
        raise ValueError("Supply a three-dimensional mesh within max_mesh_cells.")
    n_active = int(np.count_nonzero(active))
    if n_active == 0:
        raise ValueError("The mesh contains no active cells below topography.")
    if n_active > int(max_cells):
        raise ValueError(
            f"The requested mesh has {n_active:,} active cells; increase cell size or reduce depth (limit {int(max_cells):,})."
        )
    if sensitivity_mode not in ("auto", "ram", "disk", "matrix_free"):
        raise ValueError("Sensitivity mode must be auto, ram, disk or matrix_free.")
    storage = ("disk" if sensitivity_path else "ram") if sensitivity_mode == "auto" else ("forward_only" if sensitivity_mode == "matrix_free" else sensitivity_mode)
    if storage == "disk" and not sensitivity_path:
        raise ValueError("Disk sensitivity mode requires sensitivity_path.")
    if storage == "forward_only" and sensitivity_path:
        raise ValueError("Matrix-free mode cannot use a sensitivity storage path.")
    dtype = np.dtype(sensitivity_dtype)
    if dtype not in (np.dtype("float32"), np.dtype("float64")):
        raise ValueError("Sensitivity dtype must be float32 or float64.")
    sensitivity_bytes = observed.size * n_active * (3 if kind == "mvi" else 1) * dtype.itemsize
    if storage != "forward_only" and max_sensitivity_bytes is not None and sensitivity_bytes > int(max_sensitivity_bytes):
        raise ValueError(f"Sensitivity matrix requires {sensitivity_bytes} bytes, above the configured limit. Use matrix_free mode or an explicit larger storage budget.")
    reference = None if kind == "mvi" else _model_array(reference_value if reference_model is None else reference_model,
                             n_active, "Reference model")
    common = {
        "mesh": mesh,
        "active_cells": active,
        "engine": "choclo",
        "store_sensitivities": storage,
        "sensitivity_dtype": dtype.type,
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
        regularization_term, sensitivity_update = _scalar_regularizer(
            mesh, active, model_map, reference, norms, irls_iterations, regularization_convention, weights,
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
            regularization_term, sensitivity_update = _scalar_regularizer(
                mesh, active, model_map, reference, norms, irls_iterations, regularization_convention, weights,
            )
            default_lower, default_upper = 0.0, 1.0
            start_default = 1e-4
        elif kind == "mvi":
            sensitivity_update = directives.UpdateSensitivityWeights(every_iteration=False)
            if reference_value != 0. or (reference_in_smooth and reference_model is None):
                raise ValueError("MVI requires an explicit Cartesian vector reference; scalar reference controls do not apply.")
            def vector_array(value, label):
                from ._array_contract import as_array
                array = as_array(value, float)
                if array.shape == (n_active, 3):
                    array = array.ravel(order="F")
                if array.shape != (3*n_active,) or not np.isfinite(array).all():
                    raise ValueError(f"MVI {label} must be finite (n_active,3) or component-major 3*n_active values.")
                return array.copy()
            reference = np.zeros(3*n_active) if reference_model is None else vector_array(reference_model, "reference")
            model_map = maps.IdentityMap(nP=3 * n_active)
            simulation = magnetics.simulation.Simulation3DIntegral(
                survey=survey, chiMap=model_map, model_type="vector", **common
            )
            regularization_term = regularization.VectorAmplitude(
                mesh, active_cells=active, mapping=model_map, reference_model=reference, norms=norms,
                reference_model_in_smooth=bool(reference_in_smooth),
            )
            if mvi_regularization in ("vector_smooth", "componentwise"):
                # Group-amplitude smallness preserves a common compact support;
                # component smoothness also penalizes rapid direction changes.
                amplitude = regularization_term
                if mvi_regularization == "vector_smooth":
                    amplitude.norms = np.r_[norms[0], 2., 2., 2.]
                    amplitude.alpha_x = amplitude.alpha_y = amplitude.alpha_z = 0.
                wires = maps.Wires(("x", n_active), ("y", n_active), ("z", n_active))
                components = [regularization.Sparse(mesh, active_cells=active, mapping=getattr(wires, axis),
                                                    reference_model=reference, norms=norms if mvi_regularization == "componentwise" else np.r_[2., norms[1:]])
                              for axis in ("x", "y", "z")]
                for component in components:
                    if mvi_regularization == "vector_smooth":
                        component.alpha_s = 0.
                    component.reference_model_in_smooth = bool(reference_in_smooth)
                regularization_term = components[0] + components[1] + components[2]
                if mvi_regularization == "vector_smooth":
                    regularization_term = amplitude + regularization_term
            start = np.zeros(3 * n_active) if starting_model is None else vector_array(starting_model, "starting model")
            from scipy.constants import mu_0
            magnetization_scale = float(field_amplitude)*1e-9/mu_0
            default_lower, default_upper = -1.0, 1.0
        else:
            raise ValueError(f"Unknown inversion kind: {kind}")

    if kind != "mvi":
        regularization_term.reference_model_in_smooth = bool(reference_in_smooth)
    if kind == "mvi" and mvi_regularization == "vector_smooth":
        if regularization_weights is not None:
            amplitude.alpha_s = float(weights[0])
            for component in components:
                for axis, weight in zip(("x", "y", "z"), weights[1:]):
                    setattr(component, "alpha_"+axis, float(weight))
        weights = np.r_[amplitude.alpha_s, [getattr(components[0], "alpha_"+axis) for axis in ("x", "y", "z")]]
    elif kind == "mvi" and mvi_regularization == "componentwise":
        if regularization_weights is not None:
            for component in components:
                for axis, weight in zip("sxyz", weights):
                    setattr(component, "alpha_"+axis, float(weight))
        weights = np.array([getattr(components[0], "alpha_"+axis) for axis in "sxyz"])
    elif regularization_weights is not None:
        for axis, weight in zip(("s", "x", "y", "z"), weights):
            setattr(regularization_term, "alpha_" + axis, float(weight))
    if not (kind == "mvi" and mvi_regularization in ("vector_smooth", "componentwise")):
        weights = np.array([getattr(regularization_term, "alpha_" + axis) for axis in ("s", "x", "y", "z")])

    if cell_weights is not None:
        spatial_weights = _model_array(cell_weights, n_active, "Cell weights")
        if np.any(spatial_weights <= 0):
            raise ValueError("Cell weights must be positive; use fixed bounds for exclusions.")
        terms = [amplitude, *components] if kind == "mvi" and mvi_regularization == "vector_smooth" else (components if kind == "mvi" and mvi_regularization == "componentwise" else [regularization_term])
        for term in terms:
            term.set_weights(geological_prior=spatial_weights)
    resolved_lower = _property_bound(default_lower if lower is None else lower, n_active, kind, "Lower bounds")
    resolved_upper = _property_bound(default_upper if upper is None else upper, n_active, kind, "Upper bounds")
    if np.any(resolved_lower > resolved_upper) or not np.any(resolved_lower < resolved_upper):
        raise ValueError("The lower model bound must be smaller than the upper bound for at least one free parameter, and may not exceed it elsewhere.")
    if kind != "mvi":
        if np.any(reference < resolved_lower) or np.any(reference > resolved_upper):
            raise ValueError("The scalar reference model must lie inside the bounds.")
        if starting_model is not None:
            start = _model_array(starting_model, n_active, "Starting model")
        elif reference_model is not None or reference_value != 0.0:
            start = reference.copy()
        else:
            start = np.clip(np.full(n_active, start_default), resolved_lower, resolved_upper)
        if np.any(start < resolved_lower) or np.any(start > resolved_upper):
            raise ValueError("Starting model must lie inside the bounds.")
    elif np.any(reference < resolved_lower) or np.any(reference > resolved_upper) or np.any(start < resolved_lower) or np.any(start > resolved_upper):
        raise ValueError("MVI vector reference and starting model must lie inside bounds.")

    data_object = data.Data(
        survey, dobs=gravity_sign * observed, standard_deviation=standard_deviation
    )
    misfit = data_misfit.L2DataMisfit(data=data_object, simulation=simulation)
    optimizer = _jacobi_optimizer(
        cancel_callback=cancel_callback,
        maxIter=int(iterations),
        lower=resolved_lower,
        upper=resolved_upper,
        maxIterLS=20,
        cg_maxiter=int(cg_maxiter),
        cg_rtol=float(cg_rtol),
        tolX=float(optimizer_tol_x),
        tolF=float(optimizer_tol_f),
        tolG=float(optimizer_tol_g),
    )
    problem = inverse_problem.BaseInvProblem(misfit, regularization_term, optimizer, init_bfgs=False)
    directive_list = [
        sensitivity_update,
        directives.BetaEstimate_ByEig(beta0_ratio=float(beta0_ratio), random_seed=int(beta_seed)),
    ]
    if irls_iterations > 0:
        directive_list.insert(
            2,
            directives.UpdateIRLS(
                max_irls_iterations=irls_iterations,
                chifact_start=target_chi,
                chifact_target=target_chi,
                cooling_factor=beta_cooling_factor,
                cooling_rate=int(beta_cooling_rate),
            ),
        )
    else:
        directive_list.extend([
            directives.BetaSchedule(coolingFactor=beta_cooling_factor, coolingRate=int(beta_cooling_rate)),
            directives.TargetMisfit(chifact=target_chi),
        ])
    # Refresh after beta cooling/IRLS changes, not before the next Hessian's
    # weights have been selected.
    directive_list.append(_weighted_single_preconditioner())
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
                    **_cg_metrics(self.opt),
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
    predicted = gravity_sign * np.asarray(simulation.dpred(recovered), dtype=float)
    if cancel_callback is not None and cancel_callback():
        raise RuntimeError("Inversion canceled by user.")
    if not np.isfinite(recovered).all() or not np.isfinite(predicted).all():
        raise RuntimeError("Inversion returned a non-finite model or prediction.")
    wrms = float(np.sqrt(np.mean(((observed - predicted) / standard_deviation) ** 2)))
    irls = next((d for d in directive_list if isinstance(d, directives.UpdateIRLS)), None)
    return InversionResult(mesh, active, np.asarray(recovered), predicted, kind, history,
                           {"weighted_rms": wrms, "target_chi": target_chi,
                            "gravity_component": gravity_component if kind == "gravity" else None,
                            "bound_start_restarts": int(getattr(optimizer, "bound_start_restarts", 0)),
                            "iteration_limit_reached": int(optimizer.iter) >= int(iterations),
                            "cg_maxiter": int(cg_maxiter), "cg_rtol": float(cg_rtol),
                            **_cg_metrics(optimizer),
                            **_solver_history_metrics(history),
                            "target_reached": wrms ** 2 <= target_chi,
                            "init_bfgs": False, "preconditioner": "Jacobi",
                            "optimizer_tolerances": {key: float(value) for key, value in optimizer_tolerances.items()},
                            "beta_seed": int(beta_seed),
                            "preconditioner_hessian": "2 J.T Wd^2 J + beta R''; current weights",
                            "regularization_norms": norms.tolist(),
                            "regularization_convention": regularization_convention,
                            "regularization_weights": weights.tolist(),
                            "reference_in_smooth": bool(reference_in_smooth),
                            "mvi_regularization": mvi_regularization if kind == "mvi" else None,
                            "mvi_parameterization": "cartesian" if kind == "mvi" else None,
                            "final_beta": float(problem.beta),
                            "model_units": "effective susceptibility SI" if kind == "mvi" else ("g/cm^3" if kind == "gravity" else "SI"),
                            "fixed_parameter_count": int(np.sum(resolved_lower == resolved_upper)),
                            "free_parameter_count": int(np.sum(resolved_lower < resolved_upper)),
                            "geological_cell_weights_supplied": cell_weights is not None,
                            "geological_cell_weight_range": None if cell_weights is None else [float(spatial_weights.min()), float(spatial_weights.max())],
                            "mvi_layout": "component-major x,y,z; positive-up z" if kind == "mvi" else None,
                            "magnetization_a_per_m_per_si": magnetization_scale if kind == "mvi" else None,
                            "sensitivity_bytes": int(sensitivity_bytes),
                            "sensitivity_mode": "matrix_free" if storage == "forward_only" else storage,
                            "stored_sensitivity_bytes": 0 if storage == "forward_only" else int(sensitivity_bytes),
                            "field": {"amplitude": float(field_amplitude), "inclination": float(field_inclination), "declination": float(field_declination)},
                            "irls_iterations": 0 if irls is None else int(irls.metrics.irls_iteration_count),
                            "iterations": int(optimizer.iter)})


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
    gravity_component="up",
    mesh=None,
    active_cells=None,
    starting_density=0.0,
    starting_susceptibility=1e-4,
    sensitivity_dtype="float32",
    max_sensitivity_bytes=512 * 1024**2,
    cg_maxiter=100,
    cg_rtol=1e-3,
    reference_density=None,
    reference_susceptibility=None,
    cross_gradient_hessian="gauss_newton",
    max_mesh_cells=2_000_000,
    sensitivity_mode="auto",
):
    """Jointly invert gravity and TMI using structural cross-gradient coupling.

    Gravity observations/predictions follow the declared up/down component.
    """
    from ._calibration import integer_budget
    integer_budget(max_mesh_cells, "max_mesh_cells")
    if max_sensitivity_bytes is not None:
        integer_budget(max_sensitivity_bytes, "max_sensitivity_bytes", 0)
    from simpeg import (
        data,
        data_misfit,
        directives,
        inverse_problem,
        inversion,
        maps,
        regularization,
    )
    from simpeg.potential_fields import gravity, magnetics

    gravity_xyz = as_array(gravity_xyz, dtype=float)
    magnetic_xyz = as_array(magnetic_xyz, dtype=float)
    gravity_data = as_array(gravity_data, dtype=float)
    if gravity_component not in ("up", "down"):
        raise ValueError("gravity_component must be up or down.")
    gravity_sign = -1.0 if gravity_component == "down" else 1.0
    if not np.isfinite(coupling_weight) or coupling_weight < 0:
        raise ValueError("Cross-gradient coupling must be finite and nonnegative.")
    magnetic_data = as_array(magnetic_data, dtype=float)
    gravity_std = as_array(gravity_std, dtype=float)
    magnetic_std = as_array(magnetic_std, dtype=float)
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
    if int(cg_maxiter) < 1 or not np.isfinite(cg_rtol) or not 0 < cg_rtol <= 1:
        raise ValueError("CG needs a positive iteration limit and relative tolerance in (0, 1].")
    if cross_gradient_hessian not in ("gauss_newton", "simpeg"):
        raise ValueError("Cross-gradient Hessian must be gauss_newton or simpeg.")
    if not density_bounds[0] < density_bounds[1]:
        raise ValueError("Density lower bound must be smaller than its upper bound.")
    if not susceptibility_bounds[0] < susceptibility_bounds[1]:
        raise ValueError(
            "Susceptibility lower bound must be smaller than its upper bound."
        )
    combined_xyz = np.vstack([gravity_xyz, magnetic_xyz])
    if mesh is None:
        if active_cells is not None:
            raise ValueError("Active cells require a supplied mesh.")
        mesh, active = _mesh_from_data(
            combined_xyz, cell_xy, cell_z, depth, int(padding),
            topography=topography, mesh_type=mesh_type,
            refinement_levels=refinement_levels, max_mesh_cells=max_mesh_cells,
        )
    else:
        active = as_array(active_cells)
        if active.dtype != np.dtype(bool) or active.shape != (mesh.nC,):
            raise ValueError("A supplied mesh requires a boolean active_cells mask of mesh.nC values.")
    if mesh.dim != 3 or mesh.nC > max_mesh_cells:
        raise ValueError("Supply a three-dimensional mesh within max_mesh_cells.")
    n_active = int(np.count_nonzero(active))
    if n_active == 0:
        raise ValueError("The joint mesh contains no active cells below topography.")
    if n_active > int(max_cells):
        raise ValueError(
            f"The requested mesh has {n_active:,} active cells; limit is {int(max_cells):,}."
        )
    dtype = np.dtype(sensitivity_dtype)
    if dtype not in (np.dtype("float32"), np.dtype("float64")):
        raise ValueError("Sensitivity dtype must be float32 or float64.")
    sensitivity_bytes = (gravity_data.size + magnetic_data.size) * n_active * dtype.itemsize
    if sensitivity_mode not in ("auto", "ram", "disk", "matrix_free"):
        raise ValueError("Sensitivity mode must be auto, ram, disk or matrix_free.")
    storage = ("disk" if sensitivity_path else "ram") if sensitivity_mode == "auto" else ("forward_only" if sensitivity_mode == "matrix_free" else sensitivity_mode)
    if storage == "disk" and not sensitivity_path:
        raise ValueError("Disk sensitivity mode requires sensitivity_path.")
    if storage == "forward_only" and sensitivity_path:
        raise ValueError("Matrix-free mode cannot use a sensitivity storage path.")
    if storage != "forward_only" and max_sensitivity_bytes is not None and sensitivity_bytes > int(max_sensitivity_bytes):
        raise ValueError(f"Sensitivity matrices require {sensitivity_bytes} bytes, above the configured limit.")
    start_density = _model_array(starting_density, n_active, "Starting density")
    start_susceptibility = _model_array(starting_susceptibility, n_active, "Starting susceptibility")
    for values, bounds in ((start_density, density_bounds), (start_susceptibility, susceptibility_bounds)):
        if np.any(values < bounds[0]) or np.any(values > bounds[1]):
            raise ValueError("Starting models must lie inside their bounds.")
    explicit_reference = reference_density is not None or reference_susceptibility is not None
    reference = np.r_[
        _model_array(start_density if reference_density is None else reference_density, n_active, "Reference density"),
        _model_array(start_susceptibility if reference_susceptibility is None else reference_susceptibility, n_active, "Reference susceptibility"),
    ] if explicit_reference else None
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
        "store_sensitivities": storage,
        "sensitivity_dtype": dtype.type,
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
        survey_gravity, dobs=gravity_sign * gravity_data, standard_deviation=gravity_std
    )
    magnetic_object = data.Data(
        survey_magnetic, dobs=magnetic_data, standard_deviation=magnetic_std
    )
    misfit = data_misfit.L2DataMisfit(
        data=gravity_object, simulation=simulation_gravity
    ) + data_misfit.L2DataMisfit(data=magnetic_object, simulation=simulation_magnetic)
    reg_density = regularization.WeightedLeastSquares(
        mesh, active_cells=active, mapping=wires.density, reference_model=reference
    )
    reg_susceptibility = regularization.WeightedLeastSquares(
        mesh, active_cells=active, mapping=wires.susceptibility, reference_model=reference
    )
    coupling = _cross_gradient(mesh, wires, active, cross_gradient_hessian)
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
    start = np.r_[start_density, start_susceptibility]
    optimizer = _jacobi_optimizer(
        cancel_callback=cancel_callback,
        maxIter=int(iterations),
        lower=lower,
        upper=upper,
        maxIterLS=20,
        cg_maxiter=int(cg_maxiter),
        cg_rtol=float(cg_rtol),
        tolX=1e-3,
    )
    problem = inverse_problem.BaseInvProblem(misfit, regularization_term, optimizer, init_bfgs=False)
    directive_list = [
        directives.SimilarityMeasureInversionDirective(),
        directives.UpdateSensitivityWeights(every_iteration=False),
        _joint_stopping(),
        directives.PairedBetaEstimate_ByEig(beta0_ratio=1.0, seed=0),
        directives.PairedBetaSchedule(cooling_factor=5, cooling_rate=1),
        _weighted_joint_preconditioner(),
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
                    **_cg_metrics(self.opt),
                    **_joint_outer_metrics(self.opt, self.invProb.phi_d_list,
                                          np.array([len(gravity_data), len(magnetic_data)])),
                    "next_paired_betas": [float(value) for value in self.invProb.betas],
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
    if not history:
        raise RuntimeError("Joint inversion stopped before completing an iteration.")
    density = np.asarray(wires.density * recovered)
    susceptibility = np.asarray(wires.susceptibility * recovered)
    predicted_gravity = gravity_sign * np.asarray(simulation_gravity.dpred(recovered))
    predicted_magnetics = np.asarray(simulation_magnetic.dpred(recovered))
    if any(not np.isfinite(v).all() for v in (density, susceptibility, predicted_gravity, predicted_magnetics)):
        raise RuntimeError("Joint inversion returned a non-finite model or prediction.")
    gravity_wrms = float(np.sqrt(np.mean(((gravity_data-predicted_gravity)/gravity_std)**2)))
    magnetic_wrms = float(np.sqrt(np.mean(((magnetic_data-predicted_magnetics)/magnetic_std)**2)))
    return JointInversionResult(
        mesh=mesh,
        active=active,
        density=density,
        susceptibility=susceptibility,
        predicted_gravity=predicted_gravity,
        predicted_magnetics=predicted_magnetics,
        history=history,
        diagnostics={"gravity_component": gravity_component, "weighted_rms_gravity": gravity_wrms,
                     "weighted_rms_magnetics": magnetic_wrms, "unit_weighted_rms_met": max(gravity_wrms, magnetic_wrms) <= 1.,
                     "iterations": int(optimizer.iter), "iteration_limit_reached": int(optimizer.iter) >= int(iterations),
                     "coupling_weight": float(coupling_weight), "beta_seed": 0,
                     "cross_gradient_hessian": cross_gradient_hessian,
                     "sensitivity_bytes": int(sensitivity_bytes), "sensitivity_dtype": dtype.name,
                     "sensitivity_mode": "matrix_free" if storage == "forward_only" else storage,
                     "stored_sensitivity_bytes": 0 if storage == "forward_only" else int(sensitivity_bytes),
                     "cg_maxiter": int(cg_maxiter), "cg_rtol": float(cg_rtol), **_cg_metrics(optimizer),
                     **_solver_history_metrics(history),
                     **{key: history[-1][key] for key in ("relative_model_change", "data_target_tolerance_met", "outer_convergence_met")},
                     "reference_models_explicit": explicit_reference,
                     "bound_start_restarts": int(getattr(optimizer, "bound_start_restarts", 0)),
                     "preconditioner": "weighted_joint_Jacobi", "init_bfgs": False},
    )


def full_model(result, inactive_value=np.nan):
    """Expand an active-cell model to mesh cells; MVI returns amplitude and vectors."""
    count = result.mesh.nC
    if result.kind != "mvi":
        output = np.full(count, inactive_value, dtype=float)
        output[result.active] = result.model
        if result.kind == "gravity":
            return {"gravity": output, "density_contrast_g_cm3": output,
                    "density_contrast_kg_m3": output * 1000.}
        return {result.kind: output, "susceptibility_si": output}
    n_active = int(np.count_nonzero(result.active))
    vectors = np.asarray(result.model).reshape((n_active, 3), order="F")
    outputs = {}
    for index, name in enumerate(
        ("magnetization_x", "magnetization_y", "magnetization_z")
    ):
        values = np.full(count, inactive_value, dtype=float)
        values[result.active] = vectors[:, index]
        outputs[name] = values
        outputs[("effective_susceptibility_x_si", "effective_susceptibility_y_si", "effective_susceptibility_z_si")[index]] = values
        scale = result.diagnostics.get("magnetization_a_per_m_per_si")
        if scale is not None:
            outputs[("magnetization_x_a_m", "magnetization_y_a_m", "magnetization_z_a_m")[index]] = values * scale
    amplitude = np.full(count, inactive_value, dtype=float)
    amplitude[result.active] = np.linalg.norm(vectors, axis=1)
    outputs["magnetization_amplitude"] = amplitude
    outputs["effective_susceptibility_amplitude_si"] = amplitude
    if scale is not None:
        outputs["magnetization_amplitude_a_m"] = amplitude * scale
    return outputs


def joint_full_models(result, inactive_value=np.nan):
    """Expand joint active-cell models for VTK export."""
    density = np.full(result.mesh.nC, inactive_value, dtype=float)
    susceptibility = np.full(result.mesh.nC, inactive_value, dtype=float)
    density[result.active] = result.density
    susceptibility[result.active] = result.susceptibility
    return {"density": density, "susceptibility": susceptibility,
            "density_contrast_g_cm3": density, "density_contrast_kg_m3": density * 1000.,
            "susceptibility_si": susceptibility}


def write_mesh_vtk(output_base, mesh, models):
    """Write cell geometry and scalar fields without requiring the VTK package."""
    for name, values in models.items():
        if np.asarray(values).size != mesh.nC:
            raise ValueError(f"VTK model {name!r} must contain {mesh.nC} values.")

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
        stream.write("TerraWorkbench inversion mesh\n")
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


def run_inversion_workflow(kind, xyz, observed, standard_deviation, *,
                           output_directory, regional_prediction=None, require_data_target=False, **options):
    """Invert arrays and publish NPZ, VTK, residual CSV and provenance JSON.

    Coordinates are projected metres with positive-up elevations. Gravity is gz
    in mGal with density contrast in g/cm3, positive up by default; set
    gravity_component="down" for positive-down observations and predictions.
    Magnetic TMI is nT and susceptibility
    SI. Inputs must already have their survey corrections. A supplied regional
    prediction is subtracted in data space; a reference_model in options is a
    separate active-cell model prior, never an automatic substitute for it.
    A successful run may reach its iteration limit above the requested misfit;
    diagnostics explicitly report whether the target was reached.
    """
    import hashlib
    from importlib.metadata import version
    from .inversion_workflows import input_provenance, save_manifest as write_manifest

    if type(require_data_target) is not bool:
        raise ValueError("require_data_target must be boolean")

    output = Path(output_directory)
    # Refuse existing directories so failed runs and previous results survive.
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"state": "running", "kind": kind}

    def save_manifest():
        write_manifest(output / "run.json", manifest)

    save_manifest()
    try:
        xyz = as_array(xyz, dtype=float)
        observed = as_array(observed, dtype=float)
        standard_deviation = as_array(standard_deviation, dtype=float)
        regional = np.zeros_like(observed) if regional_prediction is None else as_array(regional_prediction, dtype=float)
        if regional.shape != observed.shape or not np.isfinite(regional).all():
            raise ValueError("Regional prediction must be finite and match observations.")
        residual_data = observed - regional
        manifest["versions"] = {name: version(name) for name in ("simpeg", "discretize", "numpy", "scipy", "choclo")}
        manifest["core_source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        manifest["options"] = {}
        input_arrays = {}
        for key, value in options.items():
            if callable(value):
                manifest["options"][key] = "callback"
            elif key == "mesh":
                manifest["options"][key] = None if value is None else type(value).__name__
            elif value is None or isinstance(value, (str, bool, int, float)):
                if isinstance(value, float) and not np.isfinite(value):
                    raise ValueError(f"Option {key} must be finite.")
                manifest["options"][key] = value
            else:
                array = np.asarray(value)
                input_arrays["input_" + key] = array
                manifest["options"][key] = {"shape": list(array.shape), "sha256": hashlib.sha256(array.tobytes()).hexdigest()}
        manifest["regional_removed"] = regional_prediction is not None
        manifest.update(input_provenance(dict(xyz=xyz, observed=observed,
            standard_deviation=np.asarray(standard_deviation, float), regional=regional), options))
        save_manifest()
        result = run_potential_field_inversion(kind, xyz, residual_data, standard_deviation, **options)
        models = full_model(result)
        np.savez_compressed(output / "model.npz", active=result.active,
            model=result.model, cell_centers=result.mesh.cell_centers,
            cell_widths=result.mesh.h_gridded, xyz=xyz, observed=observed,
            standard_deviation=standard_deviation, regional=regional,
            predicted_residual=result.predicted, predicted_total=regional+result.predicted,
            **models, **input_arrays)
        write_mesh_vtk(output / "model.vtk", result.mesh, models)
        np.savetxt(output / "data.csv", np.column_stack([
            xyz, observed, standard_deviation, regional, result.predicted,
            regional+result.predicted, residual_data-result.predicted]),
            delimiter=",", header="x,y,z,observed,sigma,regional,predicted_residual,predicted_total,residual", comments="")
        manifest.update(state="complete", diagnostics=result.diagnostics, history=result.history,
                        artifacts=["model.npz", "model.vtk", "data.csv", "run.json"])
        manifest["numerical_status"] = "data_target_reached" if result.diagnostics["target_reached"] else "data_target_not_reached"
        manifest["require_data_target"] = require_data_target
        if kind == "mvi":
            manifest["model_field_units"] = {
                name: "A/m" if name.endswith("_a_m") else "effective susceptibility SI"
                for name in models}
            manifest["legacy_field_note"] = "Unqualified magnetization_* names retain historical effective-SI values; use explicit _si or _a_m fields."
        elif kind == "gravity":
            manifest["model_field_units"] = {"gravity": "g/cm3", "density_contrast_g_cm3": "g/cm3", "density_contrast_kg_m3": "kg/m3"}
            manifest["legacy_field_note"] = "The historical gravity CELL field is density contrast in g/cm3, not a gravity anomaly."
        else:
            manifest["model_field_units"] = {name: "SI" for name in models}
        if require_data_target and not result.diagnostics["target_reached"]:
            raise RuntimeError("Inversion did not reach its declared data target")
        cancel = options.get("cancel_callback")
        if cancel is not None and cancel():
            raise RuntimeError("Inversion export canceled")
        save_manifest()
        return result
    except Exception as error:
        manifest.update(state="failed", error=f"{type(error).__name__}: {error}")
        save_manifest()
        raise


def main(argv=None):
    """Headless entry point using an NPZ survey and a JSON numerical recipe."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="TerraWorkbench standalone potential-field inversion")
    parser.add_argument("--kind", choices=("gravity", "susceptibility", "mvi"), required=True)
    parser.add_argument("--input", required=True, help="NPZ with xyz, observed and standard_deviation")
    parser.add_argument("--recipe", required=True, help="JSON numerical options")
    parser.add_argument("--output", required=True, help="New result directory")
    parser.add_argument("--mesh-ubc", help="Optional native octree mesh; input NPZ must include active_cells")
    args = parser.parse_args(argv)
    options = json.loads(Path(args.recipe).read_text(encoding="utf-8"))
    if not isinstance(options, dict):
        raise ValueError("The numerical recipe must be a JSON object.")
    with np.load(args.input, allow_pickle=False) as survey:
        xyz, observed, sigma = (survey[name] for name in ("xyz", "observed", "standard_deviation"))
        regional = survey["regional_prediction"] if "regional_prediction" in survey else None
        for name in ("topography", "reference_model", "starting_model", "active_cells", "lower", "upper", "cell_weights"):
            if name in survey:
                if name in options:
                    raise ValueError(f"Option {name} is present in both recipe and input NPZ.")
                options[name] = survey[name]
    if args.mesh_ubc:
        from discretize import TreeMesh
        options["mesh"] = TreeMesh.read_UBC(args.mesh_ubc)
    result = run_inversion_workflow(args.kind, xyz, observed, sigma,
        output_directory=args.output, regional_prediction=regional, **options)
    print(json.dumps({"output": str(Path(args.output).resolve()), **result.diagnostics}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

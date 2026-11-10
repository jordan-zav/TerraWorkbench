"""Staged Cartesian/spherical MVI with physical Cartesian outputs.

Formulation: Fournier, Heagy and Oldenburg (2020), doi:10.1190/geo2019-0244.1;
SDK interfaces: SimPEG 0.25 spherical MVI example (MIT, SimPEG developers).
The true mapped sensitivity diagonal includes within-cell component cross terms.
"""

import gc
import hashlib
from pathlib import Path

import numpy as np
from scipy.sparse import diags

from ._array_contract import as_array
from ._calibration import integer_budget


def spherical_optimizer(
    n, cancel_callback=None, bounded_angles=False, scaled_cg=True, **kwargs
):
    """Projected GN with a descent-preserving angular trust-step safeguard.

    The SDK's separate critical gradient floor must not override the requested
    tolerance. Only after an unsuccessful Armijo search, retry with angular
    components capped at pi/4. If clipping destroys descent, use a feasible
    diagonal-gradient direction. Already accepted Newton steps are preserved.
    Neither safeguard changes the objective, bounds or data.
    """
    from .inversion import _jacobi_optimizer

    tolerance = float(kwargs.get("tolG", 1e-6))
    kwargs["eps"] = min(float(kwargs.get("eps", 1e-5)), tolerance / 1000.0)
    opt = _jacobi_optimizer(cancel_callback=cancel_callback, **kwargs)
    original_scale = opt.scaleSearchDirection
    original_search = opt.modifySearchDirection
    original_direction = opt.findSearchDirection
    opt.spherical_step_events = []
    opt.spherical_line_search_retries = []
    opt.spherical_bound_step_events = []
    opt.spherical_search_failed = False
    opt.cg_scaled_rel_resid = None
    opt.cg_residual_replacements = 0

    def projected_jacobi():
        trial = opt.projection(opt.xc - np.asarray(opt.approxHinv @ opt.g))
        step = np.asarray(trial - opt.xc).copy()
        step[n:] = np.clip(step[n:], -np.pi / 4, np.pi / 4)
        return step

    def direction():
        if getattr(opt, "_approxHinv", None) is None:
            raise RuntimeError("Jacobi preconditioner was not initialized.")
        inactive = ~opt.activeSet(opt.xc)
        if scaled_cg and np.any(opt.g[inactive]):
            step = spherical_pcg(opt, cancel_callback)
        else:
            step = original_direction()
            opt.cg_scaled_rel_resid = None
            opt.cg_breakdown = None
            opt.cg_residual_replacements = 0
        free_bound = opt.activeSet(opt.xc) & ~opt.bindingSet(opt.xc)
        if free_bound.any():
            # The SDK's max(inactive step) mixes SI amplitude and radians.
            # Use the cell/component's own curvature to leave a bound instead.
            corrected = np.asarray(opt.approxHinv @ (-opt.g))
            previous = np.array(step[free_bound], copy=True)
            if scaled_cg and np.any(opt.g[inactive]):
                # Counterfactual SDK scaling; it is no longer applied.
                previous = (
                    (-opt.g[free_bound])
                    * opt.active_set_grad_scale
                    * np.max(abs(step))
                    / np.max(abs(opt.g[free_bound]))
                )
            step[free_bound] = corrected[free_bound]
            if not np.array_equal(previous, step[free_bound]):
                opt.spherical_bound_step_events.append(
                    dict(
                        iteration=int(opt.iter) + 1,
                        coordinates=int(np.count_nonzero(free_bound)),
                        sdk_counterfactual_max_abs=float(np.max(abs(previous))),
                        jacobi_max_abs=float(np.max(abs(step[free_bound]))),
                        angular_cg_max_abs=float(np.max(abs(step[n:]), initial=0.0)),
                    )
                )
        return step

    def scale(direction):
        if not np.isfinite(direction).all():
            raise RuntimeError("Non-finite spherical search direction")
        step = np.array(direction, copy=True)
        limit = np.pi / 4
        limited = int(np.count_nonzero(abs(step[n:]) > limit))
        step[n:] = np.clip(step[n:], -limit, limit)
        step[opt.bindingSet(opt.xc)] = 0.0
        fallback = bool(float(opt.g @ step) >= 0 and np.any(step))
        if fallback:
            step = projected_jacobi()
        if limited or fallback:
            opt.spherical_step_events.append(
                dict(
                    iteration=int(opt.iter) + 1,
                    limited_angles=limited,
                    diagonal_gradient_fallback=fallback,
                )
            )
        return original_scale(step)

    def search(direction):
        opt.spherical_search_failed = False
        value, passed = original_search(direction)
        if passed:
            return value, passed
        raw_backtracks = int(opt.iterLS)
        retry = scale(direction)
        candidates = []
        if not np.array_equal(retry, direction):
            candidates.append(("bounded_angles", retry))
        candidates.append(("projected_Jacobi", projected_jacobi()))
        for kind, candidate in candidates:
            if not np.any(candidate) or float(opt.g @ candidate) >= 0:
                continue
            value, passed = original_search(candidate)
            opt.spherical_line_search_retries.append(
                dict(
                    iteration=int(opt.iter) + 1,
                    kind=kind,
                    original_backtracks=raw_backtracks,
                    retry_backtracks=int(opt.iterLS),
                    accepted=bool(passed),
                )
            )
            if passed:
                break
        opt.spherical_search_failed = not passed
        return value, passed

    opt.spherical_retry_direction = scale
    if bounded_angles:
        opt.scaleSearchDirection = scale
    opt.findSearchDirection = direction
    opt.modifySearchDirection = search
    return opt


def spherical_pcg(opt, cancel_callback=None):
    """Projected PCG with true raw and Jacobi-energy residual requirements.

    The energy norm is dimensionally invariant under diagonal coordinate scaling.
    Keep the raw criterion too, and verify true residuals before accepting CG.
    """
    inactive = ~opt.activeSet(opt.xc)
    inverse = np.asarray(opt.approxHinv.diagonal())
    if not np.isfinite(inverse).all() or np.any(inverse <= 0):
        raise RuntimeError("Invalid spherical Jacobi inverse")
    rhs = (-opt.g) * inactive
    raw_initial = float(np.linalg.norm(rhs))
    energy_initial = float(np.sqrt(rhs @ (inverse * rhs)))
    raw_target = max(float(opt.cg_atol), float(opt.cg_rtol) * raw_initial)
    energy_target = float(opt.cg_rtol) * energy_initial
    step = np.zeros_like(rhs)
    residual = rhs.copy()
    z = inverse * residual
    conjugate = z.copy()
    rz = float(residual @ z)
    replacements = 0
    breakdown = None
    count = 0

    def product(value):
        if cancel_callback is not None and cancel_callback():
            raise RuntimeError("Spherical MVI canceled during scaled CG")
        return np.asarray(opt.H @ value) * inactive

    for count in range(1, int(opt.cg_maxiter) + 1):
        hp = product(conjugate)
        curvature = float(conjugate @ hp)
        if not np.isfinite(curvature) or curvature <= 0:
            breakdown = "nonpositive_curvature"
            break
        alpha = rz / curvature
        step += alpha * conjugate
        residual -= alpha * hp
        z = inverse * residual
        next_rz = max(float(residual @ z), 0.0)
        raw = float(np.linalg.norm(residual))
        energy = float(np.sqrt(next_rz))
        if raw <= raw_target and energy <= energy_target:
            residual = rhs - product(step)
            z = inverse * residual
            next_rz = max(float(residual @ z), 0.0)
            if (
                np.linalg.norm(residual) <= raw_target
                and np.sqrt(next_rz) <= energy_target
            ):
                break
            # Recursive residual drift is not a successful linear solve.
            replacements += 1
            conjugate = z.copy()
        else:
            if not np.isfinite(next_rz) or next_rz <= 0:
                breakdown = "residual_breakdown"
                break
            conjugate = z + (next_rz / rz) * conjugate
        rz = next_rz
    residual = rhs - product(step)
    opt.cg_count = count
    opt.cg_abs_resid = float(np.linalg.norm(residual))
    opt.cg_rel_resid = opt.cg_abs_resid / raw_initial
    opt.cg_true_rel_resid = opt.cg_rel_resid
    opt.cg_scaled_rel_resid = float(
        np.sqrt(max(float(residual @ (inverse * residual)), 0.0)) / energy_initial
    )
    opt.cg_residual_replacements = replacements
    opt.cg_breakdown = breakdown
    opt.cg_solver_mode = "projected_cg"
    if breakdown is not None and not np.any(step):
        step = inverse * rhs
        opt.cg_solver_mode = "cg_breakdown_descent"
    return step


def zero_amplitude_chart_candidate(model, physical_gradient, caps, cost, gradient):
    """Reorient blocked exact-zero free amplitudes without changing physical M.

    Accept only a non-increasing fixed prior cost and a newly negative radial
    derivative. Nonzero amplitudes and excluded cells are never reoriented.
    The direction uses measured-data gradients, never geological truth.
    """
    value = np.asarray(model)
    n = len(value) // 3
    physical = np.asarray(physical_gradient).reshape((n, 3), order="F")
    norm = np.hypot(np.hypot(physical[:, 0], physical[:, 1]), physical[:, 2])
    total = np.asarray(gradient(value))
    tolerance = 64 * np.finfo(float).eps * (norm + abs(total[:n]) + 1.0)
    blocked = (
        (value[:n] == 0)
        & (np.asarray(caps) > 0)
        & (norm > 0)
        & (total[:n] >= -tolerance)
    )
    if not blocked.any():
        return value.copy(), 0
    desired = spherical_from_cartesian(-physical)
    difference = desired - value
    difference[2 * n :] = (difference[2 * n :] + np.pi) % (2 * np.pi) - np.pi
    before = float(cost(value))
    if not np.isfinite(before):
        return value.copy(), 0
    roundoff = 64 * np.finfo(float).eps * max(abs(before), 1.0)
    for fraction in (1.0, 0.5, 0.25, 0.125):
        candidate = value.copy()
        candidate[n : 2 * n][blocked] += fraction * difference[n : 2 * n][blocked]
        candidate[2 * n :][blocked] += fraction * difference[2 * n :][blocked]
        after = float(cost(candidate))
        if np.isfinite(after) and after <= before + roundoff:
            derivative = np.asarray(gradient(candidate))[:n]
            if np.any(blocked & (derivative < -tolerance)):
                return candidate, int(np.count_nonzero(blocked))
    return value.copy(), 0


def spherical_chart_recovery(
    sim, misfit, reg, caps, target_misfit, cancel_callback=None
):
    """SDK directive for exact-zero chart repair before sensitivity/Jacobi updates."""
    from simpeg import directives, maps
    from simpeg.potential_fields import magnetics

    n = len(caps)

    class ChartRecovery(directives.InversionDirective):
        def repair(self):
            if cancel_callback is not None and cancel_callback():
                raise RuntimeError("Spherical MVI canceled during chart recovery")
            model = np.asarray(self.invProb.model)
            poles = (model[:n] > 0) & (abs(model[n : 2 * n]) == np.pi / 2) & (caps > 0)
            if not np.any((model[:n] == 0) & (caps > 0)) and not poles.any():
                return
            if float(misfit(model)) <= target_misfit and not poles.any():
                return
            weighted = 2 * (
                misfit.W.T @ (misfit.W @ (sim.dpred(model) - misfit.data.dobs))
            )
            if sim.store_sensitivities == "forward_only":
                cart = magnetics.simulation.Simulation3DIntegral(
                    sim.mesh,
                    active_cells=sim.active_cells,
                    survey=sim.survey,
                    chiMap=maps.IdentityMap(nP=3 * n),
                    model_type="vector",
                    engine="choclo",
                    store_sensitivities="forward_only",
                    sensitivity_dtype=sim.sensitivity_dtype,
                )
                physical = cart.Jtvec(cartesian_from_spherical(model), weighted)
            else:
                physical = np.asarray(sim.G).T @ weighted
            if not np.isfinite(physical).all():
                raise RuntimeError("Non-finite physical gradient in chart recovery")
            beta = float(self.invProb.beta)

            def gradient(value):
                return sim.chiMap.deriv(value).T @ physical + beta * reg.deriv(value)

            candidate, count = zero_amplitude_chart_candidate(
                model, physical, caps, lambda value: beta * reg(value), gradient
            )
            candidate, pole_count = pole_chart_candidate(
                candidate, physical, caps, lambda value: beta * reg(value), gradient
            )
            if count or pole_count:
                # Physical magnetization is exactly unchanged, so cached phi_d
                # remains valid. Update all coordinate-dependent model holders.
                self.invProb.model = candidate
                self.opt.xc = candidate
                sim.model = candidate
                for term in self.reg.objfcts:
                    term.model = candidate
                self.invProb.phi_m = float(reg(candidate))
                self.invProb.phi_m_last = self.invProb.phi_m
                self.reorientations += count
                self.pole_reorientations += pole_count
                self.events.append(
                    dict(
                        iteration=int(getattr(self.opt, "iter", 0)),
                        reoriented_cells=count,
                        reoriented_poles=pole_count,
                    )
                )

        def initialize(self):
            self.reorientations = 0
            self.pole_reorientations = 0
            self.events = []
            self.repair()

        def endIter(self):
            self.repair()

    return ChartRecovery()


def pole_chart_candidate(model, physical_gradient, caps, cost, gradient):
    """Reorient undefined azimuth at an exact pole without changing physical M."""
    value = np.asarray(model)
    n = len(value) // 3
    theta = value[n : 2 * n]
    sign = np.sign(theta)
    physical = np.asarray(physical_gradient).reshape((n, 3), order="F")
    norm = np.hypot(physical[:, 0], physical[:, 1])
    total = np.asarray(gradient(value))
    tolerance = (
        64 * np.finfo(float).eps * (value[:n] * norm + abs(total[n : 2 * n]) + 1.0)
    )
    blocked = (
        (value[:n] > 0)
        & (abs(theta) == np.pi / 2)
        & (np.asarray(caps) > 0)
        & (norm > 0)
        & (sign * total[n : 2 * n] <= tolerance)
    )
    if not blocked.any():
        return value.copy(), 0
    desired = np.arctan2(-physical[:, 1], -physical[:, 0])
    difference = (desired - value[2 * n :] + np.pi) % (2 * np.pi) - np.pi
    before = float(cost(value))
    allowance = 64 * np.finfo(float).eps * max(abs(before), 1.0)
    if not np.isfinite(before):
        return value.copy(), 0
    for fraction in (1.0, 0.5, 0.25, 0.125):
        candidate = value.copy()
        candidate[2 * n :][blocked] += fraction * difference[blocked]
        after = float(cost(candidate))
        if np.isfinite(after) and after <= before + allowance:
            derivative = np.asarray(gradient(candidate))[n : 2 * n]
            if np.any(blocked & (sign * derivative > tolerance)):
                return candidate, int(np.count_nonzero(blocked))
    return value.copy(), 0


def polar_cosine(theta):
    """Exactly zero horizontal component at representable north/south poles."""
    return np.where(abs(theta) == np.pi / 2, 0.0, np.cos(theta))


def cartesian_from_spherical(model):
    amplitude, theta, phi = np.asarray(model).reshape((3, -1))
    return np.r_[
        amplitude * polar_cosine(theta) * np.cos(phi),
        amplitude * polar_cosine(theta) * np.sin(phi),
        amplitude * np.sin(theta),
    ]


def safeguarded_irls_type():
    """SDK IRLS schedule with positive thresholds for identically zero terms.

    Threshold initialization follows SimPEG 0.25 (MIT). Retain a term's existing
    positive threshold if its model percentile is zero; never perturb the model.
    """
    from simpeg import directives, regularization

    class SafeIRLS(directives.UpdateIRLS):
        def initialize(self):
            super().initialize()
            self.threshold_fallbacks = []
            self.epochs = []
            self.inner_history = []
            self.inner_rtol = None
            self.stop_reason = None

        def start_irls(self):
            self.metrics.start_irls_iter = int(self.opt.iter)
            self.invProb.phi_m_last = float(self.reg(self.invProb.model))
            for block, (reg, norms) in enumerate(
                zip(self.reg.objfcts, self.metrics.input_norms)
            ):
                if not isinstance(reg, regularization.Sparse):
                    continue
                for component, obj in enumerate(reg.objfcts):
                    threshold = float(
                        np.percentile(
                            abs(obj.mapping * obj._delta_m(self.invProb.model)),
                            self.percentile,
                        )
                    )
                    if isinstance(obj, regularization.SmoothnessFirstOrder):
                        threshold /= reg.regularization_mesh.base_length
                    if threshold == 0.0:
                        threshold = float(obj.irls_threshold)
                        self.threshold_fallbacks.append(
                            dict(block=block, component=component, value=threshold)
                        )
                    obj.irls_threshold = threshold
                reg.norms = norms
            self.invProb.l2model = self.invProb.model.copy()
            self.cooling_factor = 1.0

        def endIter(self):
            if (
                self.invProb.phi_d <= self.misfit_from_chi_factor(self.chifact_target)
                and float(self.reg(self.invProb.model)) == 0.0
            ):
                self.stop_reason = "target_fit_zero_prior"
                self.opt.stopNextIteration = True
                return
            super().endIter()
            if self.opt.stopNextIteration:
                self.stop_reason = (
                    "irls_budget"
                    if self.metrics.irls_iteration_count >= self.max_irls_iterations
                    else "adaptive_irls_stationary"
                )

    return SafeIRLS


def lagged_irls_controller(refresh, *, max_epochs, cancel_callback=None, **kwargs):
    """Update the adaptive objective only after a frozen subproblem is solved.

    An inexact inner solve requires a 1e-3 reduction of the projected gradient
    in the initial Jacobi metric. The metric is fixed for each epoch. Newton
    iterations and objective updates have separate finite budgets. No truth or
    model-recovery statistic participates in this controller.
    """

    class LaggedIRLS(safeguarded_irls_type()):
        def initialize(self):
            super().initialize()
            self.epochs = []
            self.inner_history = []
            self.stop_reason = None
            self.metric = None
            self.last_objective = None
            self.start_iteration = 0
            self.inner_rtol = 1e-3
            original = self.opt.stoppingCriteria

            def stop(inLS=False):
                if inLS:
                    return original(inLS=True)
                if cancel_callback is not None and cancel_callback():
                    raise RuntimeError("Spherical MVI canceled during lagged IRLS")
                if self.opt.iter == 0:
                    self.opt.f0, self.opt.g0 = self.opt.f, self.opt.g.copy()
                while True:
                    if self.metric is None:
                        inverse = np.asarray(self.opt.approxHinv.diagonal())
                        self.metric = 1.0 / inverse
                        self.initial_measure = self.measure()
                        self.start_iteration = int(self.opt.iter)
                    current = float(self.opt.f)
                    if self.last_objective is not None:
                        allowance = 1e-9 * max(abs(self.last_objective), 1.0)
                        if current > self.last_objective + allowance:
                            raise RuntimeError("Frozen IRLS objective increased")
                    self.last_objective = current
                    if current == 0.0:
                        self.stop_reason = "zero_objective"
                        return True
                    measure = self.measure()
                    threshold = max(self.inner_rtol * self.initial_measure, 1e-12)
                    self.inner_history.append(
                        dict(
                            iteration=int(self.opt.iter),
                            epoch=len(self.epochs),
                            objective=current,
                            projected_gradient_metric=measure,
                            threshold=threshold,
                        )
                    )
                    if self.opt.iter >= self.opt.maxIter:
                        self.stop_reason = "newton_budget"
                        return True
                    if measure > threshold:
                        return False
                    if float(self.reg(self.invProb.model)) == 0.0 and float(
                        self.invProb.phi_d
                    ) <= self.misfit_from_chi_factor(self.chifact_target):
                        # An already optimal zero-penalty model within the noise
                        # target needs no sparse reweighting at threshold zero.
                        self.stop_reason = "target_fit_zero_prior"
                        return True
                    if len(self.epochs) >= max_epochs:
                        self.stop_reason = "objective_update_budget"
                        return True
                    self.epochs.append(
                        dict(
                            iteration=int(self.opt.iter),
                            inner_iterations=int(self.opt.iter) - self.start_iteration,
                            objective=current,
                            beta=float(self.invProb.beta),
                            phi_d=float(self.invProb.phi_d),
                            projected_gradient_metric=measure,
                            threshold=threshold,
                        )
                    )
                    # The SDK cooling cadence counts completed subproblems here,
                    # rather than incompletely solved Newton steps.
                    iteration = self.opt.iter
                    try:
                        self.opt.iter = len(self.epochs)
                        refresh("before")
                        super(LaggedIRLS, self).endIter()
                    finally:
                        self.opt.iter = iteration
                    if self.opt.stopNextIteration:
                        self.stop_reason = (
                            "irls_budget"
                            if self.metrics.irls_iteration_count
                            >= self.max_irls_iterations
                            else "irls_stationary"
                        )
                        return True
                    refresh("after")
                    self.opt.f, self.opt.g, self.opt.H = self.opt.evalFunction(
                        self.opt.xc, return_g=True, return_H=True
                    )
                    self.opt.f_last = self.opt.f
                    self.opt.f0, self.opt.g0 = self.opt.f, self.opt.g.copy()
                    self.opt.x_last = self.opt.xc.copy()
                    self.metric = self.last_objective = None

            self.opt.stoppingCriteria = stop

        def measure(self):
            step = (
                self.opt.projection(self.opt.xc - self.opt.g / self.metric)
                - self.opt.xc
            )
            return float(np.linalg.norm(np.sqrt(self.metric) * step))

        def endIter(self):
            # Objective updates are controlled at the next evaluated iterate,
            # never from stale pre-step gradients in an end-iteration callback.
            pass

    return LaggedIRLS(**kwargs)


def spherical_from_cartesian(vectors):
    x, y, z = np.asarray(vectors).T
    amplitude = np.hypot(np.hypot(x, y), z)
    return np.r_[
        amplitude,
        np.where(amplitude > 0, np.arctan2(z, np.hypot(x, y)), 0.0),
        np.where(amplitude > 0, np.arctan2(y, x), 0.0),
    ]


def exact_spherical_map(n):
    """No epsilon magnetization or approximate-equality derivative cache."""
    from simpeg import maps
    from scipy import sparse

    class ExactMap(maps.SphericalSystem):
        def _transform(self, model):
            return cartesian_from_spherical(model)

        def inverse(self, vectors):
            return spherical_from_cartesian(
                np.asarray(vectors).reshape((n, 3), order="F")
            )

        def deriv(self, m, v=None):
            if not np.array_equal(getattr(self, "_exact_model", None), m):
                a, t, p = np.asarray(m).reshape((3, -1))
                ct, st, cp, sp = polar_cosine(t), np.sin(t), np.cos(p), np.sin(p)
                self._exact_derivative = sparse.bmat(
                    [
                        [diags(ct * cp), diags(-a * st * cp), diags(-a * ct * sp)],
                        [diags(ct * sp), diags(-a * st * sp), diags(a * ct * cp)],
                        [diags(st), diags(a * ct), sparse.csr_matrix((n, n))],
                    ],
                    format="csr",
                )
                self._exact_model = np.array(m, copy=True)
            return self._exact_derivative if v is None else self._exact_derivative @ v

    return ExactMap(nP=3 * n)


def mapped_jtj_diagonal(model, gram):
    """diag(D.T G.T Wd**2 G D) for a cell-local spherical map D.

    Gram is (3,3,n) and includes all cross-component products of physical G.
    Stacking is amplitude, elevation angle, azimuth from +east, in radians.
    """
    amplitude, theta, phi = np.asarray(model).reshape((3, -1))
    ct, st, cp, sp = polar_cosine(theta), np.sin(theta), np.cos(phi), np.sin(phi)
    d = np.array(
        [
            [ct * cp, -amplitude * st * cp, -amplitude * ct * sp],
            [ct * sp, -amplitude * st * sp, amplitude * ct * cp],
            [st, amplitude * ct, np.zeros_like(amplitude)],
        ]
    )
    result = np.einsum("apc,abc,bpc->pc", d, gram, d).ravel()
    tolerance = 1e-12 * max(float(np.max(abs(result))), 1.0)
    if not np.isfinite(result).all() or np.any(result < -tolerance):
        raise RuntimeError("Invalid mapped spherical sensitivity diagonal")
    return np.maximum(result, 0.0)


def spherical_simulation(mesh, active, survey, cancel_callback=None, **kwargs):
    """Exact mapped column energies, bounded temporary blocks in matrix-free mode."""
    from simpeg import maps
    from simpeg.potential_fields import magnetics

    receivers = survey.source_field.receiver_list
    if len(receivers) != 1 or list(receivers[0].components) != ["tmi"]:
        raise ValueError(
            "Staged spherical MVI currently requires a single TMI receiver set"
        )

    class ExactSphericalSimulation(magnetics.simulation.Simulation3DIntegral):
        def getJtJdiag(self, m, W=None, f=None):
            if cancel_callback is not None and cancel_callback():
                raise RuntimeError(
                    "Spherical MVI canceled during sensitivity accumulation"
                )
            self.model = m
            weights = (
                np.ones(self.survey.nD) if W is None else np.asarray(W.diagonal()) ** 2
            )
            digest = hashlib.sha256(np.ascontiguousarray(weights).tobytes()).digest()
            if getattr(self, "_gram_weights", None) != digest:
                n = int(active.sum())
                gram = np.zeros((3, 3, n))
                if self.store_sensitivities != "forward_only":
                    blocks = [(0, np.asarray(self.G))]
                else:
                    # Public SDK kernel on small receiver blocks; never construct
                    # or retain the complete data-by-model matrix.
                    locations = survey.source_field.receiver_list[0].locations
                    rows = max(
                        1,
                        min(
                            32,
                            max(1, len(locations) // 2),
                            (32 * 1024**2) // (3 * n * 8),
                        ),
                    )

                    def generate():
                        for start in range(0, len(locations), rows):
                            field = survey.source_field
                            sub = magnetics.survey.Survey(
                                magnetics.sources.UniformBackgroundField(
                                    receiver_list=[
                                        magnetics.receivers.Point(
                                            locations[start : start + rows],
                                            components="tmi",
                                        )
                                    ],
                                    amplitude=field.amplitude,
                                    inclination=field.inclination,
                                    declination=field.declination,
                                )
                            )
                            local = magnetics.simulation.Simulation3DIntegral(
                                mesh,
                                active_cells=active,
                                survey=sub,
                                chiMap=maps.IdentityMap(nP=3 * n),
                                model_type="vector",
                                engine="choclo",
                                store_sensitivities="ram",
                                sensitivity_dtype=self.sensitivity_dtype,
                            )
                            yield start, np.asarray(local.G)

                    blocks = generate()
                for start, block in blocks:
                    if cancel_callback is not None and cancel_callback():
                        raise RuntimeError(
                            "Spherical MVI canceled during sensitivity accumulation"
                        )
                    columns = block.reshape((len(block), 3, n))
                    gram += np.einsum(
                        "ric,rjc,r->ijc",
                        columns,
                        columns,
                        weights[start : start + len(block)],
                        dtype=np.float64,
                    )
                self._physical_gram = gram
                self._gram_weights = digest
            return mapped_jtj_diagonal(m, self._physical_gram)

        def regularization_diagonal(self, m, W, mode):
            exact = self.getJtJdiag(m, W=W)
            if mode == "mapped_exact":
                return exact
            # Match the SDK prior statistic, separately from the exact solver
            # diagonal. Selecting another statistic changes the inverse problem.
            g = self._physical_gram
            component = np.r_[g[0, 0], g[1, 1], g[2, 2]]
            return np.asarray(
                (diags(np.sqrt(component)) @ self.chiMap.deriv(m)).power(2).sum(axis=0)
            ).ravel()

    return ExactSphericalSimulation(
        mesh,
        active_cells=active,
        survey=survey,
        chiMap=exact_spherical_map(int(active.sum())),
        model_type="vector",
        engine="choclo",
        **kwargs,
    )


def spherical_regularizer(
    mesh,
    active,
    reference,
    norms,
    angle_norms,
    weights,
    reference_in_smooth,
    cell_weights,
):
    from simpeg import maps, regularization, directives

    n = int(active.sum())
    wires = maps.Wires(("amplitude", n), ("theta", n), ("phi", n))
    terms = []
    for i, name in enumerate(("amplitude", "theta", "phi")):
        term = regularization.Sparse(
            mesh,
            active_cells=active,
            mapping=getattr(wires, name),
            reference_model=reference,
            reference_model_in_smooth=reference_in_smooth,
            norms=norms if i == 0 else np.r_[2.0, angle_norms],
            gradient_type="total",
        )
        if weights is not None:
            for axis, value in zip("sxyz", weights):
                setattr(term, "alpha_" + axis, float(value))
        if i:
            term.alpha_s = 0.0
            term.units = "radian"
        if cell_weights is not None:
            term.set_weights(geological_prior=cell_weights)
        terms.append(term)
    return sum(terms[1:], terms[0]), directives.SphericalUnitsWeights(
        amplitude=wires.amplitude, angles=terms[1:]
    )


def run_spherical_mvi(
    xyz,
    observed,
    standard_deviation,
    *,
    mvi_cartesian_iterations,
    mvi_amplitude_max,
    mvi_angle_norms,
    mvi_sensitivity_weights,
    mvi_irls_update="adaptive",
    **options,
):
    from simpeg import (
        data,
        data_misfit,
        inverse_problem,
        directives,
        inversion,
    )
    from simpeg.potential_fields import magnetics
    from .inversion import (
        run_potential_field_inversion,
        InversionResult,
        _cg_metrics,
        _solver_history_metrics,
        _model_array,
    )

    integer_budget(mvi_cartesian_iterations, "mvi_cartesian_iterations")
    if mvi_irls_update not in ("adaptive", "lagged"):
        raise ValueError("Unknown spherical IRLS update strategy")
    if mvi_sensitivity_weights not in ("component_approximation", "mapped_exact"):
        raise ValueError(
            "MVI sensitivity weights must be component_approximation or mapped_exact"
        )
    integer_budget(options["iterations"], "iterations")
    integer_budget(options["irls_iterations"], "irls_iterations", 0)
    if options["lower"] is not None or options["upper"] is not None:
        raise ValueError(
            "Spherical MVI uses mvi_amplitude_max, not Cartesian component bounds"
        )
    if options["regularization_convention"] != "physical_gradient":
        raise ValueError("Spherical MVI requires physical_gradient regularization")
    if options["mvi_regularization"] != "amplitude":
        raise ValueError(
            "Spherical MVI has separate amplitude/angle regularizers; select mvi_regularization amplitude"
        )
    angles = as_array(
        [2.0, 2.0, 2.0] if mvi_angle_norms is None else mvi_angle_norms, float
    )
    if (
        angles.shape != (3,)
        or not np.isfinite(angles).all()
        or np.any((angles < 0) | (angles > 2))
    ):
        raise ValueError("MVI angle norms must be three finite values in [0,2]")
    norms = as_array(
        [options["regularization_norm"]] * 4
        if options["regularization_norms"] is None
        else options["regularization_norms"],
        float,
    )
    if (
        norms.shape != (4,)
        or not np.isfinite(norms).all()
        or np.any((norms < 0) | (norms > 2))
    ):
        raise ValueError(
            "Spherical amplitude norms must be four finite values in [0,2]"
        )
    if np.any(np.r_[norms, angles] < 2) and options["irls_iterations"] <= 0:
        raise ValueError("Sparse spherical norms require positive irls_iterations")
    maximum = as_array(mvi_amplitude_max, float)
    if (
        maximum.ndim > 1
        or not np.isfinite(maximum).all()
        or np.any(maximum < 0)
        or not np.any(maximum > 0)
    ):
        raise ValueError(
            "MVI amplitude maximum must be finite, nonnegative and positive for at least one cell"
        )
    if options["sensitivity_mode"] == "disk" or (
        options["sensitivity_mode"] == "auto" and options["sensitivity_path"]
    ):
        # A namespace bound to the complete physical operator prevents stale
        # matrices from another survey being silently reused at the same path.
        from .inversion_workflows import input_provenance
        from importlib.metadata import version

        if not options["sensitivity_path"]:
            raise ValueError("Disk sensitivity mode requires sensitivity_path")
        options["sensitivity_path"] = str(options["sensitivity_path"])
        digest = input_provenance(
            dict(
                xyz=as_array(xyz),
                observed=as_array(observed),
                sigma=as_array(standard_deviation),
                kernel_versions={
                    name: version(name) for name in ("simpeg", "discretize", "choclo")
                },
            ),
            options,
        )["input_sha256"]
        options["sensitivity_path"] = str(Path(options["sensitivity_path"]) / digest)
    user_progress = options["progress_callback"]
    cancel = options["cancel_callback"]
    for name in ("reference_model", "starting_model"):
        if options[name] is None:
            continue
        vector = as_array(options[name], float)
        if vector.ndim == 1 and len(vector) % 3 == 0:
            vector = vector.reshape((-1, 3), order="F")
        if (
            vector.ndim == 2
            and vector.shape[1] == 3
            and (maximum.ndim == 0 or len(maximum) == len(vector))
        ):
            if np.any(np.linalg.norm(vector, axis=1) > maximum):
                raise ValueError(f"MVI {name} amplitude exceeds mvi_amplitude_max")
    warm_options = dict(
        options,
        iterations=int(mvi_cartesian_iterations),
        regularization_norm=2.0,
        regularization_norms=[2.0] * 4,
        irls_iterations=0,
        target_chi=2.0 * float(options["target_chi"]),
        lower=-maximum,
        upper=maximum,
        mvi_regularization="componentwise",
    )
    warm = run_potential_field_inversion(
        "mvi", xyz, observed, standard_deviation, **warm_options
    )
    mesh, active, n = warm.mesh, warm.active, int(warm.active.sum())
    cap = _model_array(maximum, n, "MVI amplitude maximum")
    reference_cart = (
        np.zeros((n, 3))
        if options["reference_model"] is None
        else as_array(options["reference_model"], float).reshape((n, 3), order="F")
    )
    if np.any(np.linalg.norm(reference_cart, axis=1) > cap):
        raise ValueError("MVI reference amplitude exceeds mvi_amplitude_max")
    start = spherical_from_cartesian(warm.model.reshape((n, 3), order="F"))
    projected = start[:n] > cap
    start[:n] = np.minimum(start[:n], cap)
    reference = spherical_from_cartesian(reference_cart)
    warm_history = [
        dict(item, stage="cartesian", stage_iteration=item["iteration"])
        for item in warm.history
    ]
    # Warm simulations/directives form cycles in the SDK; release their matrices
    # before allocating the spherical operator, retaining only public results.
    gc.collect()
    field = warm.diagnostics["field"]
    receiver = magnetics.receivers.Point(as_array(xyz, float), components="tmi")
    survey = magnetics.survey.Survey(
        magnetics.sources.UniformBackgroundField(receiver_list=[receiver], **field)
    )
    mode = warm.diagnostics["sensitivity_mode"]
    storage = "forward_only" if mode == "matrix_free" else mode
    extra = (
        {}
        if not options["sensitivity_path"]
        else dict(sensitivity_path=options["sensitivity_path"])
    )
    sim = spherical_simulation(
        mesh,
        active,
        survey,
        cancel_callback=cancel,
        store_sensitivities=storage,
        sensitivity_dtype=np.dtype(options["sensitivity_dtype"]).type,
        **extra,
    )
    reg, scale = spherical_regularizer(
        mesh,
        active,
        reference,
        norms,
        angles,
        options["regularization_weights"],
        bool(options["reference_in_smooth"]),
        None
        if options["cell_weights"] is None
        else _model_array(options["cell_weights"], n, "Cell weights"),
    )
    lower = np.r_[np.zeros(n), np.full(n, -np.pi / 2), np.full(n, -np.inf)]
    upper = np.r_[cap, np.full(n, np.pi / 2), np.full(n, np.inf)]
    misfit = data_misfit.L2DataMisfit(
        simulation=sim,
        data=data.Data(
            survey,
            dobs=as_array(observed, float),
            standard_deviation=as_array(standard_deviation, float),
        ),
    )
    opt = spherical_optimizer(
        n,
        bounded_angles=int(options["irls_iterations"]) > 0,
        cancel_callback=cancel,
        maxIter=int(options["iterations"]),
        lower=lower,
        upper=upper,
        maxIterLS=20,
        cg_maxiter=int(options["cg_maxiter"]),
        cg_rtol=float(options["cg_rtol"]),
        tolF=options["optimizer_tol_f"],
        tolX=options["optimizer_tol_x"],
        tolG=options["optimizer_tol_g"],
    )
    problem = inverse_problem.BaseInvProblem(
        misfit, reg, opt, init_bfgs=False, beta=warm.diagnostics["final_beta"]
    )
    history, floors = [], []

    class ExactProjection(directives.InversionDirective):
        def project(self, update_cost=False):
            # Zero amplitude means unknown direction, not a known zero angle.
            # Preserve angular continuation through excluded/background cells.
            value = np.array(self.invProb.model, copy=True)
            value[:n] = np.minimum(value[:n], cap)
            value[2 * n :] = (value[2 * n :] + np.pi) % (2 * np.pi) - np.pi
            self.invProb.model = value
            self.opt.xc = value
            for simulation in self.simulation:
                simulation.model = value
            if update_cost:
                self.invProb.phi_m_last = [
                    objective(value) for objective in self.reg.objfcts
                ]

        def initialize(self):
            self.project()

        def endIter(self):
            self.project(True)

    class ExactJacobi(directives.UpdatePreconditioner):
        def initialize(self):
            diagonal = (
                2.0 * sim.getJtJdiag(self.invProb.model, W=misfit.W)
                + self.invProb.beta * reg.deriv2(self.invProb.model).diagonal()
            )
            if not np.isfinite(diagonal).all() or np.any(diagonal < 0):
                raise RuntimeError("Invalid spherical Hessian diagonal")
            floor = np.finfo(float).eps * max(float(diagonal.max()), 1.0)
            floors.append(int(np.count_nonzero(diagonal < floor)))
            self.opt.approxHinv = diags(1.0 / np.maximum(diagonal, floor), format="csr")

        def endIter(self):
            self.initialize()

    class Trace(directives.InversionDirective):
        def endIter(self):
            i = int(self.opt.iter)
            history.append(
                dict(
                    iteration=len(warm_history) + i,
                    stage="spherical",
                    stage_iteration=i,
                    phi_d=float(self.invProb.phi_d),
                    phi_m=float(self.invProb.phi_m),
                    beta=float(self.invProb.beta),
                    cg_scaled_relative_residual=opt.cg_scaled_rel_resid,
                    cg_scaled_tolerance_met=(
                        None
                        if opt.cg_scaled_rel_resid is None
                        else bool(opt.cg_scaled_rel_resid <= opt.cg_rtol)
                    ),
                    cg_breakdown=getattr(opt, "cg_breakdown", None),
                    cg_residual_replacements=int(opt.cg_residual_replacements),
                    **_cg_metrics(self.opt),
                )
            )
            if user_progress is not None:
                user_progress(len(warm_history) + i)
            if cancel is not None and cancel():
                raise RuntimeError("Spherical MVI canceled")

    class PriorSensitivity(directives.UpdateSensitivityWeights):
        @property
        def simulation(self):
            # Read-only adapter: retain the SDK's volume normalization,
            # thresholding and weight placement without mutating the simulation.
            from types import SimpleNamespace

            return [
                SimpleNamespace(
                    getJtJdiag=lambda m, W=None, f=None: sim.regularization_diagonal(
                        m, W, mvi_sensitivity_weights
                    )
                )
            ]

    # Match the reference event order; the preconditioner must see the beta
    # and regularization weights selected by all preceding directives.
    # Freeze angular and sensitivity priors inside each IRLS subproblem.
    sparse_updates = int(options["irls_iterations"]) > 0
    lagged = sparse_updates and mvi_irls_update == "lagged"
    if lagged:
        scale.endIter = lambda: None
    prior = PriorSensitivity(every_iteration=not lagged)
    jacobi = ExactJacobi()
    chart = spherical_chart_recovery(
        sim,
        misfit,
        reg,
        cap,
        float(options["target_chi"]) * sim.survey.nD,
        cancel,
    )

    def refresh(phase):
        if phase == "before":
            scale.update_scaling()
        else:
            chart.repair()
            prior.update()
            jacobi.initialize()

    controls = [scale, ExactProjection()]
    irls = None
    if int(options["irls_iterations"]) > 0:
        irls_options = dict(
            max_irls_iterations=int(options["irls_iterations"]),
            chifact_start=float(options["target_chi"]),
            chifact_target=float(options["target_chi"]),
            cooling_factor=float(options["beta_cooling_factor"]),
            cooling_rate=int(options["beta_cooling_rate"]),
        )
        irls = (
            lagged_irls_controller(
                refresh,
                max_epochs=int(options["iterations"]),
                cancel_callback=cancel,
                **irls_options,
            )
            if lagged
            else safeguarded_irls_type()(**irls_options)
        )
        controls.append(irls)
    else:
        controls.extend(
            [
                directives.BetaSchedule(
                    coolingFactor=float(options["beta_cooling_factor"]),
                    coolingRate=int(options["beta_cooling_rate"]),
                ),
                directives.TargetMisfit(chifact=float(options["target_chi"])),
            ]
        )
    controls.extend(
        [
            chart,
            prior,
            jacobi,
            Trace(),
        ]
    )
    recovered = inversion.BaseInversion(problem, directiveList=controls).run(start)
    if irls is not None and irls.stop_reason is None:
        irls.stop_reason = (
            "line_search_failed"
            if opt.spherical_search_failed
            else "newton_budget"
            if opt.iter >= opt.maxIter
            else "optimizer_stop"
        )
    chart = next(control for control in controls if hasattr(control, "reorientations"))
    predicted = np.asarray(sim.dpred(recovered))
    cartesian = cartesian_from_spherical(recovered)
    if cancel is not None and cancel():
        raise RuntimeError("Spherical MVI canceled")
    if not np.isfinite(cartesian).all() or not np.isfinite(predicted).all():
        raise RuntimeError("Spherical MVI returned non-finite output")
    wrms = float(
        np.sqrt(
            np.mean(
                ((as_array(observed) - predicted) / as_array(standard_deviation)) ** 2
            )
        )
    )
    diagnostics = dict(
        warm.diagnostics,
        weighted_rms=wrms,
        target_chi=float(options["target_chi"]),
        target_reached=wrms**2 <= float(options["target_chi"]),
        mvi_parameterization="spherical",
        mvi_regularization="separate_amplitude_and_periodic_angles",
        final_beta=float(problem.beta),
        cartesian_stage=warm.diagnostics,
        spherical_iterations=int(opt.iter),
        cartesian_iteration_budget=int(mvi_cartesian_iterations),
        spherical_iteration_budget=int(options["iterations"]),
        total_iteration_budget=int(mvi_cartesian_iterations)
        + int(options["iterations"]),
        iterations=len(warm_history) + int(opt.iter),
        irls_iterations=0 if irls is None else int(irls.metrics.irls_iteration_count),
        irls_iteration_budget=int(options["irls_iterations"]),
        irls_limit_reached=bool(
            irls is not None
            and irls.metrics.irls_iteration_count >= int(options["irls_iterations"])
        ),
        irls_update_mode=("frozen_subproblem" if lagged else "adaptive_per_step")
        if sparse_updates
        else "disabled",
        mvi_irls_update=mvi_irls_update,
        irls_inner_relative_tolerance=None if irls is None else irls.inner_rtol,
        irls_subproblems=[] if irls is None else irls.epochs,
        irls_inner_history=[] if irls is None else irls.inner_history,
        irls_stop_reason=None if irls is None else irls.stop_reason,
        irls_threshold_fallbacks=[] if irls is None else irls.threshold_fallbacks,
        iteration_limit_reached=int(opt.iter) >= int(options["iterations"]),
        preconditioner="Jacobi with exact mapped J.T Wd**2 J diagonal",
        mapped_solver_diagonal_cross_terms=True,
        mvi_sensitivity_weights=mvi_sensitivity_weights,
        jacobi_floor_max_count=max(floors, default=0),
        angular_retry_step_limit_rad=float(np.pi / 4),
        angular_step_mode="bounded_each_step"
        if sparse_updates
        else "retry_failed_search",
        angular_step_safeguard_events=opt.spherical_step_events,
        angular_line_search_retries=opt.spherical_line_search_retries,
        spherical_bound_step_scaling="component_Jacobi",
        spherical_bound_step_events=opt.spherical_bound_step_events,
        cg_residual_metric="raw_and_Jacobi_energy",
        cg_scaled_relative_residual=opt.cg_scaled_rel_resid,
        cg_scaled_tolerance_met=(
            None
            if opt.cg_scaled_rel_resid is None
            else bool(opt.cg_scaled_rel_resid <= opt.cg_rtol)
        ),
        cg_breakdown=getattr(opt, "cg_breakdown", None),
        cg_residual_replacements=int(opt.cg_residual_replacements),
        gradient_critical_tolerance=float(1000 * opt.eps),
        zero_amplitude_chart_reorientations=chart.reorientations,
        pole_chart_reorientations=chart.pole_reorientations,
        zero_amplitude_chart_events=chart.events,
        spherical_angle_norms=angles.tolist(),
        regularization_norms=norms.tolist(),
        mapped_gram_bytes=int(sim._physical_gram.nbytes),
        spherical_directive_order=[
            "angle_scale",
            "canonical_projection",
            "IRLS_or_beta_schedule",
            "zero_amplitude_chart_recovery",
            "sensitivity",
            "exact_Jacobi",
            "trace",
        ],
        fixed_parameter_count=int(np.count_nonzero(cap == 0)),
        free_parameter_count=3 * n - int(np.count_nonzero(cap == 0)),
        undefined_direction_cell_count=int(np.count_nonzero(recovered[:n] == 0)),
        spherical_internal_layout="amplitude SI, elevation angle from horizontal, azimuth from +east toward +north; radians",
        warm_amplitude_projection_count=int(projected.sum()),
        amplitude_max_range=[float(cap.min()), float(cap.max())],
        **_cg_metrics(opt),
        **_solver_history_metrics(warm_history + history),
    )
    return InversionResult(
        mesh, active, cartesian, predicted, "mvi", warm_history + history, diagnostics
    )

"""Fixed linear-Gaussian diagnostics without dense model-square matrices.

Direct Python callers may supply scipy sparse matrices or LinearOperators with
true adjoints. The registered array API uses ordinary numeric matrices. Neither
API turns a constrained, adaptive-beta or nonlinear fit into a Gaussian posterior.
"""

import numpy as np
import inspect
from scipy import sparse
from scipy.sparse.linalg import LinearOperator, aslinearoperator, cg

from ._array_contract import as_array
from ._calibration import integer_budget


class _System:
    def __init__(
        self,
        sensitivity,
        data_std,
        regularization,
        beta,
        cg_rtol,
        cg_maxiter,
        precision_diagonal,
        max_elements,
        max_matvecs,
        canceled,
    ):
        for value, name in (
            (cg_maxiter, "cg_maxiter"),
            (max_elements, "max_elements"),
            (max_matvecs, "max_matvecs"),
        ):
            integer_budget(value, name)
        if (
            not np.isfinite(beta)
            or beta <= 0
            or not np.isfinite(cg_rtol)
            or not 0 < cg_rtol < 1
        ):
            raise ValueError("Positive finite beta and CG tolerance in (0,1) required")
        self.calls = 0
        self.limit, self.canceled = max_matvecs, canceled
        self.rtol, self.maxiter, self.beta = cg_rtol, cg_maxiter, beta
        self.histories = []
        self.storage = 0
        self.g = self.operator(sensitivity, "sensitivity")
        self.l = self.operator(regularization, "regularization")
        self.n = self.g.shape[1]
        if np.iscomplexobj(data_std):
            raise ValueError("Data errors must be real")
        self.std = as_array(data_std, float)
        if (
            self.l.shape[1] != self.n
            or self.std.shape != (self.g.shape[0],)
            or not np.isfinite(self.std).all()
            or np.any(self.std <= 0)
        ):
            raise ValueError(
                "Matching G/L parameter counts and finite positive data errors required"
            )
        if (
            self.storage + 32 * self.n + 4 * (self.g.shape[0] + self.l.shape[0])
            > max_elements
        ):
            raise ValueError("Matrix-free diagnostic element budget exceeded")
        self.h = LinearOperator((self.n, self.n), matvec=self.precision, dtype=float)
        self.preconditioner = None
        if precision_diagonal is not None:
            diagonal = as_array(precision_diagonal, float)
            if (
                diagonal.shape != (self.n,)
                or not np.isfinite(diagonal).all()
                or np.any(diagonal <= 0)
            ):
                raise ValueError(
                    "Positive finite precision diagonal per parameter required"
                )
            self.preconditioner = LinearOperator(
                (self.n, self.n), matvec=lambda v: v / diagonal, dtype=float
            )
        # Catch common operator-adapter mistakes before random diagonal estimates
        # conceal them. This is a numerical adjoint check, not a rank certificate.
        rng = np.random.default_rng(913)
        for operator in (self.g, self.l):
            x, y = (
                rng.normal(size=operator.shape[1]),
                rng.normal(size=operator.shape[0]),
            )
            left, right = float(y @ operator.matvec(x)), float(x @ operator.rmatvec(y))
            if not np.isclose(
                left, right, rtol=1e-8, atol=1e-10 * max(abs(left), abs(right), 1.0)
            ):
                raise ValueError("Forward/adjoint operator consistency check failed")

    def check(self):
        if self.canceled is not None and self.canceled():
            raise InterruptedError("Matrix-free resolution canceled")

    def operator(self, value, name):
        if not isinstance(value, LinearOperator):
            if sparse.issparse(value):
                if np.iscomplexobj(value.data) or not np.isfinite(value.data).all():
                    raise ValueError(name + " must be real and finite")
                self.storage += value.nnz
            else:
                if np.iscomplexobj(value):
                    raise ValueError(name + " must be real")
                value = as_array(value, float)
                if value.ndim != 2 or not np.isfinite(value).all():
                    raise ValueError(
                        name + " requires a real finite matrix or LinearOperator"
                    )
                self.storage += value.size
        raw = aslinearoperator(value)
        if min(raw.shape) < 1 or np.dtype(raw.dtype).kind not in "fiu":
            raise ValueError(name + " requires a nonempty real operator")

        def action(v, transpose=False):
            self.check()
            self.calls += 1
            if self.calls > self.limit:
                raise ValueError("Matrix-free operator application budget exceeded")
            result = np.asarray(raw.rmatvec(v) if transpose else raw.matvec(v)).reshape(
                -1
            )
            size = raw.shape[1] if transpose else raw.shape[0]
            if (
                result.shape != (size,)
                or np.iscomplexobj(result)
                or not np.isfinite(result).all()
            ):
                raise ValueError(name + " returned an invalid operator product")
            return result

        return LinearOperator(
            raw.shape, matvec=action, rmatvec=lambda v: action(v, True), dtype=float
        )

    def gram(self, vector):
        return self.g.rmatvec(self.g.matvec(vector) / self.std**2)

    def precision(self, vector):
        result = self.gram(vector) + self.beta * self.l.rmatvec(self.l.matvec(vector))
        if not np.isfinite(result).all():
            raise ValueError("Precision arithmetic overflow; rescale units/noise")
        return result

    def solve(self, rhs):
        self.check()
        steps = 0

        def tick(_):
            nonlocal steps
            steps += 1
            self.check()

        tolerance = {
            "rtol" if "rtol" in inspect.signature(cg).parameters else "tol": self.rtol
        }
        solution, info = cg(
            self.h,
            rhs,
            **tolerance,
            atol=0.0,
            maxiter=self.maxiter,
            M=self.preconditioner,
            callback=tick,
        )
        norm = float(np.linalg.norm(rhs))
        residual = float(np.linalg.norm(self.precision(solution) - rhs))
        relative = residual / norm if norm else residual
        if (
            info != 0
            or not np.isfinite(solution).all()
            or not np.isfinite(relative)
            or relative > self.rtol
        ):
            raise ValueError(
                "Precision solve did not converge; inspect prior rank/conditioning or increase CG budget"
            )
        self.histories.append(dict(iterations=steps, relative_residual=relative))
        return solution


def stochastic_linear_resolution(
    sensitivity,
    data_std,
    regularization,
    *,
    beta,
    probe_count=64,
    seed=0,
    method="rademacher",
    cg_rtol=1e-8,
    cg_maxiter=1000,
    precision_diagonal=None,
    max_elements=20_000_000,
    max_matvecs=200_000,
    canceled=None,
):
    """Estimate diag(C), diag(R) and tr(R) with checked precision solves.

    H=G.T Wd^2 G+beta L.T L, C=H^-1, R=C G.T Wd^2 G. Independent
    Rademacher probes estimate diagonals without model-square storage. Returned
    Monte Carlo standard errors describe probing variability, not posterior
    error bars or finite-CG bias. Negative variance ESTIMATES remain flagged;
    their standard deviations are NaN instead of clipped. Basis mode computes
    exact diagonals up to CG tolerance for <=1024 parameters. A proper fixed
    Gaussian prior is required. Bounds and learned regularizers are excluded.
    """
    integer_budget(probe_count, "probe_count", 1 if method == "basis" else 2)
    integer_budget(seed, "seed", 0)
    if method not in ("rademacher", "basis"):
        raise ValueError("Choose rademacher or basis probing")
    system = _System(
        sensitivity,
        data_std,
        regularization,
        beta,
        cg_rtol,
        cg_maxiter,
        precision_diagonal,
        max_elements,
        max_matvecs,
        canceled,
    )
    if method == "basis" and (system.n > 1024 or probe_count != system.n):
        raise ValueError("Basis mode requires probe_count equal to <=1024 parameters")
    rng = np.random.default_rng(seed)
    mean = np.zeros((2, system.n))
    m2 = np.zeros_like(mean)
    trace_mean = trace_m2 = 0.0
    for i in range(probe_count):
        if method == "basis":
            vector = np.zeros(system.n)
            vector[i] = 1.0
        else:
            vector = rng.choice([-1.0, 1.0], size=system.n)
        covariance = system.solve(vector)
        resolution = system.solve(system.gram(vector))
        if method == "basis":
            mean[:, i] = covariance[i], resolution[i]
            trace_mean += resolution[i]
        else:
            sample = np.array([vector * covariance, vector * resolution])
            delta = sample - mean
            mean += delta / (i + 1)
            m2 += delta * (sample - mean)
            trace_sample = float(vector @ resolution)
            trace_delta = trace_sample - trace_mean
            trace_mean += trace_delta / (i + 1)
            trace_m2 += trace_delta * (trace_sample - trace_mean)
    error = (
        np.zeros_like(mean)
        if method == "basis"
        else np.sqrt(np.maximum(m2, 0.0) / (probe_count * (probe_count - 1)))
    )
    std = np.sqrt(np.where(mean[0] >= 0, mean[0], np.nan))
    return dict(
        posterior_variance_estimate=mean[0],
        posterior_std_estimate=std,
        resolution_diagonal_estimate=mean[1],
        probing_standard_error_variance=error[0],
        probing_standard_error_resolution=error[1],
        effective_parameters_estimate=trace_mean,
        effective_parameters_probing_standard_error=0.0
        if method == "basis"
        else float(np.sqrt(max(trace_m2, 0.0) / (probe_count * (probe_count - 1)))),
        negative_variance_estimates=mean[0] < 0,
        method=method,
        probe_count=int(probe_count),
        seed=int(seed),
        cg_history=system.histories,
        operator_applications=system.calls,
        scope="Fixed unconstrained linear Gaussian; no model-square matrices; no bound/IRLS/nonlinear posterior claim",
    )


def linear_point_spread(
    sensitivity,
    data_std,
    regularization,
    parameter_indices,
    *,
    beta,
    cg_rtol=1e-8,
    cg_maxiter=1000,
    precision_diagonal=None,
    max_elements=20_000_000,
    max_matvecs=200_000,
    canceled=None,
):
    """Selected C and R columns in supplied model coordinates, not spatial DOI.

    R[:,j] is the response to a unit true parameter j under the fixed linear
    inverse. This is a column, not an averaging-kernel row. C columns carry
    model covariance units; neither is clipped or normalized automatically.
    """
    system = _System(
        sensitivity,
        data_std,
        regularization,
        beta,
        cg_rtol,
        cg_maxiter,
        precision_diagonal,
        max_elements,
        max_matvecs,
        canceled,
    )
    indices = as_array(parameter_indices)
    if (
        indices.ndim != 1
        or indices.dtype.kind not in "iu"
        or not 1 <= len(indices) <= 32
        or np.any(indices < 0)
        or np.any(indices >= system.n)
        or len(np.unique(indices)) != len(indices)
    ):
        raise ValueError("Supply 1..32 distinct valid integer parameter indices")
    if (
        system.storage
        + system.n * (32 + 2 * len(indices))
        + 4 * (system.g.shape[0] + system.l.shape[0])
        > max_elements
    ):
        raise ValueError("Point-spread output element budget exceeded")
    c, r = [], []
    for index in indices:
        vector = np.zeros(system.n)
        vector[index] = 1.0
        c.append(system.solve(vector))
        r.append(system.solve(system.gram(vector)))
    return dict(
        parameter_indices=indices,
        covariance_columns=np.column_stack(c),
        resolution_columns=np.column_stack(r),
        cg_history=system.histories,
        operator_applications=system.calls,
        scope="Fixed linear Gaussian model-coordinate point-spread columns; not geological depth or nonlinear uncertainty",
    )

"""Analytic checks of the independent fixed-objective comparison harness."""

from types import SimpleNamespace

import numpy as np

from scripts.benchmark_mvi_solver_reference import linear_reference, nonlinear_reference


def test_reference_krylov_solvers_minimize_the_same_projected_quadratic():
    from scipy.sparse import csr_matrix, diags

    h = np.array([[4.0, 1.0, 9.0], [1.0, 3.0, 8.0], [9.0, 8.0, 100.0]])
    rhs = np.array([1.0, 2.0, 30.0])
    opt = SimpleNamespace(
        xc=np.zeros(3),
        g=-rhs,
        H=csr_matrix(h),
        approxHinv=diags(1 / np.diag(h)),
        cg_count=1,
        cg_rtol=1e-8,
        activeSet=lambda _: np.array([False, False, True]),
    )
    result = linear_reference(opt, np.zeros(3), budgets=(10,))
    expected = -0.5 * rhs[:2] @ np.linalg.solve(h[:2, :2], rhs[:2])
    assert result["free_parameters"] == 2
    assert result["cases"][0]["both_tolerances_met"] is False
    for case in result["cases"][1:]:
        assert case["both_tolerances_met"] is True
        np.testing.assert_allclose(case["quadratic_objective"], expected, atol=1e-12)
    assert (
        max(row["relative_symmetry_error"] for row in result["symmetry_probes"]) < 1e-12
    )


def test_reference_nonlinear_scaling_and_bounds_preserve_the_objective():
    diagonal = np.array([1e12, 2.0, 3.0])
    target = np.array([-2e-6, 0.4, 3.0])

    class Problem:
        def evalFunction(self, model, return_g=True, return_H=False):
            error = model - target
            return float(0.5 * error @ (diagonal * error)), diagonal * error

    lower, upper = np.zeros(3), np.array([1.0, 1.0, 2.0])
    model, result = nonlinear_reference(
        Problem(), np.array([1e-6, 0.1, 0.1]), diagonal, lower, upper, budget=50
    )
    np.testing.assert_allclose(model, np.clip(target, lower, upper), atol=1e-10)
    assert result["stationarity_passed"] is True
    assert result["final"]["iteration"] == result["history"][-1]["iteration"]
    assert result["final"]["objective"] <= result["history"][0]["objective"]

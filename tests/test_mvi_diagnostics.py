"""Independent fixed-L2 and volume-weighted numerical null-space controls."""

import numpy as np
import pytest

from terraworkbench_core.inversion_diagnostics import (
    fixed_l2_reference,
    linear_error_partition,
)


def test_fixed_l2_matches_analytic_nonzero_reference_ridge():
    sigma = np.array([2.0, 1.0, 0.5])
    data = np.array([3.0, -1.0, 2.0])
    reference = np.array([0.2, -0.1, 0.3])
    weights = np.array([0.5, 1.0, 2.0])
    beta = 0.7
    result = fixed_l2_reference(
        np.eye(3), data, sigma, np.diag(weights), beta=beta, reference_model=reference
    )
    expected = (data / sigma**2 + beta * weights**2 * reference) / (
        1 / sigma**2 + beta * weights**2
    )
    np.testing.assert_allclose(result["model"], expected, rtol=1e-13)
    assert result["scaled_optimality"] < 1e-13


def test_linear_error_partition_reconstructs_and_preserves_weighted_orthogonality():
    g = np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
    volumes = np.array([1.0, 2.0, 3.0])
    error = np.array([1.0, 3.0, -2.0])
    result = linear_error_partition(g, np.array([0.2, 2.0]), error, volumes)
    row, null = result["row_error"], result["null_error"]
    np.testing.assert_allclose(row + null, error)
    np.testing.assert_allclose(g @ null, 0.0, atol=1e-14)
    assert abs(np.dot(volumes * row, null)) < 1e-13
    assert result["rank"] == 2 and result["numerical_nullity"] == 1
    assert result["row_energy_fraction"] + result[
        "null_energy_fraction"
    ] == pytest.approx(1.0)


def test_exact_null_error_cannot_be_seen_by_data():
    g = np.array([[1.0, 0.0, 1.0]])
    result = linear_error_partition(
        g, np.ones(1), np.array([1.0, 0.0, -1.0]), np.ones(3)
    )
    assert result["null_energy_fraction"] == pytest.approx(1.0)
    assert result["row_energy_fraction"] < 1e-28


def test_zero_error_has_finite_zero_energy_fractions():
    result = linear_error_partition(np.eye(2), np.ones(2), np.zeros(2), np.ones(2))
    assert result["null_energy_fraction"] == result["row_energy_fraction"] == 0.0


def test_fixed_reference_rejects_nonunique_augmented_system():
    with pytest.raises(ValueError, match="full column rank"):
        fixed_l2_reference(
            np.array([[1.0, 0.0]]), np.ones(1), np.ones(1), np.zeros((0, 2)), beta=1.0
        )


@pytest.mark.parametrize("sigma", [[0.0, 1.0], [-1.0, 1.0], [np.nan, 1.0]])
def test_invalid_data_weights_are_rejected(sigma):
    with pytest.raises(ValueError, match="positive"):
        fixed_l2_reference(np.eye(2), np.ones(2), sigma, np.eye(2), beta=1.0)
    with pytest.raises(ValueError, match="positive"):
        linear_error_partition(np.eye(2), sigma, np.ones(2), np.ones(2))


def test_dense_diagnostics_enforce_memory_budgets():
    with pytest.raises(ValueError, match="budget"):
        fixed_l2_reference(
            np.eye(3), np.ones(3), np.ones(3), np.eye(3), beta=1.0, max_elements=1
        )
    with pytest.raises(ValueError, match="budget"):
        linear_error_partition(
            np.eye(3), np.ones(3), np.ones(3), np.ones(3), max_elements=1
        )


@pytest.mark.parametrize("budget", [0, 1.5, float("nan"), True])
def test_invalid_dense_budgets_cannot_bypass_limits(budget):
    with pytest.raises(ValueError):
        fixed_l2_reference(
            np.eye(2), np.ones(2), np.ones(2), np.eye(2), beta=1.0, max_elements=budget
        )
    with pytest.raises(ValueError):
        linear_error_partition(
            np.eye(2), np.ones(2), np.ones(2), np.ones(2), max_elements=budget
        )


def test_true_projected_cg_residual_matches_independent_reduced_system():
    pytest.importorskip("simpeg")
    from scipy.sparse import csr_matrix, diags
    from terraworkbench_core.inversion import _jacobi_optimizer, _cg_metrics

    h = np.array([[4.0, 1.0, 0.2], [1.0, 3.0, 0.1], [0.2, 0.1, 2.0]])
    opt = _jacobi_optimizer(
        lower=np.array([0.0, -10.0, -10.0]),
        upper=np.full(3, 10.0),
        cg_rtol=1e-12,
        cg_maxiter=20,
    )
    opt.xc = np.array([0.0, 0.3, -0.1])
    opt.g = np.array([-1.0, 2.0, -3.0])
    opt.H = csr_matrix(h)
    opt.approxHinv = diags(1 / np.diag(h))
    direction = opt.findSearchDirection()
    expected = np.linalg.solve(h[1:, 1:], -opt.g[1:])
    np.testing.assert_allclose(direction[1:], expected, rtol=1e-12)
    metrics = _cg_metrics(opt)
    assert metrics["cg_solver_mode"] == "projected_cg"
    assert metrics["cg_true_tolerance_met"]
    assert metrics["cg_true_relative_residual"] < 1e-12
    assert direction[0] > 0.0


def test_bound_descent_is_not_certified_as_a_cg_solve():
    pytest.importorskip("simpeg")
    from scipy.sparse import eye
    from terraworkbench_core.inversion import (
        _jacobi_optimizer,
        _cg_metrics,
        _solver_history_metrics,
    )

    opt = _jacobi_optimizer(lower=0.0, upper=1.0)
    opt.xc = np.zeros(2)
    opt.g = -np.ones(2)
    opt.H = eye(2)
    opt.approxHinv = eye(2)
    np.testing.assert_allclose(opt.findSearchDirection(), 1.0)
    metrics = _cg_metrics(opt)
    assert metrics["cg_solver_mode"] == "bound_start_descent"
    assert metrics["cg_true_tolerance_met"] is None
    assert _solver_history_metrics([metrics])["all_audited_cg_tolerances_met"] is None


def test_kkt_gradient_is_not_artificially_small_for_a_narrow_box():
    from scripts.diagnose_mvi import kkt_gradient

    np.testing.assert_allclose(
        kkt_gradient(
            np.array([0.0, 0.01, -0.01]), np.array([1e6, -1e6, 1e6]), -0.01, 0.01
        ),
        [1e6, 0.0, 0.0],
    )


def test_multiple_errors_reuse_one_subspace_and_handle_zero_columns():
    g = np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
    error = np.array([[1.0, 0.0], [3.0, 0.0], [-2.0, 0.0]])
    result = linear_error_partition(g, np.ones(2), error, np.ones(3))
    np.testing.assert_allclose(result["row_error"] + result["null_error"], error)
    np.testing.assert_allclose(g @ result["null_error"], 0.0, atol=1e-14)
    assert result["null_energy_fraction"][1] == result["row_energy_fraction"][1] == 0.0


def test_final_cg_success_does_not_hide_an_earlier_failure():
    from terraworkbench_core.inversion import _solver_history_metrics

    history = [
        dict(cg_solver_mode="projected_cg", cg_true_tolerance_met=False),
        dict(cg_solver_mode="bound_start_descent", cg_true_tolerance_met=None),
        dict(cg_solver_mode="projected_cg", cg_true_tolerance_met=True),
    ]
    result = _solver_history_metrics(history)
    assert result["cg_audited_solves"] == 2
    assert result["cg_failed_true_tolerance_count"] == 1
    assert result["all_audited_cg_tolerances_met"] is False
    assert result["bound_descent_step_count"] == 1


@pytest.mark.parametrize(
    "history, raw_count, scaled_count, failed",
    [
        ([dict(cg_true_tolerance_met=True, cg_scaled_tolerance_met=False)], 1, 1, 1),
        ([dict(cg_true_tolerance_met=False, cg_scaled_tolerance_met=False)], 1, 1, 1),
        (
            [
                dict(cg_true_tolerance_met=True),
                dict(cg_true_tolerance_met=True, cg_scaled_tolerance_met=True),
            ],
            2,
            1,
            0,
        ),
        ([dict(cg_true_tolerance_met=None, cg_scaled_tolerance_met=None)], 0, 0, 0),
        ([dict(cg_scaled_tolerance_met=False)], 0, 1, 1),
    ],
)
def test_solver_summary_checks_all_recorded_residual_norms(
    history, raw_count, scaled_count, failed
):
    from terraworkbench_core.inversion import _solver_history_metrics

    result = _solver_history_metrics(history)
    assert result["cg_audited_solves"] == raw_count
    assert result["cg_audited_scaled_solves"] == scaled_count
    assert result["cg_failed_either_tolerance_count"] == failed
    expected = not failed if raw_count or scaled_count else None
    assert result["all_audited_cg_tolerances_met"] is expected


@pytest.mark.parametrize(
    "case, raw, scaled, raw_failed, scaled_failed",
    [
        ("adaptive40", 48, 43, 0, 0),
        ("adaptive80", 88, 83, 20, 18),
        ("precision_control", 88, 83, 14, 9),
    ],
)
def test_solver_summary_preserves_archived_mvi_outcomes(
    case, raw, scaled, raw_failed, scaled_failed
):
    import json
    from pathlib import Path
    from terraworkbench_core.inversion import _solver_history_metrics

    archive = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs/validation/records/mvi_outer_20261105.json"
        ).read_text(encoding="utf-8")
    )
    result = (
        archive[case]["cases"][0]
        if case == "precision_control"
        else archive["results"][case]
    )
    metrics = _solver_history_metrics(result["history"])
    assert metrics["cg_audited_solves"] == raw
    assert metrics["cg_audited_scaled_solves"] == scaled
    assert metrics["cg_failed_true_tolerance_count"] == raw_failed
    assert metrics["cg_failed_scaled_tolerance_count"] == scaled_failed
    # In these historical cases every scaled failure also failed the raw test.
    assert metrics["cg_failed_either_tolerance_count"] == raw_failed
    assert metrics["all_audited_cg_tolerances_met"] is (raw_failed == 0)

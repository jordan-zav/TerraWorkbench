"""Same-objective counterexamples: tolerance, angular steps and zero charts."""

import numpy as np
import pytest

pytest.importorskip("simpeg")


def test_critical_gradient_floor_cannot_override_requested_tolerance():
    from terraworkbench_core.spherical_mvi import spherical_optimizer

    opt = spherical_optimizer(1, tolG=1e-10, eps=1e-5)
    assert 1000 * opt.eps <= 1.0000001e-10


def test_clipped_angular_step_falls_back_if_descent_is_lost():
    from scipy.sparse import eye
    from terraworkbench_core.spherical_mvi import spherical_optimizer

    opt = spherical_optimizer(
        1,
        lower=np.array([0.0, -np.pi / 2, -np.inf]),
        upper=np.array([1.0, np.pi / 2, np.inf]),
    )
    opt.xc = np.array([0.5, 0.0, 0.0])
    opt.iter = 0
    opt.g = np.array([1.0, 100.0, 1.0])
    opt.approxHinv = eye(3)
    p = opt.spherical_retry_direction(np.array([100.0, 1e8, -2e10]))
    assert max(abs(p[1:])) <= np.pi / 4
    assert opt.g @ p < 0
    assert opt.spherical_step_events[-1]["diagonal_gradient_fallback"]


def test_zero_chart_repair_preserves_physics_and_respects_exclusions():
    from terraworkbench_core.spherical_mvi import (
        zero_amplitude_chart_candidate,
        exact_spherical_map,
    )

    mapping = exact_spherical_map(2)
    start = np.zeros(6)
    physical = np.array([0.0, 0.0, -2.0, -3.0, -1.0, -1.0])
    candidate, count = zero_amplitude_chart_candidate(
        start,
        physical,
        np.array([0.0, 1.0]),
        lambda value: 0.0,
        lambda value: mapping.deriv(value).T @ physical,
    )
    assert count == 1
    np.testing.assert_array_equal(mapping * start, mapping * candidate)
    assert candidate[2] == candidate[4] == 0.0  # excluded cell angles stay untouched
    assert (mapping.deriv(candidate).T @ physical)[1] < 0


def test_zero_chart_repair_cannot_increase_a_fixed_direction_prior():
    from terraworkbench_core.spherical_mvi import (
        zero_amplitude_chart_candidate,
        exact_spherical_map,
    )

    mapping = exact_spherical_map(1)
    start = np.zeros(3)
    physical = np.array([0.0, -1.0, -1.0])
    candidate, count = zero_amplitude_chart_candidate(
        start,
        physical,
        np.ones(1),
        lambda value: float(value[1:] @ value[1:]),
        lambda value: mapping.deriv(value).T @ physical + np.r_[0.0, 2 * value[1:]],
    )
    np.testing.assert_array_equal(candidate, start)
    assert count == 0


@pytest.mark.parametrize("name", ["zero", "tiny", "opposite", "regular"])
def test_guarded_solver_recovers_independent_fixed_objective(name):
    from scripts.benchmark_mvi_stability import case

    result = case(name, "guarded")
    assert result["passed"], result


def test_opposite_direction_is_a_real_legacy_stall():
    from scripts.benchmark_mvi_stability import case

    result = case("opposite", "legacy")
    assert not result["passed"]
    assert result["weighted_rms"] > 1.0


def test_zero_chart_recovery_also_works_without_a_stored_matrix():
    from scripts.benchmark_mvi_stability import case

    result = case("opposite", "guarded", sensitivity_mode="forward_only")
    assert result["passed"], result
    assert result["chart_reorientations"] > 0


def test_successful_newton_step_is_not_changed_by_angular_retry():
    from terraworkbench_core.spherical_mvi import spherical_optimizer

    opt = spherical_optimizer(
        1,
        lower=np.array([0.0, -np.pi / 2, -np.inf]),
        upper=np.array([1.0, np.pi / 2, np.inf]),
    )
    opt.xc = np.array([0.2, 0.0, 0.0])
    opt.iter = 0
    target = np.array([0.3, 1.0, 2.0])
    opt.g = opt.xc - target
    opt.f = float(0.5 * np.linalg.norm(opt.g) ** 2)
    opt.evalFunction = lambda value, **kwargs: float(
        0.5 * np.linalg.norm(value - target) ** 2
    )
    value, passed = opt.modifySearchDirection(target - opt.xc)
    assert passed
    np.testing.assert_allclose(value, target)
    assert opt.spherical_line_search_retries == []


def test_small_interior_value_is_not_mistaken_for_stationarity():
    from scipy.sparse import eye
    from terraworkbench_core.inversion import _jacobi_optimizer

    opt = _jacobi_optimizer(
        lower=0.0, upper=1.0, maxIter=5, tolG=1e-8, cg_maxiter=5, cg_rtol=1e-12
    )
    opt.approxHinv = eye(1)

    def objective(value, return_g=False, return_H=False):
        result = (float(0.5 * np.sum((value + 1.0) ** 2)),)
        if return_g:
            result += (value + 1.0,)
        if return_H:
            result += (eye(1),)
        return result[0] if len(result) == 1 else result

    model = opt.minimize(objective, np.array([0.005]))
    np.testing.assert_array_equal(model, 0.0)
    assert opt.iter > 0


def test_tight_tolerance_alone_cannot_fix_zero_chart():
    from scripts.benchmark_mvi_stability import case

    result = case("opposite", "tight_only")
    assert not result["passed"]
    assert result["weighted_rms"] > 1.0


def test_angular_retry_recovers_a_failed_twenty_backtrack_search():
    from scripts.benchmark_mvi_stability import case

    baseline = case("tiny", "tight_only")
    corrected = case("tiny", "step_only")
    assert not baseline["passed"] and baseline["last_line_search_backtracks"] == 20
    assert corrected["passed"]
    assert any(event["accepted"] for event in corrected["line_search_retry_events"])

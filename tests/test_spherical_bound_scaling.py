"""An unrelated angular curvature must not determine an amplitude bound step."""

import numpy as np
import pytest

pytest.importorskip("simpeg")


@pytest.mark.parametrize("angular_curvature", [1e-8, 1e-12])
def test_free_bound_step_uses_its_own_curvature(angular_curvature):
    from scipy.sparse import diags
    from terraworkbench_core.inversion import _jacobi_optimizer
    from terraworkbench_core.spherical_mvi import spherical_optimizer

    def step(factory):
        opt = factory(
            lower=np.array([0.0, -np.inf, -np.inf]),
            upper=np.array([10.0, np.inf, np.inf]),
            cg_maxiter=10,
            cg_rtol=1e-12,
        )
        opt.iter = 0
        opt.xc = np.zeros(3)
        opt.g = np.array([-100.0, -1.0, 0.0])
        opt.H = diags([100.0, angular_curvature, 1.0])
        opt.approxHinv = diags([0.01, 1 / angular_curvature, 1.0])
        result = opt.findSearchDirection()
        assert opt.cg_true_rel_resid <= 1e-12
        return opt, result

    old, old_step = step(_jacobi_optimizer)
    opt, p = step(lambda **kwargs: spherical_optimizer(1, **kwargs))
    # The independent diagonal quadratic minimizer has amplitude exactly one.
    assert old_step[0] > 1e4
    assert p[0] == pytest.approx(1.0)
    np.testing.assert_array_equal(p[1:], old_step[1:])
    assert opt.g @ p < 0
    assert opt.spherical_bound_step_events[0]["sdk_counterfactual_max_abs"] > 1e4


@pytest.mark.parametrize("angles", [[0.1, 0.2], [10.0, 1e8]])
def test_bounded_inner_step_limits_angles_and_keeps_descent(angles):
    from scipy.sparse import eye
    from terraworkbench_core.spherical_mvi import spherical_optimizer

    opt = spherical_optimizer(
        1,
        bounded_angles=True,
        lower=np.array([0.0, -np.pi / 2, -np.inf]),
        upper=np.array([1.0, np.pi / 2, np.inf]),
    )
    opt.xc = np.array([0.1, 0.0, 0.0])
    opt.iter = 0
    p = np.array([0.01, *angles])
    opt.g = -p
    opt.approxHinv = eye(3)
    scaled = opt.scaleSearchDirection(p)
    assert max(abs(scaled[1:])) <= np.pi / 4
    assert opt.g @ scaled < 0
    assert scaled[0] == p[0]
    if max(angles) < np.pi / 4:
        np.testing.assert_array_equal(scaled, p)


def test_failed_search_recovers_with_feasible_projected_gradient():
    from scipy.sparse import eye
    from terraworkbench_core.spherical_mvi import spherical_optimizer

    opt = spherical_optimizer(
        1,
        bounded_angles=True,
        maxIterLS=20,
        lower=np.array([0.0, -np.pi / 2, -np.inf]),
        upper=np.array([1.0, np.pi / 2, np.inf]),
    )
    opt.xc = np.array([0.1, 0.0, 0.0])
    opt.iter = 0
    target = np.array([0.5, 0.0, 0.0])
    opt.g = opt.xc - target
    opt.f = float(0.5 * sum(opt.g**2))
    opt.approxHinv = 1e20 * eye(3)
    opt.evalFunction = lambda value, **kwargs: float(0.5 * sum((value - target) ** 2))
    result, passed = opt.modifySearchDirection(np.array([1e40, 0.0, 0.0]))
    assert passed
    assert opt.evalFunction(result) < opt.f
    event = opt.spherical_line_search_retries[-1]
    assert event["kind"] == "projected_Jacobi" and event["accepted"]
    assert event["original_backtracks"] == 20

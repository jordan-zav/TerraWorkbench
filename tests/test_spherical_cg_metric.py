"""A raw mixed-unit CG residual can hide an unresolved angular subproblem."""

import numpy as np
import pytest

pytest.importorskip("simpeg")


def solve(factory):
    from scipy.sparse import diags
    from scipy.sparse.linalg import aslinearoperator

    scale = np.array([1e6, 1.0, 1.0])
    canonical = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.8], [0.0, 0.8, 1.0]])
    h = scale[:, None] * canonical * scale[None, :]
    rhs = scale * np.array([1.0, 1.0, 0.0])
    opt = factory(cg_maxiter=20, cg_rtol=1e-4)
    opt.iter = 0
    opt.xc = np.zeros(3)
    opt.g = -rhs
    opt.H = aslinearoperator(h)
    opt.approxHinv = diags(1 / np.diag(h))
    step = opt.findSearchDirection()
    residual = h @ step - rhs
    raw = np.linalg.norm(residual) / np.linalg.norm(rhs)
    scaled = np.linalg.norm(residual / scale) / np.linalg.norm(rhs / scale)
    return opt, step, np.linalg.solve(h, rhs), raw, scaled


def test_raw_sdk_stopping_really_hides_large_angular_error():
    from terraworkbench_core.inversion import _jacobi_optimizer

    opt, step, expected, raw, scaled = solve(_jacobi_optimizer)
    assert raw <= opt.cg_rtol
    assert scaled > 0.5
    assert np.linalg.norm(step - expected) / np.linalg.norm(expected) > 0.5


def test_spherical_cg_checks_raw_and_scaled_residuals():
    from terraworkbench_core.spherical_mvi import spherical_optimizer

    opt, step, expected, raw, scaled = solve(lambda **kw: spherical_optimizer(1, **kw))
    assert raw <= opt.cg_rtol
    assert scaled <= opt.cg_rtol
    np.testing.assert_allclose(step, expected, rtol=1e-10, atol=1e-12)


def test_history_rejects_the_raw_only_mixed_unit_counterexample():
    from terraworkbench_core.inversion import (
        _cg_metrics,
        _jacobi_optimizer,
        _solver_history_metrics,
    )

    opt, _, _, _, scaled = solve(_jacobi_optimizer)
    metrics = _cg_metrics(opt)
    assert metrics["cg_true_tolerance_met"] is True
    metrics["cg_scaled_tolerance_met"] = bool(scaled <= opt.cg_rtol)
    result = _solver_history_metrics([metrics])
    assert result["cg_failed_true_tolerance_count"] == 0
    assert result["cg_failed_scaled_tolerance_count"] == 1
    assert result["cg_failed_either_tolerance_count"] == 1
    assert result["all_audited_cg_tolerances_met"] is False


def test_scaled_cg_honors_cancellation_between_products():
    from terraworkbench_core.spherical_mvi import spherical_optimizer

    calls = []

    def cancel():
        calls.append(1)
        return len(calls) >= 2

    with pytest.raises(RuntimeError, match="canceled"):
        solve(lambda **kw: spherical_optimizer(1, cancel_callback=cancel, **kw))
    assert len(calls) == 2


def test_spherical_cg_never_creates_a_bfgs_fallback():
    from terraworkbench_core.spherical_mvi import spherical_optimizer

    opt = spherical_optimizer(1)
    opt.xc = np.zeros(3)
    opt.g = np.ones(3)
    with pytest.raises(RuntimeError, match="Jacobi"):
        opt.findSearchDirection()

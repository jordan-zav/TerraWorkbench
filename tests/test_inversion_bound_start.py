"""Bound starts must be able to enter the feasible model interior."""

import numpy as np
import pytest

pytest.importorskip("simpeg")


def test_jacobi_direction_releases_inward_bound_variables():
    from scipy.sparse import diags
    from terraworkbench_core.inversion import _jacobi_optimizer

    optimizer = _jacobi_optimizer(lower=0.0, upper=1.0, maxIter=2)
    optimizer.xc = np.zeros(3)
    optimizer.g = np.array([-2.0, -3.0, 4.0])
    optimizer._approxHinv = diags([0.5, 0.25, 1.0])
    np.testing.assert_allclose(optimizer.findSearchDirection(), [1.0, 0.75, 0.0])
    assert optimizer.cg_count == 0 and np.isfinite(optimizer.cg_rel_resid)


def test_jacobi_direction_is_zero_when_all_bounds_are_binding():
    from scipy.sparse import eye
    from terraworkbench_core.inversion import _jacobi_optimizer

    optimizer = _jacobi_optimizer(lower=0.0, upper=1.0, maxIter=2)
    optimizer.xc = np.zeros(2)
    optimizer.g = np.array([2.0, 3.0])
    optimizer._approxHinv = eye(2)
    np.testing.assert_array_equal(optimizer.findSearchDirection(), [0.0, 0.0])
    assert optimizer.cg_rel_resid == 0

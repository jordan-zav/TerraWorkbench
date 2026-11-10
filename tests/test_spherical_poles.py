"""Polar azimuth is physically undefined; repair must preserve M and the prior."""

import numpy as np
import pytest

pytest.importorskip("simpeg")


@pytest.mark.parametrize("sign", [-1.0, 1.0])
def test_pole_reorientation_preserves_physics_and_opens_feasible_descent(sign):
    from terraworkbench_core.spherical_mvi import (
        exact_spherical_map,
        pole_chart_candidate,
    )

    mapping = exact_spherical_map(1)
    model = np.array([0.03, sign * np.pi / 2, 0.0])
    physical = np.array([1.0, 1.0, 0.0])

    def gradient(value):
        return mapping.deriv(value).T @ physical

    candidate, count = pole_chart_candidate(
        model, physical, np.ones(1), lambda value: 0.0, gradient
    )
    assert count == 1
    np.testing.assert_array_equal(mapping * model, mapping * candidate)
    assert sign * gradient(candidate)[1] > 0
    # Finite differences independently check the singular-point Jacobian.
    jac = mapping.deriv(candidate).toarray()
    for index in range(3):
        delta = np.zeros(3)
        delta[index] = 1e-6
        finite = (mapping * (candidate + delta) - mapping * (candidate - delta)) / (
            2e-6
        )
        np.testing.assert_allclose(finite, jac[:, index], rtol=1e-8, atol=1e-10)


def test_pole_repair_respects_a_fixed_azimuth_prior_and_excluded_cells():
    from terraworkbench_core.spherical_mvi import (
        exact_spherical_map,
        pole_chart_candidate,
    )

    mapping = exact_spherical_map(1)
    model = np.array([0.03, np.pi / 2, 0.0])
    physical = np.array([1.0, 1.0, 0.0])

    def gradient(value):
        return mapping.deriv(value).T @ physical

    for caps, cost in [(np.zeros(1), lambda v: 0.0), (np.ones(1), lambda v: v[2] ** 2)]:
        candidate, count = pole_chart_candidate(model, physical, caps, cost, gradient)
        assert count == 0
        np.testing.assert_array_equal(candidate, model)

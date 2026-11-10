import numpy as np
import pytest

from terraworkbench_core.compact_magnetics import (
    magnetic_dipole_field,
    fit_magnetic_dipoles,
)


def survey():
    x, y = np.meshgrid(np.linspace(-10, 10, 7), np.linspace(-10, 10, 7))
    return np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))


def test_dipole_forward_against_independent_harmonica():
    hm = pytest.importorskip("harmonica")
    points = survey()
    sources = np.array([[1.0, 2.0, -5.0], [-3.0, -2.0, -7.0]])
    moments = np.array([[2.0, -1.0, -4.0], [1.0, 3.0, 2.0]])
    actual = magnetic_dipole_field(
        points, sources, moments, minimum_distance_m=0.1, block_size=3
    )["field_enu_nt"]
    expected = np.array(
        hm.dipole_magnetic(
            tuple(points.T), tuple(sources.T), tuple(moments.T), field="b"
        )
    ).T
    np.testing.assert_allclose(actual, expected, rtol=1e-8, atol=1e-9)


@pytest.mark.parametrize("shift", [np.zeros(3), np.array([500000.0, 6000000.0, 100.0])])
def test_seeded_fit_recovers_position_and_free_moment(shift):
    points = survey()
    position, moment = np.array([[1.0, 2.0, -5.0]]), np.array([[2.0, -1.0, -4.0]])
    data = magnetic_dipole_field(points, position, moment, minimum_distance_m=0.1)[
        "field_enu_nt"
    ]
    points = points + shift
    position = position + shift
    result = fit_magnetic_dipoles(
        points,
        data,
        0.05,
        position + 0.3,
        moment * 0.8,
        np.array([-4, -4, -9]) + shift,
        np.array([4, 4, -2]) + shift,
        [-10, -10, -10],
        [10, 10, 10],
        minimum_distance_m=0.1,
    )
    assert result["success"] and result["locally_full_rank"]
    np.testing.assert_allclose(result["source_xyz"], position, atol=1e-5)
    np.testing.assert_allclose(result["moments_a_m2"], moment, atol=1e-5)
    assert np.max(abs(result["residual_nt"])) < 1e-6
    assert result["local_covariance"].shape == (6, 6)


def test_total_field_fit_reports_unidentifiable_line_geometry():
    points = np.column_stack((np.linspace(-10, 10, 21), np.zeros(21), np.zeros(21)))
    position, moment = [[0, 0, -5]], [[0, 0, -4]]
    data = -magnetic_dipole_field(points, position, moment, minimum_distance_m=0.1)[
        "field_enu_nt"
    ][:, 2]
    result = fit_magnetic_dipoles(
        points,
        data,
        0.05,
        position,
        moment,
        [-2, -2, -8],
        [2, 2, -2],
        [-10, -10, -10],
        [10, 10, 10],
        minimum_distance_m=0.1,
        component="total",
        inclination=90,
        declination=0,
    )
    assert not result["locally_full_rank"] and not result["success"]
    assert result["local_covariance"] is None


def test_compact_bounds_singularities_budgets_and_cancellation():
    points = survey()
    with pytest.raises(ValueError):
        magnetic_dipole_field(points, points[:1], [[1, 1, 1]], minimum_distance_m=0.1)
    with pytest.raises(RuntimeError, match="canceled"):
        magnetic_dipole_field(
            points,
            [[0, 0, -5]],
            [[1, 1, 1]],
            minimum_distance_m=0.1,
            canceled=lambda: True,
        )
    data = np.zeros_like(points)
    options = dict(
        observation_xyz=points,
        observed_nt=data,
        data_std_nt=1,
        initial_xyz=[[0, 0, -5]],
        initial_moments_a_m2=[[1, 1, 1]],
        position_lower=[-2, -2, -8],
        position_upper=[2, 2, -2],
        moment_lower=[-10] * 3,
        moment_upper=[10] * 3,
        minimum_distance_m=0.1,
    )
    with pytest.raises(RuntimeError, match="budget"):
        fit_magnetic_dipoles(**options, max_forward_calls=1)
    with pytest.raises(ValueError, match="upper bounds"):
        fit_magnetic_dipoles(**dict(options, position_upper=[2, 2, 0]))

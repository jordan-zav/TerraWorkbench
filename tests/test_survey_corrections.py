import numpy as np
import pytest

from survey_corrections import (
    azimuth_from_velocity,
    eotvos_correction,
    hampel_filter_1d,
    heading_correction,
    interpolate_base_variation,
    lag_shift,
    linear_drift,
    rotate_grid_velocity_to_true,
    segment_velocity,
)


def test_base_variation_interpolates_inside_and_rejects_extrapolation():
    result = interpolate_base_variation(
        [-1.0, 0.0, 5.0, 10.0, 11.0], [0.0, 10.0], [50000.0, 50010.0]
    )
    assert np.isnan(result[0]) and np.isnan(result[-1])
    assert np.allclose(result[1:4], [-5.0, 0.0, 5.0])


def test_signed_lag_samples_time_plus_lag_without_extrapolation():
    result = lag_shift([0.0, 1.0, 2.0, 3.0], [0.0, 10.0, 20.0, 30.0], 1.0)
    assert np.allclose(result[:3], [10.0, 20.0, 30.0])
    assert np.isnan(result[-1])


def test_hampel_replaces_isolated_spike():
    result, replaced = hampel_filter_1d([1, 1, 1, 100, 1, 1, 1], 2, 4.0)
    assert result[3] == 1.0
    assert replaced.sum() == 1


def test_heading_first_harmonic_uses_clockwise_azimuth():
    result = heading_correction([0.0, 90.0, 180.0, 270.0], 2.0, 3.0)
    assert np.allclose(result, [2.0, 3.0, -2.0, -3.0], atol=1e-12)


def test_velocity_azimuth_eotvos_and_drift_have_expected_units():
    east, north = segment_velocity([0, 10, 20], [0, 0, 0], [0, 1, 2])
    assert np.allclose(east, 10.0)
    assert np.allclose(north, 0.0)
    assert np.allclose(azimuth_from_velocity(east, north), 90.0)
    expected = (2 * 7.2921150e-5 * 10 + 100 / 6_371_008.8) * 1e5
    assert eotvos_correction(0.0, east, north)[1] == pytest.approx(expected)
    assert np.allclose(linear_drift([0, 1800, 3600], 2.0), [0.0, 1.0, 2.0])


def test_grid_velocity_is_rotated_to_true_axes_before_heading_and_eotvos():
    # A true-north vector has a +10 degree azimuth in grid coordinates when
    # true north lies 10 degrees clockwise from grid north.
    grid_east = np.sin(np.deg2rad(10.0))
    grid_north = np.cos(np.deg2rad(10.0))
    true_east, true_north = rotate_grid_velocity_to_true(
        grid_east, grid_north, 10.0
    )
    assert true_east == pytest.approx(0.0, abs=1e-12)
    assert true_north == pytest.approx(1.0)

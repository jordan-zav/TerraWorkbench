"""Numerical tests for gamma-ray spectrometry products and corrections."""

import numpy as np
import pytest

from radiometry import (
    alteration_f_parameter,
    background_correction,
    channel_qc,
    dead_time_correction,
    height_attenuation_correction,
    median_mad_despike,
    safe_ratio,
    sensitivity_calibration,
    spectral_unmix,
    terrestrial_dose_rate,
    ternary_rgb,
)


def test_ratio_masks_zero_small_and_nonfinite_denominators():
    result = safe_ratio([4.0, 4.0, np.nan, 4.0], [2.0, 0.0, 2.0, 0.01], 0.1)
    assert result[0] == pytest.approx(2.0)
    assert np.all(np.isnan(result[1:]))


def test_dose_rate_and_f_parameter_follow_declared_equations():
    dose = terrestrial_dose_rate([1.0], [2.0], [3.0])
    assert dose[0] == pytest.approx(13.078 + 2 * 5.675 + 3 * 2.494)
    assert alteration_f_parameter([2.0], [6.0], [3.0])[0] == pytest.approx(4.0)


def test_ternary_uses_k_red_th_green_u_blue_and_can_normalize():
    k = np.array([[0.0, 10.0], [5.0, 7.5]])
    u = np.array([[0.0, 2.0], [1.0, 1.5]])
    th = np.array([[0.0, 20.0], [10.0, 15.0]])
    rgb = ternary_rgb(k, u, th, 0.0, 100.0)
    assert rgb.shape == (3, 2, 2)
    assert np.array_equal(rgb[:, 0, 1], [255.0, 255.0, 255.0])
    normalized = ternary_rgb(k, u, th, 0.0, 100.0, normalize=True)
    assert np.allclose(normalized[:, 0, 1], [85.0, 85.0, 85.0])


def test_raw_count_corrections_require_explicit_coefficients():
    assert dead_time_correction([1000.0], 0.0001)[0] == pytest.approx(1111.111111)
    with pytest.raises(ValueError, match="non-positive"):
        dead_time_correction([1000.0], 0.001)
    assert background_correction([100.0], 10.0, 5.0, 2.0)[0] == 83.0
    assert height_attenuation_correction([10.0], [120.0], 100.0, 0.01)[0] == pytest.approx(10.0 * np.exp(0.2))
    assert sensitivity_calibration([110.0], 10.0, 10.0)[0] == 10.0
    with pytest.raises(ValueError, match="positive"):
        sensitivity_calibration([10.0], 0.0)


def test_spectral_unmix_recovers_channels_from_response_matrix():
    response = np.array([[1.0, 0.1, 0.2], [0.05, 1.0, 0.15], [0.01, 0.02, 1.0]])
    true = np.array([[[10.0]], [[5.0]], [[2.0]]])
    observed = (response @ true.reshape(3, -1)).reshape(true.shape)
    recovered = spectral_unmix(*observed, response)
    assert np.allclose(recovered, true)
    with pytest.raises(ValueError, match="singular"):
        spectral_unmix(*observed, np.ones((3, 3)))


def test_channel_qc_reports_missing_and_negative_cells():
    report = channel_qc([[1.0, -1.0], [np.nan, 3.0]])
    assert report["cells"] == 4
    assert report["finite_cells"] == 3
    assert report["missing_cells"] == 1
    assert report["negative_cells"] == 1
    assert report["median"] == 1.0


def test_median_mad_despike_replaces_isolated_outlier_and_preserves_nodata():
    values = np.ones((7, 7), dtype=float)
    values[3, 3] = 100.0
    values[0, 0] = np.nan
    result, spikes = median_mad_despike(values, radius=1, threshold=4.0)
    assert result[3, 3] == pytest.approx(1.0)
    assert spikes.sum() == 1
    assert np.isnan(result[0, 0])

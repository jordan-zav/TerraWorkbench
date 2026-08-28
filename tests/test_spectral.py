"""Numerical tests for dependency-free Fourier transfer helpers."""

import numpy as np

from spectral import (
    apply_transfer,
    butterworth_highpass,
    butterworth_lowpass,
    cosine_rolloff_lowpass,
    directional_cosine,
    frequency_grid,
    ideal_bandpass,
    magnetic_direction_factor,
    magnetic_field_transform,
    stabilized_downward_continuation,
)


def test_magnetic_transform_is_identity_when_target_matches_source():
    east, north, radial = frequency_grid((16, 16), 100.0, 100.0)
    response = magnetic_field_transform(
        east, north, radial, -20.0, 5.0, -20.0, 5.0, max_gain=100.0
    )
    assert response[0, 0] == 0.0
    assert np.allclose(response[radial > 0.0], 1.0)


def test_rtp_response_uses_pole_over_source_direction_factors():
    east, north, radial = frequency_grid((16, 16), 100.0, 100.0)
    response = magnetic_field_transform(
        east, north, radial, -35.0, 12.0, 90.0, 0.0, max_gain=1e6
    )
    source = magnetic_direction_factor(east, north, radial, -35.0, 12.0)
    stable = radial > 0.0
    assert np.allclose(response[stable], 1.0 / (source[stable] ** 2))


def test_low_and_high_pass_treat_constant_field_as_expected():
    values = np.full((16, 16), 7.5)
    _east, _north, radial = frequency_grid(values.shape, 100.0, 100.0)
    low = apply_transfer(values, butterworth_lowpass(radial, 1000.0, 4))
    high = apply_transfer(values, butterworth_highpass(radial, 1000.0, 4))
    assert np.allclose(low, values)
    assert np.allclose(high, 0.0)


def test_band_and_cosine_responses_are_bounded():
    _east, _north, radial = frequency_grid((32, 32), 50.0, 50.0)
    ideal = ideal_bandpass(radial, 2000.0, 300.0)
    cosine = cosine_rolloff_lowpass(radial, 2000.0, 300.0, 2)
    assert set(np.unique(ideal)).issubset({0.0, 1.0})
    assert np.all((cosine >= 0.0) & (cosine <= 1.0))
    assert cosine[0, 0] == 1.0


def test_directional_cosine_distinguishes_orthogonal_wavevectors():
    east, north, _radial = frequency_grid((16, 16), 100.0, 100.0)
    response = directional_cosine(east, north, azimuth=0.0, degree=2)
    assert response[0, 1] > 0.99
    assert response[1, 0] < 0.01


def test_downward_continuation_is_finite_and_gain_limited():
    _east, _north, radial = frequency_grid((32, 32), 25.0, 25.0)
    response = stabilized_downward_continuation(
        radial,
        height=100.0,
        lowpass_wavelength=150.0,
        order=8,
        max_gain=50.0,
    )
    assert np.isfinite(response).all()
    assert response.max() <= 50.0
    assert response[0, 0] == 1.0

"""Controlled waveforms, interpolation, moveout and spectral-ratio checks."""

import numpy as np
import pytest

from terraworkbench_core import waveform_processing as wave


def test_bandpass_frequency_selection_and_dewow_constant():
    dt = 0.001
    t = np.arange(2000) * dt
    low, high = np.sin(2 * np.pi * 20 * t), np.sin(2 * np.pi * 200 * t)
    result = wave.trace_bandpass([low + high], dt, 10.0, 40.0)["traces"][0]
    assert np.sqrt(np.mean((result[200:-200] - low[200:-200]) ** 2)) < 0.02
    output = wave.dewow(np.ones((2, 101)) * 7, dt, 21)
    np.testing.assert_allclose(output["traces"], 0.0)
    with pytest.raises(ValueError):
        wave.dewow(np.ones((1, 100)), dt, 10)


def test_background_removal_reports_coherent_signal_loss():
    t = np.arange(100)
    common = np.exp(-(((t - 40) / 5) ** 2))
    traces = np.vstack([common, common, common * 2])
    result = wave.remove_trace_background(
        traces, 0.001, reference_traces=[True, True, False]
    )
    np.testing.assert_allclose(result["traces"][:2], 0.0)
    np.testing.assert_allclose(result["traces"][2], common)
    np.testing.assert_allclose(result["energy_ratio"], [0.0, 0.0, 0.25])


def test_time_zero_support_mask_gain_and_reversibility():
    data = np.zeros((2, 100))
    data[:, 30] = 1.0
    corrected = wave.correct_time_zero(data, 1e-9, [10e-9, 20e-9])
    assert np.nanargmax(corrected["traces"][0]) == 20
    assert np.nanargmax(corrected["traces"][1]) == 10
    assert not corrected["valid"][1, -1]
    gained = wave.explicit_time_gain(
        data, 1e-9, reference_time_s=1e-9, power=2.0, max_gain=50.0
    )
    np.testing.assert_allclose(gained["traces"] / gained["gain"], data)
    assert gained["capped"].any() and gained["gain"].max() <= 50.0 + 1e-12


def test_gpr_hyperbola_recovers_velocity_apex_and_depth():
    x = np.linspace(499990, 500010, 51)
    true = np.sqrt((40e-9) ** 2 + 4 * ((x - 500001) / 1e8) ** 2)
    fit = wave.fit_diffraction_hyperbola(
        x,
        true,
        time_std_s=np.full(len(x), 0.2e-9),
        initial=[500000, 35e-9, 0.9e8],
        velocity_bounds_m_s=[0.3e8, 2e8],
    )
    assert fit["success"]
    assert fit["apex_position_m"] == pytest.approx(500001, abs=1e-5)
    assert fit["velocity_m_s"] == pytest.approx(1e8, rel=1e-5)
    assert fit["conditional_depth_m"] == pytest.approx(2.0, rel=1e-5)


def test_nmo_aligns_synthetic_reflection_and_tracks_fold():
    dt = 0.001
    t = np.arange(600) * dt
    offsets = np.array([0.0, 100.0, 200.0, 300.0])
    velocity, t0 = 2000.0, 0.2
    arrivals = np.sqrt(t0 * t0 + (offsets / velocity) ** 2)
    traces = np.exp(-(((t[None, :] - arrivals[:, None]) / 0.003) ** 2))
    result = wave.normal_moveout(traces, dt, offsets, velocity, maximum_stretch=0.5)
    assert t[np.nanargmax(result["stack"])] == pytest.approx(t0, abs=dt)
    assert result["fold"][200] == 4
    assert np.isnan(result["traces"][3, 1])
    assert result["fold"][-1] == 1


def test_hvsr_known_ratio_rotation_and_window_selection():
    rng = np.random.default_rng(5)
    base = rng.normal(size=(8, 512))
    windows = np.stack([3 * base, 3 * base, base], axis=1)
    first = wave.hvsr_windows(windows, 0.01, vertical_psd_floor=1e-12)
    np.testing.assert_allclose(first["geometric_mean"][1:], 3.0)
    angle = 0.7
    rotated = windows.copy()
    rotated[:, 0] = np.cos(angle) * windows[:, 0] - np.sin(angle) * windows[:, 1]
    rotated[:, 1] = np.sin(angle) * windows[:, 0] + np.cos(angle) * windows[:, 1]
    second = wave.hvsr_windows(rotated, 0.01, vertical_psd_floor=1e-12)
    np.testing.assert_allclose(
        second["geometric_mean"][1:], first["geometric_mean"][1:]
    )
    assert np.isnan(first["geometric_mean"][0])
    zero = wave.hvsr_windows(np.zeros((3, 3, 100)), 0.01, vertical_psd_floor=1e-12)
    assert np.isnan(zero["geometric_mean"]).all()


def test_sta_lta_candidate_arrival_and_zero_signal():
    t = np.arange(1000) * 0.001
    rng = np.random.default_rng(44)
    data = rng.normal(0, 0.001, (2, 1000))
    data[0, 200:300] += np.sin(2 * np.pi * 50 * t[:100])
    result = wave.sta_lta_picks(
        data,
        0.001,
        sta_samples=5,
        lta_samples=50,
        threshold=4.0,
        lta_energy_floor=1e-10,
        search_window_s=(0.18, 0.35),
    )
    assert result["valid"][0]
    assert 0.2 <= result["time_s"][0] <= 0.21
    zero = wave.sta_lta_picks(
        np.zeros((1, 1000)),
        0.001,
        sta_samples=5,
        lta_samples=50,
        threshold=4.0,
        lta_energy_floor=1e-10,
        search_window_s=(0.18, 0.35),
    )
    assert zero["sample_index"][0] == -1 and np.isnan(zero["time_s"][0])


def test_phase_velocity_image_known_wave_and_alias_mask():
    dt, velocity = 0.001, 300.0
    x = np.arange(20.0)
    t = np.arange(1000) * dt
    trace = np.sin(2 * np.pi * 40 * (t[None, :] - x[:, None] / velocity))
    result = wave.phase_velocity_image(
        trace,
        dt,
        x,
        np.arange(200.0, 401.0, 2),
        frequency_range_hz=[35.0, 45.0],
        minimum_amplitude=1e-6,
    )
    row = np.argmin(abs(result["frequency_hz"] - 40))
    peak = result["velocity_m_s"][np.nanargmax(result["coherence"][row])]
    assert peak == velocity
    assert result["coherence"][row].max() == pytest.approx(1.0)
    aliased = wave.phase_velocity_image(
        trace,
        dt,
        x,
        [10.0, 20.0, 300.0],
        frequency_range_hz=[35.0, 45.0],
        minimum_amplitude=1e-6,
    )
    assert np.isnan(aliased["coherence"][:, :2]).all()

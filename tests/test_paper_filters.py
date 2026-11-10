import json
import numpy as np
import pandas as pd
import pytest
from terraworkbench_core.channel_filters import notch_segment
from terraworkbench_core.grid_tools import wavelet_directional_filter
from terraworkbench_core.profile_preparation import preprocess_frame
from terraworkbench_core.filter_recipes import apply_proposals


def test_notch_selective_and_constant():
    t = np.arange(4000) / 200
    signal = 7 + 3 * np.sin(2 * np.pi * t) + 20 * np.sin(2 * np.pi * 60 * t)
    result, counts = notch_segment(t, signal, frequency_hz=60, quality_factor=30)
    mid = slice(500, -500)
    assert (
        np.sqrt(np.mean((result[mid] - (7 + 3 * np.sin(2 * np.pi * t[mid]))) ** 2))
        < 0.01
    )
    constant, _ = notch_segment(
        t, np.full(len(t), 7.0), frequency_hz=60, quality_factor=30
    )
    np.testing.assert_allclose(constant, 7, atol=1e-10)
    assert counts["short_segments"] == 0


def test_notch_rejects_invalid_sampling_and_nyquist():
    for axis, f in [
        (np.array([0.0, 0.005, 0.017, 0.02] * 8), 60),
        (np.arange(100) / 200, 100),
    ]:
        with pytest.raises(ValueError):
            notch_segment(axis, np.ones(len(axis)), frequency_hz=f, quality_factor=30)
    out, counts = notch_segment(
        np.arange(8) / 200, np.ones(8), frequency_hz=60, quality_factor=30
    )
    assert np.isnan(out).all() and counts["short_segments"] == 1


def test_notch_profile_gaps_and_audit():
    t = np.arange(2000) / 200
    data = pd.DataFrame(
        dict(
            x=np.arange(len(t)) * 0.01,
            y=np.zeros(len(t)),
            v=np.sin(2 * np.pi * t) + 5 * np.sin(2 * np.pi * 60 * t),
            t=t,
            line=np.ones(len(t)),
            sensor=np.ones(len(t)),
        )
    )
    data.loc[900:910, "v"] = np.nan
    original = data.copy(deep=True)
    result, report = preprocess_frame(
        data,
        dict(notch_hz=60, notch_q=30, time_unit="s"),
        x_column="x",
        y_column="y",
        value_column="v",
        track_column="line",
        sensor_column="sensor",
        time_column="t",
        crs="EPSG:32617",
    )
    pd.testing.assert_frame_equal(data, original)
    assert result.loc[900:910, "v"].isna().all()
    assert len(result) == len(data) and np.isfinite(result.loc[850:899, "v"]).all()
    assert report["steps"][-1]["operation"] == "zero-phase temporal notch"
    assert report["steps"][-1]["frequency_hz"] == 60


def test_wavelet_orientation_and_controlled_noise():
    rows, cols = np.indices((128, 128))
    noise = np.sin(2 * np.pi * cols / 4)
    ns, _ = wavelet_directional_filter(
        noise,
        0.25,
        stripe_direction="NS",
        wavelet="haar",
        decomposition_level=2,
        first_level=1,
        last_level=2,
        strength=1,
        padding_cells=0,
    )
    ew, _ = wavelet_directional_filter(
        noise,
        0.25,
        stripe_direction="EW",
        wavelet="haar",
        decomposition_level=2,
        first_level=1,
        last_level=2,
        strength=1,
        padding_cells=0,
    )
    assert np.sqrt(np.mean(ns**2)) < 1e-12
    np.testing.assert_allclose(ew, noise, atol=1e-12)
    clean = 50 * np.exp(-((rows - 60) ** 2 + (cols - 70) ** 2) / 20)
    a, _ = wavelet_directional_filter(clean, 0.25, stripe_direction="NS", strength=0.25)
    b, _ = wavelet_directional_filter(
        clean + noise, 0.25, stripe_direction="NS", strength=0.25
    )
    assert np.sqrt(np.mean((b - a) ** 2)) < np.sqrt(np.mean(noise**2))


def test_wavelet_mask_dc_identity_invalid_levels():
    data = np.full((129, 131), 12.0)
    data[:10, :20] = np.nan
    result, meta = wavelet_directional_filter(data, 0.25, strength=0.25)
    np.testing.assert_array_equal(np.isfinite(result), np.isfinite(data))
    np.testing.assert_allclose(result[np.isfinite(data)], 12, atol=1e-10)
    rng = np.random.default_rng(10)
    data = rng.normal(size=(129, 131))
    data[:5] = np.nan
    same, _ = wavelet_directional_filter(data, 0.25, strength=0)
    np.testing.assert_array_equal(same, data)
    assert len(meta["references"]) == 2
    for settings in [
        dict(stripe_direction="NE"),
        dict(decomposition_level=9),
        dict(first_level=True),
        dict(strength=2),
    ]:
        with pytest.raises(ValueError):
            wavelet_directional_filter(data, 0.25, **settings)


def test_recipe_wavelet_provenance_and_support():
    grid = np.zeros((128, 128))
    grid[40:70, 40:70] = 10
    grid[:5, :10] = np.nan
    step = dict(
        filter="WAVELET",
        stripe_direction="NS",
        wavelet="db4",
        decomposition_level=3,
        first_level=1,
        last_level=3,
        strength=0.25,
    )
    products, metadata = apply_proposals(
        grid,
        0.25,
        [dict(name="DWT test", base="raw", enabled=True, steps=[step])],
        padding=16,
    )
    assert products
    for output in products.values():
        np.testing.assert_array_equal(np.isfinite(output), np.isfinite(grid))
    assert "10.1002/arp.1936" in json.dumps(metadata)


def test_parameter_preflight_does_not_reject_unknown_grid_extent():
    step = dict(
        filter="WAVELET",
        stripe_direction="NS",
        wavelet="db4",
        decomposition_level=3,
        first_level=1,
        last_level=3,
        strength=0.25,
    )
    proposal = [dict(name="Review", base="raw", steps=[step])]
    products, meta = apply_proposals(
        np.zeros((2, 2)), 0.25, proposal, validate_only=True
    )
    assert not products and not meta["grid_shape_checked"]
    with pytest.raises(ValueError):
        apply_proposals(np.zeros((2, 2)), 0.25, proposal)

import numpy as np
import pytest

from terraworkbench_core.structural_attributes import (
    monogenic_phase_attributes,
    local_grid_texture,
    local_orientation_entropy,
)


def stripe():
    x = np.arange(-32.0, 33.0)
    return np.broadcast_to(np.exp(-x * x / 18), (65, 65)).copy()


def test_phase_symmetry_polarity_contrast_and_axial_normal():
    values = stripe()
    options = dict(
        spacing=(1.0, 1.0),
        wavelengths_m=[6, 12, 24],
        sigma_on_f=0.55,
        noise_threshold=0.0,
    )
    result = monogenic_phase_attributes(values, polarity="positive", **options)
    scaled = monogenic_phase_attributes(3 * values, polarity="positive", **options)
    np.testing.assert_allclose(
        result["phase_symmetry"], scaled["phase_symmetry"], atol=1e-12
    )
    assert result["phase_symmetry"][32, 32] > 0.9
    negative = monogenic_phase_attributes(values, polarity="negative", **options)
    assert negative["phase_symmetry"][32, 32] < 0.01
    assert np.isnan(result["normal_azimuth_degrees_axial"][32, 32])
    assert result["normal_azimuth_degrees_axial"][32, 36] == pytest.approx(90, abs=1e-8)
    assert (
        np.nanmin(result["phase_alignment"]) >= 0
        and np.nanmax(result["phase_alignment"]) <= 1
    )


def test_phase_constant_no_fill_edges_and_budgets():
    options = dict(
        spacing=(1.0, 1.0), wavelengths_m=[6, 12], sigma_on_f=0.55, noise_threshold=0.0
    )
    result = monogenic_phase_attributes(
        np.ones((17, 19)), edge_exclusion_cells=2, **options
    )
    np.testing.assert_allclose(result["phase_symmetry"][2:-2, 2:-2], 0, atol=1e-12)
    assert np.isnan(result["phase_symmetry"][:2, :]).all()
    invalid = stripe()
    invalid[0, 0] = np.nan
    with pytest.raises(ValueError):
        monogenic_phase_attributes(invalid, **options)
    with pytest.raises(ValueError):
        monogenic_phase_attributes(stripe(), max_cells=100, **options)
    with pytest.raises(RuntimeError, match="canceled"):
        monogenic_phase_attributes(stripe(), canceled=lambda: True, **options)


def test_texture_exact_histogram_and_missing_support():
    values = np.ones((7, 7))
    values[2:5, 2:5] = [[0, 1, 0], [1, 0, 1], [0, 1, 0]]
    result = local_grid_texture(values, 3, (0.0, 1.0), bins=2)
    p = 4 / 9
    assert result["entropy_bits"][3, 3] == pytest.approx(
        -p * np.log2(p) - (1 - p) * np.log2(1 - p)
    )
    assert result["standard_deviation"][3, 3] == pytest.approx(np.sqrt(p * (1 - p)))
    assert np.isnan(result["entropy_bits"][0, 0])
    values[3, 3] = np.nan
    missing = local_grid_texture(values, 3, (0.0, 1.0), bins=2)
    assert np.isnan(missing["entropy_bits"][3, 3]) and missing["valid_count"][3, 3] == 8


def test_texture_rejects_implicit_clipping_and_work_overrun():
    with pytest.raises(ValueError):
        local_grid_texture(np.ones((5, 5)) * 2, 3, (0.0, 1.0))
    with pytest.raises(ValueError):
        local_grid_texture(np.ones((5, 5)), 3, (0.0, 1.0), max_bin_cells=10)


def test_orientation_entropy_axial_wrap_support_and_bin_origin():
    angles = np.full((7, 7), np.nan)
    angles[2, 2], angles[2, 3], angles[3, 2], angles[3, 3] = 179.0, 1.0, 179.0, 1.0
    result = local_orientation_entropy(
        angles, 3, bin_origin_degrees=-5, bins=18, minimum_count=3
    )
    assert result["entropy_bits"][3, 3] == pytest.approx(0, abs=1e-12)
    angles[3, 2:4] = 90
    result = local_orientation_entropy(
        angles, 3, bin_origin_degrees=-5, bins=18, minimum_count=3
    )
    assert result["entropy_bits"][3, 3] == pytest.approx(1, abs=1e-12)
    assert np.isnan(result["entropy_bits"][6, 6])
    rotated = local_orientation_entropy(
        angles + 30, 3, bin_origin_degrees=25, bins=18, minimum_count=3
    )
    np.testing.assert_allclose(
        result["entropy_bits"], rotated["entropy_bits"], equal_nan=True
    )

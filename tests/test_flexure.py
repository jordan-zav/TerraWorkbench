"""Analytic Fourier modes, plate-equation residual, Airy limit and scan safety."""

import numpy as np
import pytest

from terraworkbench_core.flexure import scan_elastic_thickness, thin_plate_flexure


PARAMETERS = dict(
    young_modulus_pa=7e10, poisson_ratio=0.25, restoring_contrast_kg_m3=500.0
)


def test_flexure_fourier_mode_sign_units_and_mean():
    n, m, dy, dx = 24, 32, 1500.0, 2000.0
    y, x = np.meshgrid(np.arange(n) * dy, np.arange(m) * dx, indexing="ij")
    kx, ky = 2 * np.pi * 3 / (m * dx), 2 * np.pi * 2 / (n * dy)
    load = 2e6 + 1e7 * np.cos(kx * x + ky * y)
    te = 15000.0
    result = thin_plate_flexure(load, [dy, dx], elastic_thickness_m=te, **PARAMETERS)
    d = 7e10 * te**3 / (12 * (1 - 0.25**2))
    foundation = 500 * 9.80665
    expected = 2e6 / foundation + 1e7 * np.cos(kx * x + ky * y) / (
        d * (kx * kx + ky * ky) ** 2 + foundation
    )
    np.testing.assert_allclose(result["displacement_down_m"], expected, atol=1e-11)
    assert result["flexural_rigidity_n_m"] == pytest.approx(d)
    assert result["displacement_down_m"].mean() == pytest.approx(
        load.mean() / foundation
    )


def test_flexure_local_airy_limit_and_equation_residual():
    rng = np.random.default_rng(4)
    load = rng.normal(size=(16, 20)) * 1e7
    airy = thin_plate_flexure(
        load, [1000.0, 1000.0], elastic_thickness_m=0.0, **PARAMETERS
    )
    np.testing.assert_allclose(
        airy["displacement_down_m"], load / (500 * 9.80665), atol=1e-11
    )
    result = thin_plate_flexure(
        load, [1000.0, 1000.0], elastic_thickness_m=10000.0, **PARAMETERS
    )
    # Reconstruct the fourth spatial derivative directly, without using transfer.
    ky = 2 * np.pi * np.fft.fftfreq(16, 1000.0)
    kx = 2 * np.pi * np.fft.fftfreq(20, 1000.0)
    w = result["displacement_down_m"]
    biharmonic = np.fft.ifft2(
        np.fft.fft2(w) * (ky[:, None] ** 2 + kx[None, :] ** 2) ** 2
    ).real
    recovered = result["flexural_rigidity_n_m"] * biharmonic + 500 * 9.80665 * w
    np.testing.assert_allclose(recovered, load, atol=0.01)


def test_thickness_scan_recovers_candidate_and_masks_only_observations():
    x, y = np.meshgrid(np.arange(32), np.arange(24))
    load = 1e7 * np.cos(2 * np.pi * x / 32) + 2e6 * np.sin(2 * np.pi * y / 24)
    prediction = thin_plate_flexure(
        load, [10000.0, 10000.0], elastic_thickness_m=15000.0, **PARAMETERS
    )
    observed = prediction["displacement_down_m"].copy()
    mask = np.ones(load.shape, bool)
    mask[:5] = False
    observed[~mask] = np.nan
    result = scan_elastic_thickness(
        load,
        observed,
        1.0,
        [10000.0, 10000.0],
        candidate_thicknesses_m=[0.0, 5000.0, 10000.0, 15000.0, 20000.0, 25000.0],
        observation_mask=mask,
        **PARAMETERS,
    )
    assert result["best_elastic_thickness_m"] == 15000.0
    assert not result["best_on_scan_boundary"]
    assert result["chi_squared"].min() < 1e-20
    assert result["number_observations"] == mask.sum()


def test_uniform_load_scan_reports_non_identifiability():
    load = np.full((8, 8), 1e6)
    observed = load / (500 * 9.80665)
    result = scan_elastic_thickness(
        load,
        observed,
        1.0,
        [1000.0, 1000.0],
        candidate_thicknesses_m=[0.0, 10000.0, 20000.0],
        **PARAMETERS,
    )
    np.testing.assert_array_equal(
        result["indistinguishable_candidate_indices"], [0, 1, 2]
    )
    assert result["best_on_scan_boundary"]


def test_flexure_missing_load_budgets_and_cancel():
    load = np.ones((8, 8))
    with pytest.raises(ValueError, match="budget"):
        thin_plate_flexure(
            load, [1.0, 1.0], elastic_thickness_m=1.0, max_cells=1, **PARAMETERS
        )
    with pytest.raises(InterruptedError):
        thin_plate_flexure(
            load, [1.0, 1.0], elastic_thickness_m=1.0, cancel=lambda: True, **PARAMETERS
        )
    with pytest.raises(ValueError, match="budget"):
        scan_elastic_thickness(
            load,
            load,
            1.0,
            [1.0, 1.0],
            candidate_thicknesses_m=[0.0, 1.0],
            max_work=1,
            **PARAMETERS,
        )
    with pytest.raises(InterruptedError):
        scan_elastic_thickness(
            load,
            load,
            1.0,
            [1.0, 1.0],
            candidate_thicknesses_m=[0.0, 1.0],
            cancel=lambda: True,
            **PARAMETERS,
        )
    load[0, 0] = np.nan
    with pytest.raises(ValueError, match="Complete"):
        thin_plate_flexure(load, [1.0, 1.0], elastic_thickness_m=0.0, **PARAMETERS)

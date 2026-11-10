"""Known Gaussian posterior and spectral conservation/independence tests."""

import numpy as np
import pytest
from terraworkbench_core.advanced_statistics import (
    linear_gaussian_ensemble,
    matched_layer_filters,
    profile_admittance_coherence,
)


def test_linear_gaussian_posterior_draws_known_mean_covariance_and_seed():
    args = dict(
        sensitivity=np.diag([1.0, 2.0]),
        observed=[2.0, 6.0],
        data_std=[1.0, 1.0],
        regularization=np.eye(2),
        reference=[0.0, 0.0],
        beta=1.0,
        sample_count=20000,
        seed=44,
    )
    result = linear_gaussian_ensemble(**args)
    np.testing.assert_allclose(result["posterior_mean"], [1.0, 2.4])
    np.testing.assert_allclose(result["posterior_covariance"], np.diag([0.5, 0.2]))
    np.testing.assert_allclose(
        np.cov(result["samples"], rowvar=False), np.diag([0.5, 0.2]), atol=0.012
    )
    np.testing.assert_array_equal(
        result["samples"], linear_gaussian_ensemble(**args)["samples"]
    )
    with pytest.raises(ValueError, match="budget"):
        linear_gaussian_ensemble(**args, max_elements=10)


def test_matched_filters_partition_and_deep_source_attenuation():
    k = np.linspace(0.0, 0.2, 30)
    result = matched_layer_filters(
        k, [10.0, 100.0], [1.0, 1.0], geometry_exponents=[0.0, 0.0], noise_psd=0.01
    )
    np.testing.assert_allclose(
        result["layer_filters"].sum(axis=0) + result["noise_remainder_filter"], 1.0
    )
    assert result["layer_filters"][1, -1] < result["layer_filters"][0, -1]
    zero = matched_layer_filters(
        k, [10.0], [0.0], geometry_exponents=[0.0], noise_psd=0.0
    )
    np.testing.assert_allclose(zero["layer_filters"], 0.0)


def test_cross_spectrum_gain_and_independent_noise_coherence():
    rng = np.random.default_rng(14)
    x = rng.normal(size=4096)
    options = dict(
        spacing_m=2.0,
        segment_samples=128,
        overlap_samples=64,
        reference_psd_floor=1e-12,
    )
    result = profile_admittance_coherence(x, 2 * x, **options)
    np.testing.assert_allclose(result["admittance"], 2.0, atol=1e-12)
    np.testing.assert_allclose(result["coherence"], 1.0, atol=1e-12)
    independent = profile_admittance_coherence(x, rng.normal(size=len(x)), **options)
    assert np.nanmean(independent["coherence"]) < 0.08


def test_catalog_marks_solver_iteration_limit_as_not_converged():
    from terraworkbench_core.magnetotellurics import layered_impedance
    from terraworkbench_core.operations import run_operation

    frequencies = np.logspace(-2, 2, 10)
    observed = layered_impedance(frequencies, [100.0], [])["impedance_ohm"]
    result = run_operation(
        "mt.fit_resistivity",
        frequency_hz=frequencies,
        impedance_ohm=observed,
        real_std_ohm=abs(observed) * 0.01,
        imag_std_ohm=abs(observed) * 0.01,
        initial_resistivity_ohm_m=[200.0],
        thicknesses_m=[],
        max_evaluations=1,
    )
    assert not result["result"]["success"]
    assert result["provenance"]["status"] == "not_converged"
    assert result["provenance"]["solver_converged"] is False

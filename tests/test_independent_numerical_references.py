"""Independent references with explicit contracts; no commercial parity claim."""

import inspect

import numpy as np
import pytest

from terraworkbench_core.basic_processing import circular_median
from terraworkbench_core.gravity_corrections import normal_gravity_grs80
from terraworkbench_core.radiometric_spectra import integrate_energy_windows
from terraworkbench_core.spectral import (
    apply_transfer,
    butterworth_highpass,
    butterworth_lowpass,
    frequency_grid,
)


def test_grs80_against_boule_over_both_hemispheres():
    boule = pytest.importorskip("boule")
    latitude = np.linspace(-90, 90, 721)
    normal = boule.GRS80.normal_gravity
    if "coordinates" in inspect.signature(normal).parameters:
        expected = normal((np.zeros_like(latitude), latitude, np.zeros_like(latitude)))
    else:
        expected = normal(latitude, 0)
    # Independently evaluated ellipsoid gravity, zero geometric height, mGal.
    np.testing.assert_allclose(
        normal_gravity_grs80(latitude),
        expected,
        rtol=0,
        atol=2e-4,
    )


@pytest.mark.parametrize("shape", [(95, 97), (96, 98)])
@pytest.mark.parametrize("order", [1, 2, 4])
@pytest.mark.parametrize("highpass", [False, True])
def test_2d_butterworth_against_skimage_unsquared_response(shape, order, highpass):
    filters = pytest.importorskip("skimage.filters")
    field = np.random.default_rng(42).normal(size=shape)
    _, _, radial = frequency_grid(shape, 2.0, 2.0)
    transfer = (butterworth_highpass if highpass else butterworth_lowpass)(
        radial, wavelength=40.0, order=order
    )
    actual = apply_transfer(field, transfer)
    expected = filters.butterworth(
        field,
        cutoff_frequency_ratio=2.0 / 40.0,
        high_pass=highpass,
        order=order,
        squared_butterworth=False,
        npad=0,
    )
    np.testing.assert_allclose(actual, expected, rtol=2e-12, atol=2e-12)


@pytest.mark.parametrize("radius", [1, 2, 4])
def test_circular_median_against_explicit_pixel_neighbourhoods(radius):
    data = np.random.default_rng(71).normal(size=(13, 17))
    data[2:4, 3:7] = np.nan
    expected = np.full_like(data, np.nan)
    for row, col in np.ndindex(data.shape):
        if np.isnan(data[row, col]):
            continue
        values = []
        for y, x in np.ndindex(data.shape):
            if (row - y) ** 2 + (col - x) ** 2 <= radius**2 and np.isfinite(data[y, x]):
                values.append(data[y, x])
        ordered = sorted(values)
        count = len(ordered)
        expected[row, col] = (ordered[(count - 1) // 2] + ordered[count // 2]) / 2
    np.testing.assert_array_equal(circular_median(data, radius), expected)


def test_overlapping_radiometry_windows_against_poisson_trials():
    # Monte Carlo reference uses independent Poisson raw bins and explicit
    # scalar overlap fractions; it does not reuse the Core weight builder.
    counts = np.array([50.0, 100.0, 75.0])
    result = integrate_energy_windows(
        counts, [0.0, 1.0, 2.0, 4.0], [[0.5, 2.0], [1.0, 3.0]]
    )
    rng = np.random.default_rng(18)
    draws = rng.poisson(counts, size=(200_000, 3))
    windows = np.column_stack(
        (0.5 * draws[:, 0] + draws[:, 1], draws[:, 1] + 0.5 * draws[:, 2])
    )
    np.testing.assert_allclose(
        result["counts"], windows.mean(axis=0), atol=0.08, rtol=0
    )
    np.testing.assert_allclose(
        result["covariance"], np.cov(windows, rowvar=False), rtol=0.012
    )


def test_euler_gravity_depth_against_geoana_point_mass():
    gravity = pytest.importorskip("geoana.gravity")
    from terraworkbench_core.source_depth import euler_window

    source = np.array([500030., 6000020., -180.])
    xx, yy = np.meshgrid(np.linspace(499850., 500200., 9),
                         np.linspace(5999850., 6000200., 9))
    xyz = np.c_[xx.ravel(), yy.ravel(), np.full(xx.size, 70.)]
    body = gravity.PointMass(mass=5e10, location=source)
    field = -1e5 * body.gravitational_field(xyz)[:, 2] + 1234.
    derivatives = -1e5 * body.gravitational_gradient(xyz)[:, 2, :]
    solution, reason = euler_window(xyz, field, derivatives, structural_index=2)
    assert reason is None
    np.testing.assert_allclose([solution[k] for k in ("x", "y", "z")], source, atol=1e-7)
    assert solution["background"] == pytest.approx(1234.)


@pytest.mark.parametrize("roughness", [1e-4, 2., 1e4])
@pytest.mark.parametrize("seed", [7, 19, 31])
def test_radon_correlated_heterogeneous_noise_against_dense_segmented_posterior(seed, roughness):
    from scipy.linalg import block_diag
    from terraworkbench_core.radiometric_radon import paired_detector_radon

    rng = np.random.default_rng(seed)
    n = 11
    alpha, beta, gamma = 1.2, .15, .9
    sd, su = rng.uniform(.4, 2., size=(2, n))
    covariance = rng.uniform(-.6, .6, n) * sd * su
    time = np.cumsum(rng.uniform(.3, 2., n))
    groups = np.r_[np.zeros(5, int), np.ones(6, int)]
    down, up = rng.normal(15., 3., n), rng.normal(5., 2., n)
    actual = paired_detector_radon(
        time, down, up, downward_std=sd, upward_std=su,
        covariance_down_up=covariance, downward_radon_response=alpha,
        upward_ground_response=beta, upward_radon_response=gamma,
        roughness=roughness, segment_ids=groups,
    )
    # Interleaved dense ground/radon variables and independent full 2x2
    # likelihood blocks, with no prior link crossing the segment boundary.
    mixing = np.array([[1., alpha], [beta, gamma]])
    design = block_diag(*([mixing] * n))
    noise = block_diag(*[np.array([[sd[i]**2, covariance[i]],
                                 [covariance[i], su[i]**2]]) for i in range(n)])
    precision = design.T @ np.linalg.solve(noise, design)
    for i in range(n-1):
        if groups[i] != groups[i+1]:
            continue
        difference = np.zeros(2*n)
        difference[2*i+1], difference[2*i+3] = -1, 1
        precision += roughness * np.outer(difference, difference) / (time[i+1]-time[i])
    posterior = np.linalg.inv(precision)
    mean = np.linalg.solve(precision, design.T @ np.linalg.solve(noise, np.c_[down, up].ravel()))
    for key, expected in (
        ("terrestrial_u_rate", mean[::2]), ("radon_proxy", mean[1::2]),
        ("terrestrial_posterior_variance", np.diag(posterior)[::2]),
        ("radon_posterior_variance", np.diag(posterior)[1::2]),
        ("local_ground_radon_posterior_covariance", posterior[np.arange(n)*2, np.arange(n)*2+1]),
    ):
        np.testing.assert_allclose(actual[key], expected, atol=2e-9, rtol=2e-9)

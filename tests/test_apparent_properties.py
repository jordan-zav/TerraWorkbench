import numpy as np
import pytest
from scipy.constants import G, mu_0

from terraworkbench_core.apparent_properties import (
    layer_property_response,
    apparent_layer_property,
)


@pytest.mark.parametrize("kind", ["density", "susceptibility"])
def test_oblique_mode_analytical_response_recovery_and_units(kind):
    rows, columns = 33, 35
    dy, dx = 20.0, 30.0
    ky, kx = 2 * np.pi * 2 / (rows * dy), 2 * np.pi / (columns * dx)
    y, x = np.meshgrid(np.arange(rows) * dy, np.arange(columns) * dx, indexing="ij")
    phase = kx * x + ky * y
    k = np.hypot(kx, ky)
    amplitude = 100.0 if kind == "density" else 0.01
    inc, dec = np.deg2rad(50.0), np.deg2rad(25.0)
    depth, thickness = 35.0, 120.0
    options = dict(kind=kind, top_depth_m=depth, thickness_m=thickness)
    if kind == "density":
        response = (
            2 * np.pi * G * 1e5 * np.exp(-k * depth) * (1 - np.exp(-k * thickness)) / k
        )
    else:
        options.update(field_nt=50000.0, inclination=50.0, declination=25.0)
        d = np.sin(inc) + 1j * np.cos(inc) * (kx * np.sin(dec) + ky * np.cos(dec)) / k
        response = 25000.0 * np.exp(-k * depth) * (1 - np.exp(-k * thickness)) * d**2
    known = amplitude * np.cos(phase)
    expected = (amplitude * response * np.exp(1j * phase)).real
    forward = layer_property_response(known, (dy, dx), **options)
    np.testing.assert_allclose(forward["predicted"], expected, atol=1e-11)
    inverse = apparent_layer_property(
        expected + 7.0,
        (dy, dx),
        background=2.0,
        regularization_response=0.0,
        max_inverse_gain=1e12,
        minimum_wavelength_m=60.0,
        **options,
    )
    np.testing.assert_allclose(inverse["contrast"], known, atol=1e-9)
    np.testing.assert_allclose(inverse["property"], known + 2.0, atol=1e-9)
    assert inverse["recipe"]["observed_mean_removed"] == pytest.approx(7.0)
    assert inverse["recipe"]["residual_rms"] < 1e-10
    damped = apparent_layer_property(
        expected,
        (dy, dx),
        background=0.0,
        regularization_response=abs(response),
        max_inverse_gain=1e12,
        minimum_wavelength_m=60.0,
        **options,
    )
    np.testing.assert_allclose(damped["contrast"], known / 2, atol=1e-9)


def test_slab_limit_susceptibility_dc_and_unobservable_modes():
    values = np.ones((9, 9))
    gravity = layer_property_response(
        values * 100.0,
        (10.0, 10.0),
        kind="density",
        top_depth_m=50.0,
        thickness_m=200.0,
    )
    np.testing.assert_allclose(
        gravity["predicted"], 2 * np.pi * G * 100.0 * 200.0 * 1e5
    )
    options = dict(
        kind="susceptibility",
        top_depth_m=20.0,
        thickness_m=100.0,
        field_nt=50000.0,
        inclination=0.0,
        declination=0.0,
    )
    assert np.allclose(
        layer_property_response(values, (10.0, 10.0), **options)["predicted"], 0.0
    )
    transverse = np.broadcast_to(np.cos(2 * np.pi * np.arange(9) / 9), (9, 9))
    assert np.allclose(
        layer_property_response(transverse, (10.0, 10.0), **options)["predicted"], 0.0
    )
    result = apparent_layer_property(
        transverse,
        (10.0, 10.0),
        background=0.1,
        regularization_response=0.0,
        max_inverse_gain=1.0,
        minimum_wavelength_m=20.0,
        **options,
    )
    assert np.allclose(result["contrast"], 0.0)
    assert not result["resolved_frequency_mask"][0, 1]


def test_caps_bandcut_nyquist_and_guards():
    wave = np.broadcast_to(np.cos(2 * np.pi * np.arange(9) / 9), (9, 9))
    options = dict(kind="density", top_depth_m=10.0, thickness_m=100.0)
    inverse = dict(
        background=0.0,
        regularization_response=0.0,
        max_inverse_gain=2.0,
        minimum_wavelength_m=2.0,
    )
    result = apparent_layer_property(wave, (1.0, 1.0), **options, **inverse)
    assert abs(result["contrast"]).max() <= 2.0 + 1e-10
    assert result["recipe"]["clipped_modes"] > 0
    cutoff = dict(inverse, minimum_wavelength_m=10.0)
    assert np.allclose(
        apparent_layer_property(wave, (1.0, 1.0), **options, **cutoff)["contrast"], 0.0
    )
    even = (-1.0) ** np.indices((8, 8))[1]
    assert np.allclose(
        layer_property_response(even, (1.0, 1.0), **options)["predicted"], 0.0
    )
    for invalid in (
        dict(top_depth_m=-1.0),
        dict(thickness_m=0.0),
        dict(field_nt=50000.0),
        dict(max_cells=10),
    ):
        with pytest.raises(ValueError):
            layer_property_response(wave, (1.0, 1.0), **dict(options, **invalid))
    for invalid in (
        dict(regularization_response=-1.0),
        dict(max_inverse_gain=0.0),
        dict(minimum_wavelength_m=1.0),
    ):
        with pytest.raises(ValueError):
            apparent_layer_property(
                wave, (1.0, 1.0), **options, **dict(inverse, **invalid)
            )
    with pytest.raises(RuntimeError, match="canceled"):
        apparent_layer_property(
            wave, (1.0, 1.0), **options, **inverse, canceled=lambda: True
        )
    with pytest.raises(ValueError):
        layer_property_response(wave + np.nan, (1.0, 1.0), **options)


@pytest.mark.parametrize("kind", ["density", "susceptibility"])
def test_continuous_layer_against_finite_harmonica_prisms(kind):
    hm = pytest.importorskip("harmonica")
    # Wide finite prism patch approximates a continuous periodic cosine layer.
    axis = np.arange(-96, 97) * 25.0
    y, x = np.meshgrid(axis, axis, indexing="ij")
    wavelength, depth, thickness = 800.0, 50.0, 300.0
    wave = np.cos(2 * np.pi * x / wavelength)
    prisms = np.column_stack(
        (
            x.ravel() - 12.5,
            x.ravel() + 12.5,
            y.ravel() - 12.5,
            y.ravel() + 12.5,
            np.full(x.size, -depth - thickness),
            np.full(x.size, -depth),
        )
    )
    ox = np.arange(-6, 7) * 25.0
    coords = (ox, np.zeros(ox.size), np.zeros(ox.size))
    k = 2 * np.pi / wavelength
    attenuation = np.exp(-k * depth) * (1 - np.exp(-k * thickness))
    if kind == "density":
        actual = hm.prism_gravity(
            coords, prisms, 100.0 * wave.ravel(), field="g_z", parallel=False
        )
        expected = 2 * np.pi * G * 1e5 * 100.0 * attenuation / k * np.cos(k * ox)
    else:
        inc, dec = np.deg2rad(50.0), np.deg2rad(25.0)
        direction = np.array(
            [np.cos(inc) * np.sin(dec), np.cos(inc) * np.cos(dec), -np.sin(inc)]
        )
        magnetization = 0.01 * 50000e-9 / mu_0 * wave.ravel()[:, None] * direction
        components = hm.prism_magnetic(
            coords, prisms, tuple(magnetization.T), field="b", parallel=False
        )
        actual = np.array(components).T @ direction
        d = np.sin(inc) + 1j * np.cos(inc) * np.sin(dec)
        expected = (0.01 * 25000.0 * attenuation * d**2 * np.exp(1j * k * ox)).real
    # Finite patch edges and piecewise-constant cells differ from continuous model.
    relative_error = np.max(abs(actual - expected)) / np.max(abs(expected))
    assert relative_error < 0.02

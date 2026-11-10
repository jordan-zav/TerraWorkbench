"""Analytic harmonic fields plus independent finite-prism sign check."""

import numpy as np
import pytest

from terraworkbench_core.magnetic_components import (
    convert_field_component,
    reconstruct_tmi_from_gradients,
)


def harmonic():
    x, y = np.meshgrid(np.arange(19.0) * 3, np.arange(17.0) * 2)
    ke, kn = 2 * np.pi / 57, 4 * np.pi / 34
    k = np.hypot(ke, kn)
    phase = ke * x + kn * y
    return phase, ke, kn, k


@pytest.mark.parametrize("source", ["up", "down", "east", "north", "total"])
def test_conversions_match_analytic_potential(source):
    phase, ke, kn, k = harmonic()
    e, n, u = 10 * ke * np.sin(phase), 10 * kn * np.sin(phase), 10 * k * np.cos(phase)
    inclination, declination = np.deg2rad([-50.0, 30.0])
    fields = dict(east=e, north=n, up=u, down=-u)
    fields["total"] = (
        np.cos(inclination) * (np.sin(declination) * e + np.cos(declination) * n)
        - np.sin(inclination) * u
    )
    for target in fields:
        result = convert_field_component(
            fields[source],
            (2.0, 3.0),
            input_component=source,
            output_component=target,
            output_mean_nt=0.0,
            inclination=-50.0,
            declination=30.0,
            max_gain=100.0,
        )
        np.testing.assert_allclose(result["field_nt"], fields[target], atol=1e-12)


def test_gradient_integration_recovers_analytic_field_and_mean():
    phase, ke, kn, k = harmonic()
    field = 23 * np.cos(phase) + 41
    gradients = dict(
        east=-23 * ke * np.sin(phase),
        north=-23 * kn * np.sin(phase),
        up=-23 * k * np.cos(phase),
    )
    result = reconstruct_tmi_from_gradients(
        (2.0, 3.0),
        reference_mean_nt=41,
        gradient_east=gradients["east"],
        gradient_north=gradients["north"],
        gradient_up=gradients["up"],
    )
    np.testing.assert_allclose(result["tmi_nt"], field, atol=1e-11)
    assert max(result["residual_rms_nt_per_m"].values()) < 1e-11
    vertical = reconstruct_tmi_from_gradients(
        (2.0, 3.0), reference_mean_nt=41, gradient_up=gradients["up"]
    )
    np.testing.assert_allclose(vertical["tmi_nt"], field, atol=1e-11)
    damped = reconstruct_tmi_from_gradients(
        (2.0, 3.0),
        reference_mean_nt=41,
        gradient_up=gradients["up"],
        damping_wavenumber=k,
    )
    np.testing.assert_allclose(damped["tmi_nt"], 41 + 11.5 * np.cos(phase), atol=1e-11)


def test_unobservable_modes_and_nyquist_are_not_presented_as_recovered():
    phase = 2 * np.pi * np.arange(17.0)[:, None] / 17
    impossible_east = np.broadcast_to(np.cos(phase), (17, 19))
    result = reconstruct_tmi_from_gradients(
        (1.0, 1.0), reference_mean_nt=12, gradient_east=impossible_east
    )
    np.testing.assert_allclose(result["tmi_nt"], 12, atol=1e-12)
    assert result["recipe"]["unobservable_modes"] > 0
    nyquist = np.broadcast_to((-1.0) ** np.arange(16), (18, 16))
    result = convert_field_component(
        nyquist,
        (1.0, 1.0),
        input_component="up",
        output_component="down",
        output_mean_nt=5,
    )
    np.testing.assert_allclose(result["field_nt"], 5, atol=1e-12)
    assert result["recipe"]["removed_nyquist_modes"] > 0


def test_component_conversion_matches_independent_prism_in_central_region():
    hm = pytest.importorskip("harmonica")
    axis = np.arange(-64, 65) * 25.0
    x, y = np.meshgrid(axis, axis)
    be, _bn, bu = hm.prism_magnetic(
        (x, y, np.zeros_like(x)),
        [-50, 50, -50, 50, -350, -250],
        ([0.0], [0.0], [-1.0]),
        field="b",
    )
    result = convert_field_component(
        bu,
        (25.0, 25.0),
        input_component="up",
        output_component="east",
        output_mean_nt=0.0,
    )["field_nt"]
    central = np.s_[48:81, 48:81]
    assert np.max(abs(result[central] - be[central])) / np.max(abs(be[central])) < 0.01


def test_input_guards_cancellation_and_gain_cap():
    values = np.ones((9, 9))
    with pytest.raises(ValueError):
        convert_field_component(
            values,
            (1, 1),
            input_component="total",
            output_component="up",
            output_mean_nt=0,
        )
    with pytest.raises(ValueError):
        reconstruct_tmi_from_gradients((1, 1), reference_mean_nt=0)
    with pytest.raises(ValueError):
        reconstruct_tmi_from_gradients(
            (1, 1), reference_mean_nt=0, gradient_up=values, weights={"east": 1}
        )
    with pytest.raises(RuntimeError, match="canceled"):
        convert_field_component(
            values,
            (1, 1),
            input_component="up",
            output_component="down",
            output_mean_nt=0,
            canceled=lambda: True,
        )
    with pytest.raises(ValueError):
        convert_field_component(
            values,
            (1, 1),
            input_component="up",
            output_component="down",
            output_mean_nt=0,
            max_cells=3,
        )
    low_inclination = np.broadcast_to(np.cos(2 * np.pi * np.arange(9) / 9), (9, 9))
    clipped = convert_field_component(
        low_inclination,
        (1, 1),
        input_component="total",
        output_component="up",
        output_mean_nt=0,
        inclination=0.001,
        declination=0,
        max_gain=2,
    )
    assert np.max(abs(clipped["field_nt"])) <= 2 + 1e-10
    assert clipped["recipe"]["clipped_modes"] > 0
    values[0, 0] = np.nan
    with pytest.raises(ValueError):
        reconstruct_tmi_from_gradients((1, 1), reference_mean_nt=0, gradient_up=values)

"""Known-body properties recovered from independent 3D volume integration."""

import numpy as np
import pytest
from scipy.constants import mu_0
from numpy.polynomial.legendre import leggauss

pytest.importorskip("harmonica")


def inputs():
    axis = np.linspace(-300.0, 300.0, 5)
    x, y = np.meshgrid(axis, axis)
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
    return xyz, np.array([[-100.0, 100.0, -100.0, 100.0, -300.0, -100.0]])


def independent_vector(xyz, magnetization):
    nodes, weights = leggauss(12)
    x, y, z = np.meshgrid(nodes * 100, nodes * 100, nodes * 100 - 200, indexing="ij")
    wx, wy, wz = np.meshgrid(weights * 100, weights * 100, weights * 100, indexing="ij")
    delta = xyz[:, None, :] - np.c_[x.ravel(), y.ravel(), z.ravel()][None, :, :]
    radius = np.linalg.norm(delta, axis=2)
    dot = delta @ magnetization
    return (
        mu_0
        / (4 * np.pi)
        * 1e9
        * np.sum(
            (
                3 * delta * dot[:, :, None] / radius[:, :, None] ** 5
                - magnetization / radius[:, :, None] ** 3
            )
            * (wx * wy * wz).ravel()[None, :, None],
            axis=1,
        )
    )


def test_density_and_background_recovery_from_volume_integral():
    from terraworkbench_core.prism_inversion import fit_prism_density
    from scripts.validate_inversion_campaign import volume_reference, direction

    xyz, prisms = inputs()
    observed = volume_reference(xyz, direction(60.0, 25.0))[0]
    result = fit_prism_density(
        xyz, prisms, observed + 0.12, np.full(len(xyz), 0.002), fit_offset=True
    )
    np.testing.assert_allclose(result["density_kg_m3"], [400.0], rtol=1e-6)
    assert result["offset_mgal"] == pytest.approx(0.12, abs=1e-7)
    down = fit_prism_density(
        xyz, prisms, -observed, np.full(len(xyz), 0.002), gravity_component="down"
    )
    np.testing.assert_allclose(down["density_kg_m3"], [400.0], rtol=1e-6)


@pytest.mark.parametrize("component", ["vector", "total"])
def test_magnetization_physical_units_covariance_and_offsets(component):
    from terraworkbench_core.prism_inversion import fit_prism_magnetization
    from scripts.validate_inversion_campaign import direction

    xyz, prisms = inputs()
    truth = np.array([0.3, -0.7, 0.5])
    vector = independent_vector(xyz, truth)
    offset = np.array([2.0, -3.0, 4.0]) if component == "vector" else 1.7
    observed = vector if component == "vector" else vector @ direction(60.0, 25.0)
    result = fit_prism_magnetization(
        xyz,
        prisms,
        observed + offset,
        np.full(observed.shape, 0.3),
        component=component,
        inclination=60.0,
        declination=25.0,
        fit_offset=True,
    )
    np.testing.assert_allclose(
        result["magnetization_a_m"], truth[None, :], rtol=1e-6, atol=1e-7
    )
    np.testing.assert_allclose(result["offset_nt"], offset, atol=1e-6)
    assert np.linalg.eigvalsh(result["parameter_covariance"]).min() > 0
    assert result["diagnostics"]["degrees_of_freedom"] == observed.size - (
        6 if component == "vector" else 4
    )


def test_rank_geometry_budget_and_cancellation_rejected():
    from terraworkbench_core.prism_inversion import (
        fit_prism_density,
        fit_prism_magnetization,
    )

    xyz, prisms = inputs()
    with pytest.raises(ValueError, match="rank deficient"):
        fit_prism_density(
            xyz, np.vstack([prisms, prisms]), np.ones(len(xyz)), np.ones(len(xyz))
        )
    with pytest.raises(ValueError, match="outside"):
        fit_prism_density([[0.0, 0.0, -200.0]], prisms, [1.0], [1.0])
    with pytest.raises(ValueError, match="interaction budget"):
        fit_prism_density(
            xyz, prisms, np.ones(len(xyz)), np.ones(len(xyz)), max_interactions=1
        )
    with pytest.raises(InterruptedError):
        fit_prism_density(
            xyz, prisms, np.ones(len(xyz)), np.ones(len(xyz)), canceled=lambda: True
        )
    with pytest.raises(ValueError, match="inclination"):
        fit_prism_magnetization(xyz, prisms, np.ones(len(xyz)), np.ones(len(xyz)))

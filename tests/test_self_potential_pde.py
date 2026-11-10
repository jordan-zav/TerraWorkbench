"""SP PDE units, analytic nonuniform resistor, convergence and source fit."""

import numpy as np
import pytest

from terraworkbench_core.self_potential_pde import fit_sp_pde_sources, sp_pde_forward


def test_sp_pde_neumann_continuum_refinement_and_sign():
    pytest.importorskip("simpeg")
    from discretize import TensorMesh

    errors = []
    for n in (8, 16):
        widths = [np.full(n, 16.0 / n), [1.0, 1.0], [1.0, 1.0]]
        mesh = TensorMesh(widths, x0=[0.0, 0.0, 0.0])
        xyz = mesh.cell_centers
        target = np.cos(np.pi * xyz[:, 0] / 16.0)
        q = 0.1 * (np.pi / 16.0) ** 2 * target
        result = sp_pde_forward(
            widths, [0.0, 0.0, 0.0], np.full(mesh.n_cells, 0.1), q, xyz, xyz[0]
        )
        expected = target - target[0]
        errors.append(np.max(abs(result["potential_difference_v"] - expected)))
        assert result["potential_difference_v"][-1] < 0
        assert abs(result["net_current_a"]) < 1e-12
    assert errors[1] < errors[0] / 3.8
    assert errors[1] < 0.007


def test_sp_pde_heterogeneous_nonuniform_resistor_units():
    pytest.importorskip("simpeg")
    from discretize import TensorMesh

    hx = np.array([1.0, 2.0, 1.0, 3.0, 2.0, 1.0])
    widths = [hx, [1.0, 1.0], [1.0, 1.0]]
    mesh = TensorMesh(widths, x0=[0.0, 0.0, 0.0])
    sigma_x = np.array([0.1, 0.2, 0.5, 0.3, 0.1, 0.1])
    sigma = np.broadcast_to(sigma_x[:, None, None], (6, 2, 2)).ravel(order="F")
    q = np.zeros((6, 2, 2))
    q[0] = 1 / (4 * hx[0])
    q[-1] = -1 / (4 * hx[-1])
    xyz = mesh.cell_centers[:6]
    result = sp_pde_forward(
        widths, [0.0, 0.0, 0.0], sigma, q.ravel(order="F"), xyz, xyz[0]
    )
    drops = (hx[:-1] / (2 * sigma_x[:-1]) + hx[1:] / (2 * sigma_x[1:])) / 4
    expected = -np.r_[0.0, np.cumsum(drops)]
    np.testing.assert_allclose(result["potential_difference_v"], expected, atol=1e-10)
    # Reference changes do not alter physical voltage differences or sign.
    shifted = sp_pde_forward(
        widths, [0.0, 0.0, 0.0], sigma, q.ravel(order="F"), xyz, xyz[-1]
    )
    np.testing.assert_allclose(
        shifted["potential_difference_v"], expected - expected[-1], atol=1e-10
    )


def test_sp_pde_source_template_inverse_and_conditional_covariance():
    pytest.importorskip("simpeg")
    from discretize import TensorMesh

    widths = [np.ones(8), np.ones(6), np.ones(4)]
    mesh = TensorMesh(widths, x0=[0.0, 0.0, 0.0])
    xyz = mesh.cell_centers
    sigma = np.where(xyz[:, 0] < 4.0, 0.1, 0.3)
    templates = 0.01 * np.column_stack(
        [np.cos(np.pi * xyz[:, 0] / 8), np.cos(np.pi * xyz[:, 1] / 6)]
    )
    truth = np.array([1.5, -0.5])
    observed = sp_pde_forward(
        widths, [0.0, 0.0, 0.0], sigma, templates @ truth, xyz, xyz[0]
    )["potential_difference_v"]
    fit = fit_sp_pde_sources(
        widths,
        [0.0, 0.0, 0.0],
        sigma,
        templates,
        xyz,
        xyz[0],
        observed,
        np.full(len(xyz), 1e-4),
        reference_coefficients=[0.0, 0.0],
        beta=1e-6,
    )
    np.testing.assert_allclose(fit["source_coefficients"], truth, atol=1e-8)
    np.testing.assert_allclose(fit["predicted_v"], observed, atol=1e-9)
    np.testing.assert_allclose(fit["resolution"], np.eye(2), atol=1e-8)
    assert np.linalg.eigvalsh(fit["posterior_covariance"]).min() > 0
    with pytest.raises(ValueError, match="budget"):
        fit_sp_pde_sources(
            widths,
            [0.0, 0.0, 0.0],
            sigma,
            templates,
            xyz,
            xyz[0],
            observed,
            np.full(len(xyz), 1e-4),
            reference_coefficients=[0.0, 0.0],
            beta=1e-6,
            max_elements=1,
        )


def test_sp_pde_conservation_geometry_budgets_and_cancellation():
    widths = [np.ones(2)] * 3
    args = dict(
        mesh_widths=widths,
        mesh_origin=[0.0, 0.0, 0.0],
        conductivity_s_m=np.ones(8),
        source_density_a_m3=np.zeros(8),
        observation_m=[[0.5, 0.5, 0.5]],
        reference_m=[1.5, 1.5, 1.5],
    )
    with pytest.raises(ValueError, match="budget"):
        sp_pde_forward(**args, max_cells=2)
    with pytest.raises(InterruptedError):
        sp_pde_forward(**args, cancel=lambda: True)
    with pytest.raises(ValueError, match="bounds"):
        sp_pde_forward(**dict(args, observation_m=[[0.0, 0.0, 0.0]]))
    pytest.importorskip("simpeg")
    with pytest.raises(ValueError, match="conserve"):
        sp_pde_forward(**dict(args, source_density_a_m3=np.ones(8)))

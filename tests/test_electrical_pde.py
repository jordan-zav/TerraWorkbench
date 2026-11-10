"""PDE electrical units, analytic half space, recovery and resource contracts."""

import numpy as np
import pytest

from terraworkbench_core.electrical import geometric_factor
from terraworkbench_core.electrical_pde import electrical_forward, invert_electrical


def mesh2():
    hx = np.r_[
        2 * 1.5 ** np.arange(8, 0, -1), np.repeat(2.0, 40), 2 * 1.5 ** np.arange(1, 9)
    ]
    hz = np.r_[2 * 1.5 ** np.arange(8, 0, -1), np.repeat(2.0, 20)]
    xyz = np.array([[-12.0, 0, 0], [-4.0, 0, 0], [4.0, 0, 0], [12.0, 0, 0]])
    return dict(
        mesh_widths=[hx, hz],
        mesh_origin=[-hx.sum() / 2, -hz.sum()],
        electrodes=xyz,
        abmn=[[0, 3, 1, 2]],
        parameter_labels=np.zeros(len(hx) * len(hz), dtype=int),
    )


def mesh3():
    h = np.r_[
        5 * 1.7 ** np.arange(4, 0, -1), np.repeat(2.5, 16), 5 * 1.7 ** np.arange(1, 5)
    ]
    z = np.r_[5 * 1.7 ** np.arange(4, 0, -1), np.repeat(2.5, 10)]
    xyz = np.array([[-15.0, 0, 0], [-5.0, 0, 0], [5.0, 0, 0], [15.0, 0, 0]])
    return dict(
        mesh_widths=[h, h, z],
        mesh_origin=[-h.sum() / 2, -h.sum() / 2, -z.sum()],
        electrodes=xyz,
        abmn=[[0, 3, 1, 2]],
        parameter_labels=np.zeros(len(h) ** 2 * len(z), dtype=int),
        max_cells=10000,
    )


@pytest.mark.parametrize("factory,tolerance", [(mesh2, 0.04), (mesh3, 0.06)])
def test_dc_pde_halfspace_units_and_ip_normalization(factory, tolerance):
    pytest.importorskip("simpeg")
    args = factory()
    factor = geometric_factor(args["electrodes"], np.array(args["abmn"]))[0]
    dc = electrical_forward(**args, conductivity_s_m=[0.01])
    assert dc["predicted"][0] * factor == pytest.approx(100.0, rel=tolerance)
    ip = electrical_forward(**args, conductivity_s_m=[0.01], chargeability_v_v=[0.025])
    assert ip["predicted"][0] == pytest.approx(0.025, rel=0.01)
    assert ip["quantity"] == "apparent_chargeability_v_v"


def test_dc_and_static_ip_bounded_recovery():
    pytest.importorskip("simpeg")
    args = mesh2()
    dc = electrical_forward(**args, conductivity_s_m=[0.02])["predicted"]
    fitted = invert_electrical(
        **args,
        observed=dc,
        data_std=abs(dc) * 0.01,
        initial=[0.01],
        reference=[0.01],
        beta=1e-6,
        max_evaluations=12,
    )
    assert fitted["success"]
    assert fitted["model"][0] == pytest.approx(0.02, rel=0.001)
    ip = electrical_forward(**args, conductivity_s_m=[0.02], chargeability_v_v=[0.04])[
        "predicted"
    ]
    inverse_ip = invert_electrical(
        **args,
        observed=ip,
        data_std=[0.0001],
        initial=[0.01],
        reference=[0.01],
        beta=1e-6,
        kind="ip",
        conductivity_s_m=[0.02],
    )
    assert inverse_ip["success"]
    assert inverse_ip["model"][0] == pytest.approx(0.04, rel=0.001)


def test_pde_input_budgets_cancel_and_no_silent_projection():
    args = mesh2()
    with pytest.raises(ValueError, match="cell budget"):
        electrical_forward(**args, conductivity_s_m=[0.01], max_cells=5)
    with pytest.raises(ValueError, match="work budget"):
        electrical_forward(**args, conductivity_s_m=[0.01], max_work=5)
    offplane = dict(args)
    offplane["electrodes"] = args["electrodes"] + np.array([0.0, 1.0, 0.0])
    with pytest.raises(ValueError, match="y=0"):
        electrical_forward(**offplane, conductivity_s_m=[0.01])
    with pytest.raises(InterruptedError):
        electrical_forward(**args, conductivity_s_m=[0.01], cancel=lambda: True)
    pytest.importorskip("simpeg")
    with pytest.raises(ValueError, match="Jacobian"):
        invert_electrical(
            **args,
            observed=[1.0],
            data_std=[0.01],
            initial=[0.01],
            reference=[0.01],
            beta=1.0,
            max_jacobian_elements=1,
        )


def test_two_zone_anomaly_recovery_and_solver_budget():
    pytest.importorskip("simpeg")
    from discretize import TensorMesh

    args = mesh2()
    mesh = TensorMesh(args["mesh_widths"], x0=args["mesh_origin"])
    x, z = mesh.cell_centers.T
    args["parameter_labels"] = ((abs(x) < 10) & (z > -12) & (z < -2)).astype(int)
    electrodes = np.array(
        [
            [center + dx, 0.0, 0.0]
            for center in [-16.0, -8.0, 0.0, 8.0, 16.0]
            for dx in (-12.0, -4.0, 4.0, 12.0)
        ]
    )
    args["electrodes"] = electrodes
    args["abmn"] = [[4 * i, 4 * i + 3, 4 * i + 1, 4 * i + 2] for i in range(5)]
    data = electrical_forward(**args, conductivity_s_m=[0.01, 0.03])["predicted"]
    fit = invert_electrical(
        **args,
        observed=data,
        data_std=abs(data) * 0.01,
        initial=[0.012, 0.02],
        reference=[0.01, 0.01],
        beta=1e-6,
    )
    assert fit["success"]
    np.testing.assert_allclose(fit["model"], [0.01, 0.03], rtol=0.003)
    with pytest.raises(RuntimeError, match="budget"):
        invert_electrical(
            **args,
            observed=data,
            data_std=abs(data) * 0.01,
            initial=[0.012, 0.02],
            reference=[0.01, 0.01],
            beta=1e-6,
            max_forward_evaluations=1,
        )


def test_active_air_nonflat_surface_and_polarity():
    pytest.importorskip("simpeg")
    from discretize import TensorMesh

    args = mesh2()
    args["mesh_widths"] = [
        args["mesh_widths"][0],
        np.r_[args["mesh_widths"][1], np.repeat(2.0, 4)],
    ]
    mesh = TensorMesh(args["mesh_widths"], x0=args["mesh_origin"])
    x, z = mesh.cell_centers.T
    active = z < np.where(x < 0, 2.0, 0.0)
    args["active_cells"] = active
    args["parameter_labels"] = np.zeros(active.sum(), dtype=int)
    args["electrodes"][:, 2] = [2.0, 2.0, 0.0, 0.0]
    normal = electrical_forward(**args, conductivity_s_m=[0.01])["predicted"]
    args["abmn"] = [[0, 3, 2, 1]]
    reverse = electrical_forward(**args, conductivity_s_m=[0.01])["predicted"]
    np.testing.assert_allclose(reverse, -normal, rtol=1e-9)


def test_three_dimensional_dc_and_ip_inverse_parameter_recovery():
    pytest.importorskip("simpeg")
    args = mesh3()
    dc = electrical_forward(**args, conductivity_s_m=[0.015])["predicted"]
    fit = invert_electrical(
        **args,
        observed=dc,
        data_std=abs(dc) * 0.01,
        initial=[0.01],
        reference=[0.01],
        beta=1e-6,
    )
    assert fit["success"] and fit["earth_dimension"] == "3D"
    assert fit["model"][0] == pytest.approx(0.015, rel=0.001)
    ip = electrical_forward(**args, conductivity_s_m=[0.015], chargeability_v_v=[0.03])[
        "predicted"
    ]
    fit_ip = invert_electrical(
        **args,
        observed=ip,
        data_std=[0.0001],
        initial=[0.01],
        reference=[0.01],
        beta=1e-6,
        kind="ip",
        conductivity_s_m=[0.015],
    )
    assert fit_ip["success"]
    assert fit_ip["model"][0] == pytest.approx(0.03, rel=0.001)

"""A replay must propagate outer tolerances and its beta seed to real SimPEG."""

import json
import numpy as np
import pytest

pytest.importorskip("simpeg")


@pytest.mark.parametrize("custom", [False, True])
def test_recipe_controls_reach_optimizer_and_beta_initialization(
    monkeypatch, custom, tmp_path
):
    from discretize import TensorMesh
    from simpeg import directives
    from terraworkbench_core import inversion as backend

    mesh = TensorMesh([[(100.0, 3)]] * 3, origin=[-150.0, -150.0, -300.0])
    x, y = np.meshgrid([-100.0, 0.0, 100.0], [-100.0, 0.0, 100.0])
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
    optimizers, seeds = [], []
    native_optimizer = backend._jacobi_optimizer
    native_beta = directives.BetaEstimate_ByEig

    def optimizer(**kwargs):
        result = native_optimizer(**kwargs)
        optimizers.append(result)
        return result

    def beta(**kwargs):
        seeds.append(kwargs["random_seed"])
        return native_beta(**kwargs)

    monkeypatch.setattr(backend, "_jacobi_optimizer", optimizer)
    monkeypatch.setattr(directives, "BetaEstimate_ByEig", beta)
    options = (
        dict(
            optimizer_tol_f=0.1, optimizer_tol_x=0.2, optimizer_tol_g=0.3, beta_seed=17
        )
        if custom
        else {}
    )
    result = backend.run_inversion_workflow(
        "susceptibility",
        xyz,
        np.array([0.0, 1.0, 0.0, 1.0, 2.0, 1.0, 0.0, 1.0, 0.0]),
        np.ones(len(xyz)),
        output_directory=tmp_path / "run",
        mesh=mesh,
        active_cells=np.ones(mesh.nC, bool),
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        iterations=2,
        **options,
    )
    expected = dict(f=0.1, x=0.2, g=0.3) if custom else dict(f=1e-6, x=1e-8, g=1e-6)
    assert {
        axis: getattr(optimizers[0], "tol" + axis.upper()) for axis in expected
    } == expected
    assert seeds == [17 if custom else 0]
    assert result.diagnostics["optimizer_tolerances"] == expected
    assert result.diagnostics["beta_seed"] == seeds[0]
    assert np.isfinite(result.model).all()
    manifest = json.loads((tmp_path / "run/run.json").read_text())
    assert manifest["diagnostics"]["optimizer_tolerances"] == expected
    if custom:
        assert all(
            manifest["options"][name] == value for name, value in options.items()
        )


@pytest.mark.parametrize(
    "options",
    [
        dict(beta_seed=-1),
        dict(beta_seed=True),
        dict(beta_seed=1.5),
        dict(optimizer_tol_f=0.0),
        dict(optimizer_tol_x=np.nan),
        dict(optimizer_tol_g=True),
        dict(optimizer_tol_f="0.1"),
    ],
)
def test_invalid_recipe_controls_fail_before_mesh_allocation(options):
    from terraworkbench_core.inversion import run_potential_field_inversion

    with pytest.raises(ValueError):
        run_potential_field_inversion(
            "susceptibility",
            np.zeros((5, 3)),
            np.zeros(5),
            np.ones(5),
            cell_xy=100.0,
            cell_z=100.0,
            depth=300.0,
            **options,
        )

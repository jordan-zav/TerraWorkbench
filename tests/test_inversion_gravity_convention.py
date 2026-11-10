"""Physical positive-density recovery and explicit observation sign contracts."""

import json

import numpy as np
import pytest

pytest.importorskip("simpeg")


def problem():
    from scripts.validate_inversion_campaign import volume_reference, direction
    from terraworkbench_core.inversion import _mesh_from_data

    x, y = np.meshgrid(np.arange(-200.0, 201.0, 100.0), np.arange(-200.0, 201.0, 100.0))
    xyz = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, 100.0)))
    topo = np.array(
        [
            [-400.0, -400.0, 0.0],
            [-400.0, 400.0, 0.0],
            [400.0, -400.0, 0.0],
            [400.0, 400.0, 0.0],
        ]
    )
    mesh, active = _mesh_from_data(xyz, 100, 100, 300, 0, topography=topo)
    observed = volume_reference(xyz, direction(60.0, 25.0))[0]
    return (
        xyz,
        observed,
        dict(
            cell_xy=100,
            cell_z=100,
            depth=300,
            mesh=mesh,
            active_cells=active,
            iterations=30,
            lower=0.0,
            upper=1.0,
        ),
    )


def test_positive_density_from_zero_bound_and_up_down_export_consistency(tmp_path):
    from terraworkbench_core.inversion import run_inversion_workflow

    xyz, observed, options = problem()
    # This checks ULP-scale background/sign equivalence, not the default
    # loose-CG optimization trajectory in an underdetermined voxel model.
    # Tighten the solve rather than widening the model/prediction tolerances.
    options.update(cg_rtol=1e-9, cg_maxiter=200)
    sigma = np.full(len(xyz), 0.002)
    up = run_inversion_workflow(
        "gravity", xyz, observed, sigma, output_directory=tmp_path / "up", **options
    )
    down = run_inversion_workflow(
        "gravity",
        xyz,
        -observed,
        sigma,
        gravity_component="down",
        output_directory=tmp_path / "down",
        **options,
    )
    assert up.diagnostics["weighted_rms"] < 2
    assert up.diagnostics["bound_start_restarts"] >= 1
    assert up.model.max() > 0.01 and up.model.min() >= 0
    np.testing.assert_allclose(up.model, down.model, atol=1e-10, rtol=1e-9)
    np.testing.assert_allclose(up.predicted, -down.predicted, atol=1e-12)
    regional = run_inversion_workflow(
        "gravity",
        xyz,
        -observed + 0.01,
        sigma,
        gravity_component="down",
        regional_prediction=np.full(len(xyz), 0.01),
        output_directory=tmp_path / "regional",
        **options,
    )
    # Adding/removing a floating regional introduces ULP differences. The
    # ill-conditioned cell model need not be bit-identical; predictions must
    # remain far below the declared data uncertainty (1e-5 sigma here).
    np.testing.assert_allclose(regional.model, down.model, atol=1e-8, rtol=1e-5)
    assert np.sqrt(np.mean(((regional.predicted - down.predicted) / sigma) ** 2)) < 1e-5
    manifest = json.loads((tmp_path / "regional/run.json").read_text())
    assert manifest["diagnostics"]["gravity_component"] == "down"
    assert manifest["regional_removed"]
    with np.load(tmp_path / "regional/model.npz") as saved:
        np.testing.assert_allclose(saved["predicted_total"], 0.01 + regional.predicted)
    table = np.loadtxt(tmp_path / "regional/data.csv", delimiter=",", skiprows=1)
    np.testing.assert_allclose(table[:, -1], -observed - regional.predicted, atol=1e-15)


def test_cancel_after_first_iteration_never_publishes_finished_artifacts(tmp_path):
    from terraworkbench_core.inversion import run_inversion_workflow

    xyz, observed, options = problem()
    iterations = []
    folder = tmp_path / "cancelled"
    with pytest.raises(RuntimeError, match="canceled"):
        run_inversion_workflow(
            "gravity",
            xyz,
            observed,
            np.full(len(xyz), 0.002),
            output_directory=folder,
            progress_callback=iterations.append,
            cancel_callback=lambda: bool(iterations),
            **options,
        )
    assert (
        iterations
        and json.loads((folder / "run.json").read_text())["state"] == "failed"
    )
    assert not (folder / "model.npz").exists() and not (folder / "data.csv").exists()


@pytest.mark.parametrize(
    "kind,component",
    [("gravity", "guess"), ("susceptibility", "down"), ("mvi", "down")],
)
def test_invalid_component_is_not_silently_ignored(kind, component):
    from terraworkbench_core.inversion import run_potential_field_inversion

    with pytest.raises(ValueError, match="gravity_component"):
        run_potential_field_inversion(
            kind,
            np.ones((5, 3)),
            np.ones(5),
            np.ones(5),
            cell_xy=100,
            cell_z=100,
            depth=300,
            gravity_component=component,
        )

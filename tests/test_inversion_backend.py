"""Real optional-backend regressions; no QGIS and no external survey data."""
# ruff: noqa: E402
import json
import subprocess
import sys
import numpy as np
import pytest

pytest.importorskip("simpeg")
from simpeg import inverse_problem, maps, optimization
from simpeg.potential_fields import magnetics
from terraworkbench_core.inversion import (
    _mesh_from_data, run_inversion_workflow, run_potential_field_inversion,
    run_joint_cross_gradient_inversion,
)


def synthetic():
    x, y = np.meshgrid(np.arange(-200, 201, 100.), np.arange(-200, 201, 100.))
    xyz = np.column_stack([x.ravel(), y.ravel(), np.full(x.size, 100.)])
    topo = np.array([[-400, -400, 0], [400, -400, 0], [-400, 400, 0], [400, 400, 0.]])
    settings = dict(cell_xy=100, cell_z=100, depth=300, padding=1,
                    topography=topo, iterations=30, max_cells=1000)
    mesh, active = _mesh_from_data(xyz, 100, 100, 300, 1, topography=topo)
    centers = mesh.cell_centers[active]
    truth = np.where((np.abs(centers[:, 0]) < 100) &
                     (np.abs(centers[:, 1]) < 100) & (centers[:, 2] > -200), .03, .001)
    source = magnetics.sources.UniformBackgroundField(
        receiver_list=[magnetics.receivers.Point(xyz, components="tmi")],
        amplitude=50000., inclination=60., declination=0.)
    simulation = magnetics.simulation.Simulation3DIntegral(mesh,
        survey=magnetics.survey.Survey(source), active_cells=active,
        chiMap=maps.IdentityMap(nP=int(active.sum())), engine="choclo")
    observed = np.asarray(simulation.dpred(truth), dtype=float)
    return xyz, observed, settings, int(active.sum())


def forbid_factorization(*args, **kwargs):
    raise AssertionError("BFGS factorization must never run")


def test_full_sparse_inversion_exports_and_avoids_bfgs(tmp_path, monkeypatch):
    monkeypatch.setattr(inverse_problem, "get_default_solver", forbid_factorization)
    monkeypatch.setattr(optimization.BFGS, "bfgsH0", property(forbid_factorization, forbid_factorization))
    xyz, observed, settings, count = synthetic()
    output = tmp_path / "inversion"
    result = run_inversion_workflow("susceptibility", xyz, observed+7., np.full(len(xyz), .5),
        output_directory=output, regional_prediction=np.full(len(xyz), 7.),
        reference_model=np.full(count, .001), starting_model=np.full(count, .001),
        regularization_norms=[1., 1., 1., 1.], irls_iterations=3, **settings)
    assert np.isfinite(result.model).all()
    assert np.all((result.model >= 0) & (result.model <= 1))
    assert result.diagnostics["weighted_rms"] < 2
    assert result.diagnostics["irls_iterations"] >= 2
    manifest = json.loads((output / "run.json").read_text())
    assert manifest["state"] == "complete" and manifest["regional_removed"]
    assert manifest["diagnostics"]["init_bfgs"] is False
    with np.load(output / "model.npz") as saved:
        np.testing.assert_allclose(saved["predicted_total"], result.predicted+7.)
        assert saved["cell_centers"].shape == saved["cell_widths"].shape
    assert "UNSTRUCTURED_GRID" in (output / "model.vtk").read_text()
    table = np.loadtxt(output / "data.csv", delimiter=",", skiprows=1)
    np.testing.assert_allclose(table[:, -1], observed-result.predicted)
    with pytest.raises(FileExistsError):
        run_inversion_workflow("susceptibility", xyz, observed, np.ones(len(xyz)),
                              output_directory=output, **settings)


def test_failed_and_canceled_runs_are_not_published_as_complete(tmp_path):
    xyz, observed, settings, _ = synthetic()
    output = tmp_path / "canceled"
    with pytest.raises(RuntimeError, match="canceled"):
        run_inversion_workflow("susceptibility", xyz, observed, np.ones(len(xyz)),
            output_directory=output, cancel_callback=lambda: True, **settings)
    assert json.loads((output / "run.json").read_text())["state"] == "failed"
    assert not (output / "model.npz").exists()
    with pytest.raises(ValueError, match="Reference model"):
        run_potential_field_inversion("susceptibility", xyz, observed, np.ones(len(xyz)),
                                      reference_model=np.ones(2), **settings)


def test_other_engines_use_jacobi_without_factorization(monkeypatch):
    monkeypatch.setattr(inverse_problem, "get_default_solver", forbid_factorization)
    xyz, observed, settings, _ = synthetic()
    settings.update(iterations=2)
    for kind in ["gravity", "mvi"]:
        result = run_potential_field_inversion(kind, xyz, observed/100., np.ones(len(xyz)), **settings)
        assert result.history and np.isfinite(result.predicted).all()
    joint = run_joint_cross_gradient_inversion(xyz, observed/100., np.ones(len(xyz)),
        xyz, observed, np.ones(len(xyz)), coupling_weight=1e4, **settings)
    assert joint.history and np.isfinite(joint.predicted_gravity).all()
    assert joint.diagnostics["gravity_component"] == "up"
    assert joint.diagnostics["beta_seed"] == 0
    assert joint.diagnostics["iterations"] == len(joint.history)
    assert joint.diagnostics["weighted_rms_gravity"] == pytest.approx(
        np.sqrt(np.mean((observed/100.-joint.predicted_gravity)**2)))


def test_supplied_mesh_and_sensitivity_budget(tmp_path):
    xyz, observed, settings, count = synthetic()
    mesh, active = _mesh_from_data(xyz, 100, 100, 300, 1, topography=settings["topography"])
    with pytest.raises(ValueError, match="Sensitivity matrix"):
        run_potential_field_inversion("susceptibility", xyz, observed, np.ones(len(xyz)),
            mesh=mesh, active_cells=active, max_sensitivity_bytes=1, **settings)
    result = run_inversion_workflow("susceptibility", xyz, observed, np.ones(len(xyz)),
        mesh=mesh, active_cells=active, reference_model=np.full(count, .001),
        output_directory=tmp_path / "supplied_mesh", **settings)
    assert result.mesh is mesh
    np.testing.assert_array_equal(result.active, active)
    assert result.diagnostics["sensitivity_bytes"] == len(xyz) * count * 8
    with np.load(tmp_path / "supplied_mesh" / "model.npz") as saved:
        np.testing.assert_allclose(saved["input_reference_model"], .001)


def test_missing_jacobi_aborts_instead_of_bfgs_fallback():
    from terraworkbench_core.inversion import _jacobi_optimizer
    optimizer = _jacobi_optimizer(maxIter=1)
    with pytest.raises(RuntimeError, match="Jacobi"):
        optimizer.findSearchDirection()


def test_headless_command_line_runs_to_completion(tmp_path):
    xyz, observed, settings, _ = synthetic()
    topo = settings.pop("topography")
    settings["iterations"] = 2
    np.savez(tmp_path / "survey.npz", xyz=xyz, observed=observed,
             standard_deviation=np.ones(len(xyz)), topography=topo)
    (tmp_path / "recipe.json").write_text(json.dumps(settings), encoding="utf-8")
    subprocess.run([sys.executable, "-m", "terraworkbench_core.inversion",
        "--kind", "susceptibility", "--input", str(tmp_path / "survey.npz"),
        "--recipe", str(tmp_path / "recipe.json"), "--output", str(tmp_path / "cli")],
        check=True, capture_output=True, text=True)
    manifest = json.loads((tmp_path / "cli" / "run.json").read_text())
    assert manifest["state"] == "complete"
    assert manifest["diagnostics"]["target_reached"] is False


def test_legacy_plugin_calls_share_core():
    from compat.inversion_core import run_potential_field_inversion as legacy
    assert legacy is run_potential_field_inversion

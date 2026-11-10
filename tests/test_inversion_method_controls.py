"""Independent Cartesian-vector conventions and insufficient-budget reporting."""

import json

import numpy as np
import pytest

pytest.importorskip("simpeg")


def test_known_body_vector_control_uses_independent_fields(tmp_path):
    from scripts.validate_inversion_methods import Campaign, direction_control

    campaign = Campaign(tmp_path / "direction")
    direction_control(campaign)
    cases = campaign.report["cases"]
    assert len(cases) == 12
    assert all(case["rank"] == 3 for case in cases)
    assert max(case["angular_error_deg"] for case in cases) < 1.0
    assert max(case["model_error"] for case in cases) < 0.02


def test_mvi_execution_completion_is_not_data_target_completion(tmp_path):
    from scripts.validate_inversion_campaign import direction, volume_reference
    from terraworkbench_core.inversion import run_inversion_workflow

    x, y = np.meshgrid(np.arange(-300.0, 301.0, 100.0), np.arange(-300.0, 301.0, 100.0))
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
    topo = np.array(
        [
            [-500.0, -500.0, 0.0],
            [-500.0, 500.0, 0.0],
            [500.0, -500.0, 0.0],
            [500.0, 500.0, 0.0],
        ]
    )
    observed = volume_reference(xyz, direction(25.0, -35.0))[1]
    observed += 0.3 * np.random.default_rng(413).normal(size=len(observed))
    output = tmp_path / "short_mvi"
    result = run_inversion_workflow(
        "mvi",
        xyz,
        observed,
        np.full(len(xyz), 0.3),
        output_directory=output,
        cell_xy=100.0,
        cell_z=100.0,
        depth=400.0,
        padding=1,
        topography=topo,
        iterations=1,
        cg_maxiter=200,
        cg_rtol=1e-4,
        field_inclination=60.0,
        field_declination=25.0,
    )
    assert result.diagnostics["iteration_limit_reached"]
    assert not result.diagnostics["target_reached"]
    assert result.diagnostics["weighted_rms"] > 3.0
    manifest = json.loads((output / "run.json").read_text())
    assert manifest["state"] == "complete"
    assert manifest["diagnostics"]["target_reached"] is False
    with np.load(output / "model.npz") as saved:
        np.testing.assert_array_equal(saved["model"], result.model)


@pytest.mark.parametrize("regularization", ["amplitude", "vector_smooth"])
def test_mvi_accepts_explicit_vector_models_and_sparse_irls(regularization):
    from scripts.validate_inversion_campaign import direction, volume_reference
    from terraworkbench_core.inversion import (
        _mesh_from_data,
        run_potential_field_inversion,
    )

    x, y = np.meshgrid(np.arange(-300.0, 301.0, 100.0), np.arange(-300.0, 301.0, 100.0))
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
    topo = np.array(
        [
            [-500.0, -500.0, 0.0],
            [-500.0, 500.0, 0.0],
            [500.0, -500.0, 0.0],
            [500.0, 500.0, 0.0],
        ]
    )
    mesh, active = _mesh_from_data(xyz, 100.0, 100.0, 400.0, 1, topography=topo)
    observed = volume_reference(xyz, direction(25.0, -35.0))[1]
    result = run_potential_field_inversion(
        "mvi",
        xyz,
        observed,
        np.full(len(xyz), 0.3),
        cell_xy=100.0,
        cell_z=100.0,
        depth=400.0,
        mesh=mesh,
        active_cells=active,
        reference_model=np.zeros((active.sum(), 3)),
        starting_model=np.zeros(3 * active.sum()),
        regularization_norms=[1.0, 2.0, 2.0, 2.0],
        irls_iterations=2,
        iterations=30,
        cg_maxiter=100,
        mvi_regularization=regularization,
        field_inclination=60.0,
        field_declination=25.0,
    )
    assert result.diagnostics["irls_iterations"] >= 1
    assert result.diagnostics["mvi_regularization"] == regularization
    assert result.diagnostics["model_units"] == "effective susceptibility SI"
    assert 39.0 < result.diagnostics["magnetization_a_per_m_per_si"] < 40.0
    assert np.isfinite(result.model).all()


def test_mvi_rejects_scalar_reference_controls_and_wrong_vector_shapes():
    from terraworkbench_core.inversion import run_potential_field_inversion

    xyz = np.c_[np.arange(5.0) * 100.0, np.zeros(5), np.full(5, 100.0)]
    options = dict(cell_xy=100.0, cell_z=100.0, depth=200.0, max_cells=50000)
    for extra, message in (
        ({"reference_model": 0.1}, "MVI reference"),
        ({"reference_value": 0.1}, "Cartesian vector reference"),
    ):
        with pytest.raises(ValueError, match=message):
            run_potential_field_inversion(
                "mvi", xyz, np.ones(5), np.ones(5), **options, **extra
            )


@pytest.mark.parametrize("mesh_type", ["tensor", "tree"])
def test_flat_auto_surface_is_valid_for_collinear_profiles(mesh_type):
    from terraworkbench_core.inversion import _mesh_from_data

    xyz = np.c_[np.arange(5.0) * 100.0, np.zeros(5), np.full(5, 100.0)]
    mesh, active = _mesh_from_data(xyz, 100.0, 100.0, 200.0, 1, mesh_type=mesh_type)
    assert active.dtype.kind == "b" and active.any()
    assert np.all(mesh.cell_centers[active, 2] < 50.0)

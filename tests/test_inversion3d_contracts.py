"""Real 3D engines, matrix-free equivalence, physical units and artifact guards."""

import json
from types import SimpleNamespace
import numpy as np
import pytest
from scipy import sparse

pytest.importorskip("simpeg")


def domain():
    from discretize import TensorMesh

    mesh = TensorMesh([[(100.0, 3)]] * 3, origin=[-150.0, -150.0, -300.0])
    active = np.ones(mesh.nC, bool)
    x, y = np.meshgrid(np.linspace(-140.0, 140.0, 5), np.linspace(-140.0, 140.0, 5))
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 70.0)]
    return mesh, active, xyz


@pytest.mark.parametrize("kind", ["gravity", "susceptibility", "mvi"])
def test_matrix_free_matches_stored_3d_inversion(kind):
    from terraworkbench_core.inversion import run_potential_field_inversion
    from simpeg import maps
    from simpeg.potential_fields import gravity, magnetics

    mesh, active, xyz = domain()
    n = mesh.nC
    if kind == "gravity":
        survey = gravity.survey.Survey(
            gravity.sources.SourceField(
                receiver_list=[gravity.receivers.Point(xyz, components="gz")]
            )
        )
        sim = gravity.simulation.Simulation3DIntegral(
            mesh, survey=survey, rhoMap=maps.IdentityMap(nP=n), engine="choclo"
        )
        truth = np.full(n, 0.2)
    else:
        survey = magnetics.survey.Survey(
            magnetics.sources.UniformBackgroundField(
                receiver_list=[magnetics.receivers.Point(xyz, components="tmi")],
                amplitude=50000.0,
                inclination=60.0,
                declination=0.0,
            )
        )
        sim = magnetics.simulation.Simulation3DIntegral(
            mesh,
            survey=survey,
            chiMap=maps.IdentityMap(nP=n * (3 if kind == "mvi" else 1)),
            model_type="vector" if kind == "mvi" else "scalar",
            engine="choclo",
        )
        truth = np.full(n * (3 if kind == "mvi" else 1), 0.015)
    observed = sim.dpred(truth)
    std = np.full(len(xyz), max(float(abs(observed).max()) * 0.03, 1e-4))
    opts = dict(
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        iterations=3,
        cg_maxiter=80,
        cg_rtol=1e-6,
        starting_model=np.full(len(truth), 0.001),
    )
    stored = run_potential_field_inversion(kind, xyz, observed, std, **opts)
    free = run_potential_field_inversion(
        kind,
        xyz,
        observed,
        std,
        sensitivity_mode="matrix_free",
        max_sensitivity_bytes=1,
        **opts,
    )
    np.testing.assert_allclose(free.predicted, stored.predicted, rtol=5e-5, atol=1e-6)
    np.testing.assert_allclose(free.model, stored.model, rtol=1e-4, atol=1e-6)
    assert free.diagnostics["stored_sensitivity_bytes"] == 0
    assert free.diagnostics["sensitivity_bytes"] > 1


def test_single_preconditioner_is_full_l2_hessian_diagonal():
    from terraworkbench_core.inversion import _single_hessian_diagonal

    rng = np.random.default_rng(32)
    g = rng.normal(size=(8, 5))
    w = np.linspace(0.2, 2.0, 8)
    reg = rng.normal(size=(9, 5))
    problem = SimpleNamespace(
        model=np.ones(5),
        beta=7.0,
        reg=SimpleNamespace(deriv2=lambda m: sparse.csr_matrix(2 * reg.T @ reg)),
        dmisfit=SimpleNamespace(
            W=sparse.diags(w),
            simulation=SimpleNamespace(
                getJtJdiag=lambda m, W: np.sum((w[:, None] * g) ** 2, axis=0)
            ),
        ),
    )
    expected = np.diag(2 * g.T @ np.diag(w * w) @ g + 14 * reg.T @ reg)
    np.testing.assert_allclose(_single_hessian_diagonal(problem), expected)


def test_preconditioner_refresh_follows_beta_schedule(monkeypatch):
    from terraworkbench_core import inversion as engine

    original = engine._single_hessian_diagonal
    recorded = []

    def capture(problem):
        recorded.append((problem, float(problem.beta)))
        return original(problem)

    monkeypatch.setattr(engine, "_single_hessian_diagonal", capture)

    def progress(_):
        problem, beta = recorded[-1]
        assert beta == float(problem.beta), (
            "Preconditioner used beta from before cooling"
        )

    mesh, active, xyz = domain()
    engine.run_potential_field_inversion(
        "gravity",
        xyz,
        np.linspace(0.01, 0.2, len(xyz)),
        np.full(len(xyz), 0.01),
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        iterations=2,
        progress_callback=progress,
    )
    assert len(recorded) >= 2


def test_cancel_during_cg_and_restore_hessian():
    from terraworkbench_core.inversion import _jacobi_optimizer

    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls >= 2

    optimizer = _jacobi_optimizer(cancel_callback=cancel, lower=-2.0, upper=2.0)
    optimizer.xc = np.ones(3) * 0.1
    optimizer.g = np.array([1.0, 2.0, 3.0])
    optimizer.H = sparse.diags([1.0, 2.0, 4.0])
    optimizer._approxHinv = sparse.eye(3)
    original = optimizer.H
    with pytest.raises(RuntimeError, match="during CG"):
        optimizer.findSearchDirection()
    assert optimizer.H is original


def test_zero_free_gradient_releases_partial_bounds_and_handles_stationarity():
    from terraworkbench_core.inversion import _jacobi_optimizer

    optimizer = _jacobi_optimizer(lower=0.0, upper=1.0)
    optimizer._approxHinv = sparse.eye(2)
    optimizer.xc = np.array([0.0, 0.5])
    optimizer.g = np.array([-1.0, 0.0])
    np.testing.assert_allclose(optimizer.findSearchDirection(), [1.0, 0.0])
    optimizer.xc = np.array([0.5, 0.5])
    optimizer.g = np.zeros(2)
    np.testing.assert_array_equal(optimizer.findSearchDirection(), [0.0, 0.0])
    assert optimizer.cg_rel_resid == 0.0


def test_mesh_budget_fails_before_tensor_constructor(monkeypatch):
    from terraworkbench_core.inversion import _mesh_from_data
    import discretize

    def forbidden(*args, **kwargs):
        raise AssertionError("Oversized mesh was allocated")

    monkeypatch.setattr(discretize, "TensorMesh", forbidden)
    xyz = np.array([[0.0, 0.0, 20.0], [10000.0, 10000.0, 20.0]])
    with pytest.raises(ValueError, match="before construction"):
        _mesh_from_data(xyz, 1.0, 1.0, 1000.0, 0, max_mesh_cells=100)


def test_masked_and_complex_observations_are_never_silently_reinterpreted(tmp_path):
    from terraworkbench_core.inversion import (
        run_potential_field_inversion,
        run_inversion_workflow,
    )

    mesh, active, xyz = domain()
    options = dict(
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        iterations=1,
    )
    masked = np.ma.array(np.ones(len(xyz)), mask=np.arange(len(xyz)) == 0)
    with pytest.raises(ValueError, match="NoData"):
        run_potential_field_inversion(
            "gravity", xyz, masked, np.ones(len(xyz)), **options
        )
    with pytest.raises(ValueError, match="Complex"):
        run_potential_field_inversion(
            "gravity",
            xyz,
            np.ones(len(xyz), complex) * (1 + 1j),
            np.ones(len(xyz)),
            **options,
        )
    output = tmp_path / "masked"
    with pytest.raises(ValueError, match="NoData"):
        run_inversion_workflow(
            "gravity",
            xyz,
            masked,
            np.ones(len(xyz)),
            output_directory=output,
            **options,
        )
    assert json.loads((output / "run.json").read_text())["state"] == "failed"


def test_mvi_exports_effective_si_and_physical_am_units():
    from terraworkbench_core.inversion import full_model

    mesh, active, _ = domain()
    result = SimpleNamespace(
        mesh=mesh,
        active=active,
        kind="mvi",
        model=np.ones(3 * mesh.nC) * 0.01,
        diagnostics={"magnetization_a_per_m_per_si": 40.0},
    )
    outputs = full_model(result)
    np.testing.assert_allclose(outputs["effective_susceptibility_x_si"], 0.01)
    np.testing.assert_allclose(outputs["magnetization_x_a_m"], 0.4)
    np.testing.assert_array_equal(
        outputs["magnetization_x"], outputs["effective_susceptibility_x_si"]
    )


def test_density_export_names_distinguish_property_from_gravity_anomaly():
    from terraworkbench_core.inversion import full_model

    mesh, active, _ = domain()
    result = SimpleNamespace(
        mesh=mesh, active=active, kind="gravity", model=np.full(mesh.nC, 0.4)
    )
    fields = full_model(result)
    np.testing.assert_allclose(fields["density_contrast_g_cm3"], 0.4)
    np.testing.assert_allclose(fields["density_contrast_kg_m3"], 400.0)
    np.testing.assert_array_equal(fields["gravity"], fields["density_contrast_g_cm3"])


def test_joint_workflow_artifacts_provenance_and_strict_rejection(tmp_path):
    from terraworkbench_core.inversion_workflows import (
        run_joint_inversion_workflow,
        input_provenance,
    )

    mesh, active, xyz = domain()
    opts = dict(
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        iterations=1,
        coupling_weight=0.0,
        starting_density=1e-6,
        starting_susceptibility=1e-6,
        sensitivity_mode="matrix_free",
    )
    values = np.linspace(0.01, 0.2, len(xyz))
    args = (xyz, values, np.ones(len(xyz)), xyz, values * 100, np.ones(len(xyz)))
    output = tmp_path / "joint"
    result = run_joint_inversion_workflow(
        *args,
        output_directory=output,
        regional_gravity=np.full(len(xyz), 0.005),
        **opts,
    )
    manifest = json.loads((output / "run.json").read_text())
    assert manifest["state"] == "complete"
    assert manifest["numerical_status"] == "not_converged"
    assert len(manifest["input_sha256"]) == 64
    assert all((output / name).is_file() for name in manifest["artifacts"])
    with np.load(output / "model.npz") as arrays:
        np.testing.assert_allclose(
            arrays["predicted_gravity_residual"], result.predicted_gravity
        )
    with pytest.raises(FileExistsError):
        run_joint_inversion_workflow(*args, output_directory=output, **opts)
    strict = tmp_path / "strict"
    with pytest.raises(RuntimeError, match="convergence criteria"):
        run_joint_inversion_workflow(
            *args, output_directory=strict, require_convergence=True, **opts
        )
    rejected = json.loads((strict / "run.json").read_text())
    assert (
        rejected["state"] == "failed"
        and rejected["numerical_status"] == "not_converged"
    )
    assert (strict / "model.npz").exists()
    before = input_provenance(dict(data=values), opts)["input_sha256"]
    changed = input_provenance(dict(data=values + 0.001), opts)["input_sha256"]
    assert before != changed

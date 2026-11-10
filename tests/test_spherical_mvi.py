"""Mapped derivatives, periodic angles, real staged solves and exported units."""

import json
import numpy as np
import pytest

pytest.importorskip("simpeg")


def domain():
    from discretize import TensorMesh
    from simpeg import maps
    from simpeg.potential_fields import magnetics

    mesh = TensorMesh([[(100.0, 3)]] * 3, origin=[-150.0, -150.0, -300.0])
    active = np.ones(mesh.nC, bool)
    x, y = np.meshgrid(np.linspace(-250.0, 250.0, 5), np.linspace(-250.0, 250.0, 5))
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
    survey = magnetics.survey.Survey(
        magnetics.sources.UniformBackgroundField(
            receiver_list=[magnetics.receivers.Point(xyz, components="tmi")],
            amplitude=50000.0,
            inclination=60.0,
            declination=25.0,
        )
    )
    sim = magnetics.simulation.Simulation3DIntegral(
        mesh,
        active_cells=active,
        survey=survey,
        chiMap=maps.IdentityMap(nP=3 * mesh.nC),
        model_type="vector",
        engine="choclo",
    )
    truth = np.zeros((mesh.nC, 3))
    truth[13] = [0.01, -0.02, 0.03]
    return mesh, active, xyz, survey, sim.dpred(truth.ravel(order="F")), truth


@pytest.mark.parametrize("mode", ["ram", "forward_only"])
def test_mapped_diagonal_includes_cross_component_energy(mode):
    from scipy.sparse import diags
    from scipy.sparse.linalg import LinearOperator
    from terraworkbench_core.spherical_mvi import (
        spherical_simulation,
        exact_spherical_map,
    )

    mesh, active, _, survey, _, _ = domain()
    sim = spherical_simulation(
        mesh, active, survey, store_sensitivities=mode, sensitivity_dtype=np.float64
    )
    rng = np.random.default_rng(891)
    n = mesh.nC
    m = np.r_[
        rng.uniform(0.001, 0.04, n),
        rng.uniform(-1.0, 1.0, n),
        rng.uniform(-3.0, 3.0, n),
    ]
    # Build the reference physical matrix with a different analytic engine.
    from simpeg.potential_fields import magnetics

    reference = magnetics.simulation.Simulation3DIntegral(
        mesh,
        active_cells=active,
        survey=survey,
        chiMap=exact_spherical_map(mesh.nC),
        model_type="vector",
        engine="geoana",
        sensitivity_dtype=np.float64,
    )
    weights = diags(np.linspace(0.5, 1.5, survey.nD))
    jac = np.asarray(reference.getJ(m))
    expected = np.sum((weights @ jac) ** 2, axis=0)
    np.testing.assert_allclose(
        sim.getJtJdiag(m, W=weights), expected, rtol=1e-10, atol=1e-10
    )
    approximate = reference.getJtJdiag(m, W=weights)
    assert np.linalg.norm(approximate - expected) / np.linalg.norm(expected) > 0.05
    np.testing.assert_allclose(
        sim.regularization_diagonal(m, weights, "component_approximation"),
        approximate,
        rtol=1e-10,
        atol=1e-10,
    )
    np.testing.assert_allclose(
        sim.regularization_diagonal(m, weights, "mapped_exact"),
        expected,
        rtol=1e-10,
        atol=1e-10,
    )
    # The same physical Gram cache must track changed angles and new errors.
    m[n:] += 0.3
    np.testing.assert_allclose(
        sim.getJtJdiag(m, W=weights),
        np.sum((weights @ reference.getJ(m)) ** 2, axis=0),
        rtol=1e-10,
        atol=1e-10,
    )
    weights = diags(np.linspace(1.0, 2.0, survey.nD))
    np.testing.assert_allclose(
        sim.getJtJdiag(m, W=weights),
        np.sum((weights @ reference.getJ(m)) ** 2, axis=0),
        rtol=1e-10,
        atol=1e-10,
    )
    if mode == "forward_only":
        assert isinstance(sim.G, LinearOperator)
        assert sim._physical_gram.shape == (3, 3, n)


def test_exact_map_zero_roundtrip_and_finite_difference_derivative():
    from terraworkbench_core.spherical_mvi import exact_spherical_map

    mapping = exact_spherical_map(4)
    m = np.r_[[0.0, 0.01, 0.03, 0.02], [0.3, -0.5, 0.9, 0.0], [2.9, -2.9, 0.1, 0.3]]
    cart = mapping * m
    np.testing.assert_array_equal(cart.reshape((4, 3), order="F")[0], 0.0)
    np.testing.assert_allclose(mapping * mapping.inverse(cart), cart, atol=1e-15)
    jac = mapping.deriv(m).toarray()
    shifted = m.copy()
    shifted[5] += 1e-7
    assert np.linalg.norm(mapping.deriv(shifted).toarray() - jac) > 1e-12
    for i in range(len(m)):
        delta = np.zeros_like(m)
        delta[i] = 1e-7
        np.testing.assert_allclose(
            ((mapping * (m + delta)) - (mapping * (m - delta))) / (2e-7),
            jac[:, i],
            rtol=1e-7,
            atol=1e-9,
        )


def test_angular_regularization_handles_the_pi_seam():
    from simpeg import utils
    from terraworkbench_core.spherical_mvi import spherical_regularizer

    mesh, active, _, _, _, _ = domain()
    n = mesh.nC
    reference = np.zeros(3 * n)
    reg, _ = spherical_regularizer(
        mesh, active, reference, [2.0] * 4, [2.0] * 3, [0.0, 1.0, 1.0, 1.0], False, None
    )
    phi = np.full(n, np.pi - 0.01)
    phi[1::2] = -np.pi + 0.01
    a = np.r_[np.ones(n), np.zeros(n), phi]
    b = a.copy()
    b[2 * n :][1::2] += 2 * np.pi
    np.testing.assert_allclose(reg(a), reg(b), rtol=1e-10)
    np.testing.assert_allclose(reg.deriv(a), reg.deriv(b), rtol=1e-10, atol=1e-10)
    rng = np.random.default_rng(8)
    step = rng.normal(size=3 * n)
    epsilon = 1e-7
    assert (reg(a + epsilon * step) - reg(a - epsilon * step)) / (
        2 * epsilon
    ) == pytest.approx(reg.deriv(a) @ step, rel=1e-5, abs=1e-6)
    cart = utils.mat_utils.spherical2cartesian(a.reshape((n, 3), order="F"))
    assert np.isfinite(cart).all()


def test_staged_ram_and_matrix_free_keep_cartesian_outputs(tmp_path):
    from terraworkbench_core.inversion import run_potential_field_inversion
    from terraworkbench_core.inversion import run_inversion_workflow

    mesh, active, xyz, _, observed, truth = domain()
    options = dict(
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        mvi_parameterization="spherical",
        mvi_cartesian_iterations=3,
        iterations=4,
        cg_maxiter=100,
        cg_rtol=1e-6,
        field_inclination=60.0,
        field_declination=25.0,
        starting_model=truth * 0.1,
        mvi_amplitude_max=0.1,
    )
    ram = run_inversion_workflow(
        "mvi",
        xyz,
        observed,
        np.full(len(xyz), 0.2),
        output_directory=tmp_path / "stored",
        **options,
    )
    free = run_potential_field_inversion(
        "mvi",
        xyz,
        observed,
        np.full(len(xyz), 0.2),
        sensitivity_mode="matrix_free",
        max_sensitivity_bytes=1,
        **options,
    )
    np.testing.assert_allclose(ram.model, free.model, rtol=5e-4, atol=1e-7)
    np.testing.assert_allclose(ram.predicted, free.predicted, rtol=5e-4, atol=1e-6)
    assert ram.model.shape == (3 * mesh.nC,)
    assert (
        np.linalg.norm(ram.model.reshape((-1, 3), order="F"), axis=1).max()
        <= 0.1 + 1e-10
    )
    assert {item["stage"] for item in ram.history} == {"cartesian", "spherical"}
    assert free.diagnostics["stored_sensitivity_bytes"] == 0
    assert ram.diagnostics["irls_iteration_budget"] == 0
    assert not ram.diagnostics["irls_limit_reached"]
    manifest = json.loads((tmp_path / "stored/run.json").read_text())
    assert manifest["state"] == "complete"
    assert "spherical_mvi.py" in manifest["core_sources_sha256"]


@pytest.mark.parametrize(
    "extra",
    [
        dict(mvi_angle_norms=[1.0, 2.0]),
        dict(mvi_amplitude_max=-1.0),
        dict(lower=-1.0),
        dict(mvi_cartesian_iterations=0),
        dict(mvi_angle_norms=[1.0] * 3),
        dict(regularization_norms=[3.0] * 4),
        dict(mvi_sensitivity_weights="unknown"),
        dict(mvi_irls_update="unknown"),
    ],
)
def test_invalid_spherical_controls_are_rejected(extra):
    from terraworkbench_core.inversion import run_potential_field_inversion

    with pytest.raises(ValueError):
        run_potential_field_inversion(
            "mvi",
            np.zeros((5, 3)),
            np.ones(5),
            np.ones(5),
            cell_xy=100.0,
            cell_z=100.0,
            depth=300.0,
            mvi_parameterization="spherical",
            **extra,
        )


def test_sparse_spherical_caps_preserve_exact_background_and_cancellation():
    from terraworkbench_core.inversion import run_potential_field_inversion

    mesh, active, xyz, _, observed, truth = domain()
    cap = np.where(np.linalg.norm(truth, axis=1) > 0, 0.1, 0.0)
    calls = []
    opts = dict(
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        mvi_parameterization="spherical",
        mvi_amplitude_max=cap,
        mvi_cartesian_iterations=3,
        regularization_norms=[0.0, 1.0, 1.0, 1.0],
        mvi_angle_norms=[1.0, 1.0, 1.0],
        irls_iterations=2,
        mvi_irls_update="lagged",
        iterations=8,
        cg_maxiter=100,
        field_inclination=60.0,
        field_declination=25.0,
        progress_callback=calls.append,
    )
    result = run_potential_field_inversion(
        "mvi", xyz, observed, np.full(len(xyz), 0.2), **opts
    )
    np.testing.assert_array_equal(
        result.model.reshape((-1, 3), order="F")[cap == 0], 0.0
    )
    assert result.diagnostics["mvi_parameterization"] == "spherical"
    assert result.diagnostics["regularization_norms"] == [0.0, 1.0, 1.0, 1.0]
    assert 0 <= result.diagnostics["irls_iterations"] <= 2
    assert result.diagnostics["irls_update_mode"] == "frozen_subproblem"
    assert all(
        e["projected_gradient_metric"] <= e["threshold"]
        for e in result.diagnostics["irls_subproblems"]
    )
    assert result.diagnostics["irls_iteration_budget"] == 2
    assert calls == sorted(calls) and len(set(calls)) == len(calls)
    with pytest.raises(RuntimeError, match="canceled"):
        run_potential_field_inversion(
            "mvi",
            xyz,
            observed,
            np.ones(len(xyz)),
            cancel_callback=lambda: True,
            **opts,
        )


@pytest.mark.parametrize("irls_budget", [0, 2])
def test_zero_data_do_not_create_epsilon_magnetization(irls_budget):
    from terraworkbench_core.inversion import run_potential_field_inversion

    mesh, active, xyz, _, _, _ = domain()
    result = run_potential_field_inversion(
        "mvi",
        xyz,
        np.zeros(len(xyz)),
        np.ones(len(xyz)),
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        mvi_parameterization="spherical",
        mvi_cartesian_iterations=1,
        irls_iterations=irls_budget,
        iterations=2,
        cg_maxiter=30,
    )
    np.testing.assert_array_equal(result.model, 0.0)
    np.testing.assert_array_equal(result.predicted, 0.0)


def test_disk_cache_is_namespaced_by_physical_inputs_and_preserves_other_files(
    tmp_path,
):
    from terraworkbench_core.inversion import run_potential_field_inversion

    mesh, active, xyz, _, observed, _ = domain()
    path = tmp_path / "cache"
    path.mkdir()
    sentinel = path / "sensitivity.npy"
    sentinel.write_text("preserve original cache")
    options = dict(
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        mvi_parameterization="spherical",
        mvi_cartesian_iterations=2,
        iterations=2,
        cg_maxiter=80,
        field_inclination=60.0,
        field_declination=25.0,
    )
    stored = run_potential_field_inversion(
        "mvi",
        xyz,
        observed,
        np.full(len(xyz), 0.2),
        sensitivity_mode="disk",
        sensitivity_path=path,
        **options,
    )
    ram = run_potential_field_inversion(
        "mvi", xyz, observed, np.full(len(xyz), 0.2), **options
    )
    np.testing.assert_allclose(stored.model, ram.model, rtol=1e-6, atol=1e-9)
    assert (
        len(list(path.iterdir())) == 2
        and sentinel.read_text() == "preserve original cache"
    )
    run_potential_field_inversion(
        "mvi",
        xyz + np.array([10.0, 0.0, 0.0]),
        observed,
        np.full(len(xyz), 0.2),
        sensitivity_mode="disk",
        sensitivity_path=path,
        **options,
    )
    assert len(list(path.iterdir())) == 3


def test_cancellation_records_failed_workflow_without_partial_model(tmp_path):
    from terraworkbench_core.inversion import run_inversion_workflow

    mesh, active, xyz, _, observed, _ = domain()
    with pytest.raises(RuntimeError, match="canceled"):
        run_inversion_workflow(
            "mvi",
            xyz,
            observed,
            np.ones(len(xyz)),
            output_directory=tmp_path / "failed",
            cell_xy=100.0,
            cell_z=100.0,
            depth=300.0,
            mesh=mesh,
            active_cells=active,
            mvi_parameterization="spherical",
            cancel_callback=lambda: True,
        )
    manifest = json.loads((tmp_path / "failed/run.json").read_text())
    assert manifest["state"] == "failed"
    assert not (tmp_path / "failed/model.npz").exists()


def test_path_and_string_cache_inputs_have_identical_provenance(tmp_path):
    from terraworkbench_core.inversion_workflows import input_provenance

    options = dict(sensitivity_path=tmp_path / "cache")
    a = input_provenance(dict(data=np.arange(5.0)), options)
    b = input_provenance(
        dict(data=np.arange(5.0)), dict(sensitivity_path=str(tmp_path / "cache"))
    )
    assert a["input_sha256"] == b["input_sha256"]


def test_exact_prior_choice_is_explicit_and_never_changes_the_default():
    from terraworkbench_core.inversion import run_potential_field_inversion

    mesh, active, xyz, _, observed, truth = domain()
    options = dict(
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        mvi_parameterization="spherical",
        mvi_cartesian_iterations=2,
        iterations=2,
        cg_maxiter=80,
        starting_model=truth * 0.1,
    )
    result = run_potential_field_inversion(
        "mvi",
        xyz,
        observed,
        np.ones(len(xyz)),
        mvi_sensitivity_weights="mapped_exact",
        **options,
    )
    assert result.diagnostics["mvi_sensitivity_weights"] == "mapped_exact"
    with pytest.raises(ValueError, match="Spherical controls"):
        run_potential_field_inversion(
            "mvi",
            xyz,
            observed,
            np.ones(len(xyz)),
            cell_xy=100.0,
            cell_z=100.0,
            depth=300.0,
            mvi_sensitivity_weights="mapped_exact",
        )


def test_componentwise_initialization_preserves_vector_reference_and_cell_weights():
    from terraworkbench_core.inversion import run_potential_field_inversion

    mesh, active, xyz, _, observed, truth = domain()
    options = dict(
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        mvi_regularization="componentwise",
        reference_model=truth * 0.2,
        reference_in_smooth=True,
        cell_weights=np.linspace(0.5, 2.0, mesh.nC),
        regularization_weights=[1.0, 0.5, 0.7, 0.9],
        iterations=3,
        cg_maxiter=100,
        cg_rtol=1e-6,
    )
    ram = run_potential_field_inversion(
        "mvi", xyz, observed, np.ones(len(xyz)), **options
    )
    streamed = run_potential_field_inversion(
        "mvi",
        xyz,
        observed,
        np.ones(len(xyz)),
        sensitivity_mode="matrix_free",
        **options,
    )
    np.testing.assert_allclose(ram.model, streamed.model, rtol=1e-5, atol=1e-9)
    assert ram.diagnostics["mvi_regularization"] == "componentwise"
    assert np.isfinite(ram.model).all()

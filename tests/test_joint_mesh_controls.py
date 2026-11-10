"""Public benchmark support must preserve supplied meshes and fail early."""

import numpy as np
import pytest
from types import SimpleNamespace

pytest.importorskip("simpeg")


def inputs():
    from discretize import TensorMesh

    mesh = TensorMesh([[(100.0, 3)]] * 3, origin=[-150.0, -150.0, -300.0])
    active = np.ones(mesh.nC, bool)
    xyz = np.array(
        [
            [-100.0, -100.0, 50.0],
            [-100.0, 100.0, 50.0],
            [100.0, -100.0, 50.0],
            [100.0, 100.0, 50.0],
            [0.0, 0.0, 50.0],
        ]
    )
    return mesh, active, xyz


def run(grid, mask, xyz, **extra):
    from terraworkbench_core.inversion import run_joint_cross_gradient_inversion

    options = dict(
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=grid,
        active_cells=mask,
        iterations=1,
        coupling_weight=0.0,
        starting_density=1e-6,
        starting_susceptibility=1e-6,
    )
    options.update(extra)
    return run_joint_cross_gradient_inversion(
        xyz,
        np.arange(5.0) * 0.01,
        np.ones(5),
        xyz,
        np.arange(5.0),
        np.ones(5),
        **options,
    )


def test_supplied_joint_mesh_start_and_precision():
    mesh, active, xyz = inputs()
    result = run(
        mesh,
        active,
        xyz,
        sensitivity_dtype="float64",
        reference_density=0.0,
        reference_susceptibility=0.001,
    )
    assert result.mesh is mesh
    np.testing.assert_array_equal(result.active, active)
    assert result.diagnostics["sensitivity_dtype"] == "float64"
    assert result.diagnostics["reference_models_explicit"] is True
    assert result.diagnostics["cross_gradient_hessian"] == "gauss_newton"
    assert result.diagnostics["sensitivity_bytes"] == 10 * mesh.nC * 8
    assert (
        np.isfinite(result.density).all() and np.isfinite(result.susceptibility).all()
    )
    assert result.history and "cg_relative_residual" in result.history[-1]
    assert len(result.history[-1]["next_paired_betas"]) == 2


@pytest.mark.parametrize(
    "extra,message",
    [
        ({"cg_maxiter": 0}, "CG needs"),
        ({"cg_rtol": np.nan}, "CG needs"),
        ({"cross_gradient_hessian": "unknown"}, "Cross-gradient Hessian"),
        ({"reference_density": [1.0, 2.0]}, "Reference density"),
        ({"max_sensitivity_bytes": 1}, "Sensitivity matrices"),
        ({"sensitivity_dtype": "int32"}, "Sensitivity dtype"),
        ({"starting_density": [1.0, 2.0]}, "Starting density"),
        ({"starting_susceptibility": -1.0}, "inside their bounds"),
        ({"active_cells": np.ones(27)}, "boolean active_cells"),
        ({"active_cells": np.zeros(27, bool)}, "no active cells"),
        ({"mesh": None}, "Active cells require"),
    ],
)
def test_invalid_joint_inputs_rejected_before_large_allocation(extra, message):
    mesh, active, xyz = inputs()
    with pytest.raises(ValueError, match=message):
        run(mesh, active, xyz, **extra)


def test_joint_preconditioner_matches_weighted_hessian_after_beta_update():
    from scipy.sparse import diags
    from simpeg import maps, regularization
    from terraworkbench_core.inversion import _joint_hessian_diagonal

    mesh, active, _ = inputs()
    wires = maps.Wires(("density", mesh.nC), ("susceptibility", mesh.nC))
    reg1 = regularization.WeightedLeastSquares(mesh, mapping=wires.density)
    reg2 = regularization.WeightedLeastSquares(mesh, mapping=wires.susceptibility)
    coupling = regularization.CrossGradient(mesh, wires, active_cells=active)
    reg = reg1 + reg2 + 1e9 * coupling
    rng = np.random.default_rng(15)
    model = rng.normal(size=2 * mesh.nC)
    jacobian = rng.normal(size=(7, model.size))
    weights = diags(np.arange(1.0, 8.0))
    sim = SimpleNamespace(getJtJdiag=lambda m, W: np.sum((W @ jacobian) ** 2, axis=0))
    misfit = SimpleNamespace(simulation=sim, W=weights)
    problem = SimpleNamespace(
        model=model,
        beta=0.7,
        reg=reg,
        dmisfit=SimpleNamespace(multipliers=[3.0], objfcts=[misfit]),
    )
    data_hessian = 6.0 * (weights @ jacobian).T @ (weights @ jacobian)
    for beta1, beta2 in ((1e-3, 1e4), (2e5, 0.2)):
        reg.multipliers[:2] = [beta1, beta2]
        expected = np.diag(data_hessian) + problem.beta * reg.deriv2(model).diagonal()
        np.testing.assert_allclose(
            _joint_hessian_diagonal(problem), expected, rtol=1e-13
        )


def test_joint_stopping_requires_inner_tolerance_targets_and_stable_model():
    from terraworkbench_core.inversion import _joint_outer_metrics

    opt = SimpleNamespace(
        x_last=np.ones(2), xc=np.ones(2), cg_rel_resid=0.2, cg_rtol=1e-4
    )
    assert not _joint_outer_metrics(opt, [10.0, 20.0], np.array([10.0, 20.0]))[
        "outer_convergence_met"
    ]
    opt.cg_rel_resid = 1e-5
    assert _joint_outer_metrics(opt, [10.0, 20.0], np.array([10.0, 20.0]))[
        "outer_convergence_met"
    ]
    assert not _joint_outer_metrics(opt, [1.0, 20.0], np.array([10.0, 20.0]))[
        "outer_convergence_met"
    ]
    opt.xc = np.ones(2) * 1.01
    assert not _joint_outer_metrics(opt, [10.0, 20.0], np.array([10.0, 20.0]))[
        "outer_convergence_met"
    ]
    opt.x_last = np.zeros(2)
    assert (
        _joint_outer_metrics(opt, [10.0, 20.0], np.array([10.0, 20.0]))[
            "relative_model_change"
        ]
        is None
    )


@pytest.mark.parametrize("dimension", [2, 3])
def test_cross_gradient_gn_matches_independent_residual_jacobian(dimension):
    from itertools import combinations
    from discretize import TensorMesh
    from simpeg import maps, regularization
    from terraworkbench_core.inversion import _cross_gradient

    mesh = TensorMesh([[70.0, 100.0, 130.0]] * dimension)
    active = np.ones(mesh.nC, bool)
    active[0] = False
    n = int(active.sum())
    wires = maps.Wires(("density", n), ("susceptibility", n))
    gn = _cross_gradient(mesh, wires, active, "gauss_newton")
    legacy = _cross_gradient(mesh, wires, active, "simpeg")
    native = regularization.CrossGradient(mesh, wires, active_cells=active)
    rng = np.random.default_rng(52)
    model = rng.normal(size=2 * n)
    G, A = gn._G.toarray(), gn._Av.tocsr()

    def independent(values):
        u, w = G @ values[:n], G @ values[n:]
        residuals, rows = [], []
        for cell in range(A.shape[0]):
            row = A.getrow(cell)
            for i, j in combinations(range(row.nnz), 2):
                a, b = row.indices[[i, j]]
                weight = np.sqrt(row.data[i] * row.data[j])
                residuals.append(weight * (u[a] * w[b] - u[b] * w[a]))
                rows.append(
                    weight * np.r_[w[b] * G[a] - w[a] * G[b], u[a] * G[b] - u[b] * G[a]]
                )
        return np.asarray(residuals), np.asarray(rows)

    residual, jacobian = independent(model)
    np.testing.assert_allclose(gn(model), residual @ residual, rtol=1e-12)
    np.testing.assert_allclose(
        gn.deriv(model), 2 * jacobian.T @ residual, atol=1e-12, rtol=1e-12
    )
    np.testing.assert_allclose(gn.deriv(model), native.deriv(model), atol=1e-12)
    expected = 2 * jacobian.T @ jacobian
    np.testing.assert_allclose(
        gn.deriv2(model).toarray(), expected, atol=1e-12, rtol=1e-12
    )
    direction = rng.normal(size=model.size)
    epsilon = 1e-6
    plus, _ = independent(model + epsilon * direction)
    minus, _ = independent(model - epsilon * direction)
    np.testing.assert_allclose(
        (plus - minus) / (2 * epsilon), jacobian @ direction, rtol=1e-7, atol=1e-10
    )
    np.testing.assert_allclose(
        gn.deriv2(model, direction), expected @ direction, atol=1e-12
    )
    assert np.linalg.eigvalsh(expected).min() >= -1e-12
    np.testing.assert_allclose(
        legacy.deriv2(model).toarray(), native.deriv2(model).toarray()
    )
    # A changed model must invalidate the cached operator, including in-place updates.
    model *= 2
    _, updated = independent(model)
    np.testing.assert_allclose(
        gn.deriv2(model).toarray(), 2 * updated.T @ updated, atol=1e-12
    )

"""Frozen IRLS subproblems checked against independent dense normal solves."""

import numpy as np
import pytest

pytest.importorskip("simpeg")


@pytest.mark.parametrize("iteration_budget", [1, 30])
def test_lagged_updates_wait_for_independent_subproblem_solutions(iteration_budget):
    from discretize import TensorMesh
    from scipy.sparse import diags
    from simpeg import simulation, regularization, maps
    from scripts.diagnose_mvi import fixed_solve
    from terraworkbench_core.spherical_mvi import lagged_irls_controller

    matrix = np.diag([1.0, 2.0, 3.0])
    observed = np.array([1.0, 2.0, 3.0])
    sigma = np.full(3, 0.1)

    class Linear(simulation.LinearSimulation):
        def getJtJdiag(self, m, W=None, f=None):
            return np.sum((self.G if W is None else W @ self.G) ** 2, axis=0)

    sim = Linear(G=matrix, model_map=maps.IdentityMap(nP=3))
    reg = regularization.Sparse(
        TensorMesh([np.ones(3)]),
        norms=[1.0, 2.0],
        alpha_s=1.0,
        alpha_x=0.0,
        reference_model=np.zeros(3),
    )
    errors = []

    def refresh(phase):
        if phase == "before":
            h = 2 * matrix.T @ (matrix / sigma[:, None] ** 2)
            h += (
                controller.invProb.beta * reg.deriv2(controller.invProb.model).toarray()
            )
            expected = np.linalg.solve(h, 2 * matrix.T @ (observed / sigma**2))
            errors.append(np.linalg.norm(controller.invProb.model - expected))
        else:
            diagonal = 2 * sim.getJtJdiag(controller.invProb.model, W=diags(1 / sigma))
            diagonal += (
                controller.invProb.beta
                * reg.deriv2(controller.invProb.model).diagonal()
            )
            controller.opt.approxHinv = diags(1 / diagonal)

    controller = lagged_irls_controller(
        refresh,
        max_epochs=30,
        max_irls_iterations=4,
        chifact_start=1.0,
        chifact_target=1.0,
        cooling_factor=2.0,
        cooling_rate=1,
        verbose=False,
    )
    solved = fixed_solve(
        sim,
        observed,
        sigma,
        reg,
        np.zeros(3),
        10.0,
        iterations=iteration_budget,
        controls=[controller],
    )
    if iteration_budget == 1:
        assert errors == []
        assert controller.stop_reason == "newton_budget"
        assert controller.metrics.irls_iteration_count == 0
        return
    assert len(errors) >= 3
    assert max(errors) < 1e-9
    assert all(
        e["projected_gradient_metric"] <= e["threshold"] for e in controller.epochs
    )
    assert controller.metrics.irls_iteration_count > 0
    assert np.isfinite(solved["model"]).all()
    for epoch in {row["epoch"] for row in controller.inner_history}:
        costs = [
            row["objective"]
            for row in controller.inner_history
            if row["epoch"] == epoch
        ]
        assert np.all(
            np.diff(costs) <= 1e-9 * np.maximum(abs(np.array(costs[:-1])), 1.0)
        )


def test_noise_only_data_nullspace_keeps_zero_sparse_model():
    from discretize import TensorMesh
    from simpeg import simulation, regularization, maps
    from scripts.diagnose_mvi import fixed_solve
    from terraworkbench_core.spherical_mvi import lagged_irls_controller

    class Linear(simulation.LinearSimulation):
        def getJtJdiag(self, m, W=None, f=None):
            return np.sum((self.G if W is None else W @ self.G) ** 2, axis=0)

    sim = Linear(
        G=np.vstack([np.eye(3), np.zeros((1, 3))]), model_map=maps.IdentityMap(nP=3)
    )
    reg = regularization.Sparse(
        TensorMesh([np.ones(3)]),
        norms=[1.0, 2.0],
        alpha_s=1.0,
        alpha_x=0.0,
        reference_model=np.zeros(3),
    )
    control = lagged_irls_controller(
        lambda phase: None, max_epochs=5, max_irls_iterations=2, verbose=False
    )
    result = fixed_solve(
        sim,
        np.array([0.0, 0.0, 0.0, 0.01]),
        np.ones(4),
        reg,
        np.zeros(3),
        1.0,
        iterations=5,
        controls=[control],
    )
    np.testing.assert_array_equal(result["model"], 0.0)
    assert np.isfinite(result["objective"])
    assert control.metrics.irls_iteration_count == 0


@pytest.mark.parametrize("mode", ["adaptive", "lagged"])
def test_zero_component_keeps_a_positive_threshold_without_inventing_signal(mode):
    from discretize import TensorMesh
    from simpeg import simulation, regularization, maps
    from scripts.diagnose_mvi import fixed_solve
    from terraworkbench_core.spherical_mvi import (
        lagged_irls_controller,
        safeguarded_irls_type,
    )

    class Linear(simulation.LinearSimulation):
        def getJtJdiag(self, m, W=None, f=None):
            return np.sum((self.G if W is None else W @ self.G) ** 2, axis=0)

    sim = Linear(G=np.eye(4), model_map=maps.IdentityMap(nP=4))
    mesh = TensorMesh([np.ones(2)])
    wires = maps.Wires(("x", 2), ("y", 2))
    x = regularization.Sparse(
        mesh,
        mapping=wires.x,
        norms=[1.0, 2.0],
        alpha_s=1.0,
        alpha_x=0.0,
        reference_model=np.zeros(4),
    )
    y = regularization.Sparse(
        mesh,
        mapping=wires.y,
        norms=[2.0, 1.0],
        alpha_s=0.0,
        alpha_x=1.0,
        reference_model=np.zeros(4),
    )
    params = dict(max_irls_iterations=2, verbose=False)
    control = (
        lagged_irls_controller(lambda phase: None, max_epochs=20, **params)
        if mode == "lagged"
        else safeguarded_irls_type()(**params)
    )
    result = fixed_solve(
        sim,
        np.array([1.0, 1.0, 0.0, 0.0]),
        np.ones(4),
        x + y,
        np.zeros(4),
        1.0,
        iterations=20,
        controls=[control],
    )
    assert np.isfinite(result["objective"])
    np.testing.assert_array_equal(result["model"][2:], 0.0)
    assert control.metrics.irls_iteration_count > 0
    assert control.threshold_fallbacks
    assert all(item["value"] > 0 for item in control.threshold_fallbacks)

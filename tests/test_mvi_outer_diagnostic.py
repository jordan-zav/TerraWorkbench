"""Check the frozen-prior harness against independent diagonal ridge solutions."""

import numpy as np
import pytest

pytest.importorskip("simpeg")


@pytest.mark.parametrize("beta", [0.5, 1.0, 2.0])
def test_frozen_beta_branch_matches_closed_form_without_prior_updates(tmp_path, beta):
    from discretize import TensorMesh
    from simpeg import maps, simulation, regularization, data, data_misfit
    from simpeg import inverse_problem
    from scipy.sparse import eye
    from scripts.benchmark_mvi_outer import frozen_branch, prior_digest
    from terraworkbench_core.spherical_mvi import (
        exact_spherical_map,
        spherical_optimizer,
    )

    class Linear(simulation.LinearSimulation):
        def getJtJdiag(self, m, W=None, f=None):
            jacobian = self.G @ self.model_map.deriv(m)
            if W is not None:
                jacobian = W @ jacobian
            return np.asarray(jacobian.power(2).sum(axis=0)).ravel()

    mesh = TensorMesh([np.ones(2)])
    mapping = exact_spherical_map(2)
    sim = Linear(G=eye(6, format="csr")[:2], model_map=mapping)
    observed = np.array([1.0, 2.0])
    misfit = data_misfit.L2DataMisfit(
        simulation=sim,
        data=data.Data(sim.survey, dobs=observed, standard_deviation=np.ones(2)),
    )
    wires = maps.Wires(("a", 2), ("t", 2), ("p", 2))
    terms = [
        regularization.Sparse(
            mesh,
            mapping=getattr(wires, name),
            reference_model=np.zeros(6),
            norms=[2, 2],
            alpha_s=1.0,
            alpha_x=0.0,
        )
        for name in ("a", "t", "p")
    ]
    reg = terms[0] + terms[1] + terms[2]
    lower = np.zeros(6)
    upper = np.r_[np.full(2, 10.0), np.zeros(4)]
    opt = spherical_optimizer(2, lower=lower, upper=upper)
    problem = inverse_problem.BaseInvProblem(
        misfit, reg, opt, init_bfgs=False, beta=beta
    )
    start = np.r_[np.full(2, 0.1), np.zeros(4)]
    # frozen_branch continues an initialized SDK inverse problem, as in the campaign.
    problem.startup(start)
    before = prior_digest(reg)
    inputs = dict(
        centers=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        volumes=np.ones(2),
        truth=np.c_[observed, np.zeros((2, 2))],
        observed=observed,
        sigma=np.ones(2),
        connectivity_edges=np.array([[0, 1]]),
    )
    result = frozen_branch(
        problem, start, beta, 10, tmp_path, inputs, mesh, np.ones(2, dtype=bool)
    )
    model = np.load(tmp_path / "model.npz")["model"]
    np.testing.assert_allclose(model[:2], observed / (1 + beta), rtol=1e-10, atol=1e-12)
    np.testing.assert_array_equal(model[2:], 0.0)
    assert result["stop_reason"] == "projected_gradient_reduction"
    assert result["all_audited_cg_met"]
    assert result["prior_sha256"] == before == prior_digest(reg)

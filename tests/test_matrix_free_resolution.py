"""Independent dense identities, large diagonal operators and solve failures."""

import numpy as np
import pytest
from scipy import sparse
from scipy.sparse.linalg import LinearOperator

from terraworkbench_core.matrix_free_resolution import (
    stochastic_linear_resolution,
    linear_point_spread,
)
from terraworkbench_core.inversion_diagnostics import linear_resolution


def problem():
    rng = np.random.default_rng(731)
    return (
        rng.normal(size=(17, 9)),
        np.linspace(0.3, 0.9, 17),
        np.diag(np.linspace(0.6, 2.0, 9)),
    )


def test_single_parameter_basis_has_exact_zero_probing_error():
    result = stochastic_linear_resolution(
        [[2.0]], [1.0], [[1.0]], beta=1.0, method="basis", probe_count=1
    )
    np.testing.assert_allclose(result["posterior_variance_estimate"], [0.2])
    np.testing.assert_allclose(result["resolution_diagonal_estimate"], [0.8])
    assert result["effective_parameters_probing_standard_error"] == 0.0


def test_basis_and_point_spread_against_dense_gaussian_identity():
    g, std, reg = problem()
    exact = linear_resolution(g, std, reg, beta=2.0)
    result = stochastic_linear_resolution(
        g, std, reg, beta=2.0, method="basis", probe_count=9, cg_rtol=1e-10
    )
    np.testing.assert_allclose(
        result["posterior_variance_estimate"],
        np.diag(exact["posterior_covariance"]),
        rtol=1e-8,
    )
    np.testing.assert_allclose(
        result["resolution_diagonal_estimate"], np.diag(exact["resolution"]), rtol=1e-8
    )
    assert result["effective_parameters_estimate"] == pytest.approx(
        exact["effective_parameters"]
    )
    spread = linear_point_spread(
        sparse.csr_matrix(g),
        std,
        sparse.csr_matrix(reg),
        [1, 4, 8],
        beta=2.0,
        cg_rtol=1e-10,
    )
    np.testing.assert_allclose(
        spread["resolution_columns"], exact["resolution"][:, [1, 4, 8]], atol=1e-8
    )
    np.testing.assert_allclose(
        spread["covariance_columns"],
        exact["posterior_covariance"][:, [1, 4, 8]],
        atol=1e-8,
    )


def test_random_probe_replay_and_empirical_mean_error():
    g, std, reg = problem()
    exact = linear_resolution(g, std, reg, beta=2.0)
    result = stochastic_linear_resolution(
        g, std, reg, beta=2.0, probe_count=128, seed=18
    )
    second = stochastic_linear_resolution(
        g, std, reg, beta=2.0, probe_count=128, seed=18
    )
    np.testing.assert_array_equal(
        result["posterior_variance_estimate"], second["posterior_variance_estimate"]
    )
    difference = abs(
        result["posterior_variance_estimate"] - np.diag(exact["posterior_covariance"])
    )
    assert np.all(difference < 5 * result["probing_standard_error_variance"])


def test_large_diagonal_operator_requires_no_model_square_allocation():
    n = 100_000
    diagonal = np.linspace(0.5, 2.0, n)
    operator = LinearOperator(
        (n, n),
        matvec=lambda v: diagonal * v,
        rmatvec=lambda v: diagonal * v,
        dtype=float,
    )
    result = stochastic_linear_resolution(
        operator,
        np.ones(n),
        sparse.eye(n),
        beta=3.0,
        probe_count=2,
        precision_diagonal=diagonal**2 + 3,
        max_elements=5_000_000,
    )
    np.testing.assert_allclose(
        result["posterior_variance_estimate"], 1 / (diagonal**2 + 3), rtol=1e-12
    )
    np.testing.assert_allclose(
        result["resolution_diagonal_estimate"],
        diagonal**2 / (diagonal**2 + 3),
        rtol=1e-12,
    )
    assert max(step["iterations"] for step in result["cg_history"]) <= 1


def test_budget_cancellation_adjoint_and_nonconvergence_are_errors():
    g, std, reg = problem()
    with pytest.raises(InterruptedError):
        stochastic_linear_resolution(g, std, reg, beta=1.0, canceled=lambda: True)
    with pytest.raises(ValueError, match="element budget"):
        stochastic_linear_resolution(g, std, reg, beta=1.0, max_elements=1)
    with pytest.raises(ValueError, match="application budget"):
        stochastic_linear_resolution(g, std, reg, beta=1.0, max_matvecs=4)
    with pytest.raises(ValueError, match="did not converge"):
        stochastic_linear_resolution(g, std, reg, beta=1.0, cg_maxiter=1, cg_rtol=1e-12)
    wrong = LinearOperator(
        g.shape, matvec=lambda v: g @ v, rmatvec=lambda v: -(g.T @ v), dtype=float
    )
    with pytest.raises(ValueError, match="adjoint"):
        stochastic_linear_resolution(wrong, std, reg, beta=1.0)
    with pytest.raises(ValueError, match="Basis mode"):
        stochastic_linear_resolution(
            g, std, reg, beta=1.0, method="basis", probe_count=3
        )
    with pytest.raises(ValueError, match="distinct"):
        linear_point_spread(g, std, reg, [2, 2], beta=1.0)

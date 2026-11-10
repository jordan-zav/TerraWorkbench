"""Exact GLS, independent numerical Jacobians and held-out Monte Carlo tests."""

import numpy as np
import pytest
from scipy.linalg import block_diag

from terraworkbench_core.complex_calibration import (
    apply_complex_response,
    fit_complex_response,
)
from terraworkbench_core.radiometric_calibration import (
    fit_radiometric_response,
    radiometric_concentrations,
)


def standards():
    c = np.array(
        [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [2.0, 1.0], [1.0, 3.0], [3.0, 2.0]]
    )
    s = np.array([[10.0, 2.0], [1.0, 5.0]])
    b = np.array([2.0, 3.0])
    args = dict(
        component_names=["K", "eU"],
        concentration_units=["%", "ppm"],
        window_names=["K_window", "U_window"],
    )
    return c, s, b, args


def test_radiometric_full_gls_coefficients_and_joint_covariance():
    c, s, b, args = standards()
    noise = np.array([[4.0, 0.6], [0.6, 1.0]])
    y = c @ s.T + b
    fit = fit_radiometric_response(c, y, noise, **args)
    np.testing.assert_allclose(fit["sensitivity"], s, atol=1e-12)
    np.testing.assert_allclose(fit["offset_rate"], b, atol=1e-12)
    design = np.zeros((len(c) * 2, 6))
    for i, row in enumerate(c):
        design[2 * i, :3] = np.r_[row, 1.0]
        design[2 * i + 1, 3:] = np.r_[row, 1.0]
    weight = np.linalg.inv(block_diag(*([noise] * len(c))))
    expected = np.linalg.inv(design.T @ weight @ design)
    np.testing.assert_allclose(fit["coefficient_covariance"], expected, atol=1e-12)
    assert abs(fit["coefficient_covariance"][0, 3]) > 0
    assert fit["degrees_of_freedom"] == 6


def test_radiometric_calibration_propagates_operator_uncertainty():
    c, s, b, args = standards()
    fit = fit_radiometric_response(c, c @ s.T + b, np.eye(2) * 0.01, **args)
    truth = np.array([[-1.0, 2.0], [1.5, 3.0]])
    noise = np.array([[0.04, 0.005], [0.005, 0.02]])
    rates = truth @ s.T + b
    result = radiometric_concentrations(rates, noise, calibration=fit, block_size=1)
    np.testing.assert_allclose(result["concentrations"], truth, atol=1e-12)
    assert result["negative"][0, 0]
    theta = np.column_stack([s, b]).ravel()
    for i in range(2):
        derivative = np.empty((2, 6))
        for j in range(6):
            plus, minus = theta.copy(), theta.copy()
            plus[j] += 1e-5
            minus[j] -= 1e-5

            def solve(t):
                a = t.reshape(2, 3)
                return np.linalg.solve(a[:, :2], rates[i] - a[:, 2])

            derivative[:, j] = (solve(plus) - solve(minus)) / 2e-5
        inverse = np.linalg.inv(s)
        expected = (
            inverse @ noise @ inverse.T
            + derivative @ fit["coefficient_covariance"] @ derivative.T
        )
        np.testing.assert_allclose(
            result["covariance"][i], expected, rtol=1e-8, atol=1e-12
        )


def test_radiometric_heldout_first_order_uncertainty_monte_carlo():
    c, s, b, args = standards()
    fit = fit_radiometric_response(c, c @ s.T + b, np.eye(2) * 1e-4, **args)
    rate = np.array([[20.0, 15.0]])
    noise = np.array([[1e-3, 2e-4], [2e-4, 2e-3]])
    result = radiometric_concentrations(rate, noise, calibration=fit)
    rng = np.random.default_rng(93)
    theta = rng.multivariate_normal(
        np.column_stack([s, b]).ravel(), fit["coefficient_covariance"], 40000
    ).reshape(-1, 2, 3)
    measured = rng.multivariate_normal(rate[0], noise, len(theta))
    draws = np.linalg.solve(theta[:, :, :2], (measured - theta[:, :, 2])[..., None])[
        ..., 0
    ]
    np.testing.assert_allclose(
        np.cov(draws, rowvar=False), result["covariance"][0], rtol=0.04, atol=2e-7
    )


def test_radiometric_bad_design_budgets_and_cancellation():
    c, s, b, args = standards()
    with pytest.raises(ValueError, match="budget"):
        fit_radiometric_response(c, c @ s.T + b, np.eye(2), **args, max_elements=1)
    with pytest.raises(ValueError, match="rank"):
        fit_radiometric_response(np.ones_like(c), c @ s.T + b, np.eye(2), **args)
    fit = fit_radiometric_response(c, c @ s.T + b, np.eye(2), **args)
    with pytest.raises(InterruptedError):
        radiometric_concentrations(
            [[1.0, 2.0]], np.eye(2), calibration=fit, cancel=lambda: True
        )
    with pytest.raises(ValueError, match="budget"):
        radiometric_concentrations(
            [[1.0, 2.0]], np.eye(2), calibration=fit, max_output_elements=1
        )
    bad = dict(fit, sensitivity=np.ones((2, 2)))
    with pytest.raises(ValueError, match="singular"):
        radiometric_concentrations([[1.0, 2.0]], np.eye(2), calibration=bad)


def test_complex_calibration_full_gls_and_covariance():
    x = np.array([1 + 2j, 3 - 1j, -2 + 0.5j, 0.0, 4 + 2j])
    gain, offset = 0.5 + 2j, 3.0 - 4j
    noise = np.array([[0.3, 0.08], [0.08, 0.1]])
    result = fit_complex_response(x, gain * x + offset, noise)
    np.testing.assert_allclose(result["gain"], gain, atol=1e-12)
    np.testing.assert_allclose(result["offset"], offset, atol=1e-12)
    design = np.zeros((2 * len(x), 4))
    for i, v in enumerate(x):
        design[2 * i : 2 * i + 2] = [[v.real, -v.imag, 1, 0], [v.imag, v.real, 0, 1]]
    precision = np.linalg.inv(block_diag(*([noise] * len(x))))
    expected = np.linalg.inv(design.T @ precision @ design)
    np.testing.assert_allclose(result["coefficient_covariance"], expected, atol=1e-12)


def test_complex_correction_full_joint_uncertainty_numerical_jacobian():
    rng = np.random.default_rng(3)
    basis = rng.normal(size=(4, 4)) * 0.01
    coeff_cov = basis @ basis.T
    gain, offset = 0.3 + 1.7j, -2 + 1j
    calibration = dict(gain=gain, offset=offset, coefficient_covariance=coeff_cov)
    measured = np.array([2 + 3j, -5 + 7j])
    noise = np.array([[0.2, -0.06], [-0.06, 0.1]])
    result = apply_complex_response(
        measured, noise, calibration=calibration, block_size=1
    )
    np.testing.assert_allclose(result["corrected"], (measured - offset) / gain)
    theta = np.array([gain.real, gain.imag, offset.real, offset.imag])
    for i, y in enumerate(measured):
        derivative = np.empty((2, 6))
        vector = np.r_[y.real, y.imag, theta]

        def correct(v):
            value = (complex(*v[:2]) - complex(*v[4:6])) / complex(*v[2:4])
            return np.array([value.real, value.imag])

        for j in range(6):
            plus, minus = vector.copy(), vector.copy()
            plus[j] += 1e-5
            minus[j] -= 1e-5
            derivative[:, j] = (correct(plus) - correct(minus)) / 2e-5
        expected = derivative @ block_diag(noise, coeff_cov) @ derivative.T
        np.testing.assert_allclose(
            result["covariance_real_imag"][i], expected, rtol=1e-8, atol=1e-12
        )


def test_complex_bad_calibration_errors_budgets_cancel():
    with pytest.raises(ValueError, match="rank"):
        fit_complex_response([1j, 1j], [1j, 2j], np.eye(2))
    with pytest.raises(ValueError, match="definite"):
        fit_complex_response([1j, 2j], [1j, 2j], [[1.0, 2.0], [2.0, 1.0]])
    calibration = dict(gain=1j, offset=0j, coefficient_covariance=np.zeros((4, 4)))
    with pytest.raises(InterruptedError):
        apply_complex_response(
            [1j], np.eye(2), calibration=calibration, cancel=lambda: True
        )
    with pytest.raises(ValueError, match="budget"):
        apply_complex_response(
            [1j, 2j], np.eye(2), calibration=calibration, max_samples=1
        )
    with pytest.raises(ValueError, match="gain"):
        apply_complex_response([1j], np.eye(2), calibration=dict(calibration, gain=0))


def test_covariance_not_silently_symmetrized_or_masks_lost():
    with pytest.raises(ValueError, match="symmetric"):
        fit_complex_response([1j, 2j], [1j, 2j], [[1.0, 0.1], [0.2, 1.0]])
    x = np.ma.array([1j, 2j], mask=[False, True])
    with pytest.raises(ValueError, match="Masked"):
        fit_complex_response(x, [1j, 2j], np.eye(2))


def test_calibration_rank_is_invariant_to_physical_units():
    reference = np.array([1 + 2j, 3 - 1j, -2 + 0.5j, 0.0, 4 + 2j]) * 1e-12
    gain, offset = 0.5 + 2j, 3e-14 - 4e-14j
    fit = fit_complex_response(reference, gain * reference + offset, np.eye(2) * 1e-28)
    np.testing.assert_allclose(fit["gain"], gain, rtol=1e-12)
    np.testing.assert_allclose(fit["offset"], offset, atol=1e-26)
    assert fit["design_condition"] < 10
    c, s, b, args = standards()
    c[:, 0] *= 1e-15
    s[:, 0] /= 1e-15
    fit = fit_radiometric_response(c, c @ s.T + b, np.eye(2), **args)
    np.testing.assert_allclose(fit["sensitivity"], s, rtol=1e-12)

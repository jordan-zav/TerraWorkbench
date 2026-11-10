"""Mixture inversion and independent dense Gaussian posterior comparisons."""

import numpy as np
import pytest

from terraworkbench_core.radiometric_radon import paired_detector_radon


def test_radon_no_smoothing_matches_direct_mixing_inverse_and_covariance():
    n = 6
    ground, radon = (
        np.linspace(10.0, 20.0, n),
        np.array([2.0, 3.0, -1.0, 4.0, 5.0, 6.0]),
    )
    matrix = np.array([[1.0, 1.2], [0.1, 0.8]])
    data = np.column_stack([ground, radon]) @ matrix.T
    result = paired_detector_radon(
        np.arange(n),
        data[:, 0],
        data[:, 1],
        downward_std=np.ones(n) * 2,
        upward_std=np.ones(n),
        covariance_down_up=0.3,
        downward_radon_response=1.2,
        upward_ground_response=0.1,
        upward_radon_response=0.8,
        roughness=0.0,
    )
    np.testing.assert_allclose(result["terrestrial_u_rate"], ground)
    np.testing.assert_allclose(result["radon_proxy"], radon)
    inverse = np.linalg.inv(matrix)
    covariance = inverse @ np.array([[4.0, 0.3], [0.3, 1.0]]) @ inverse.T
    np.testing.assert_allclose(
        result["terrestrial_posterior_variance"], covariance[0, 0]
    )
    np.testing.assert_allclose(result["radon_posterior_variance"], covariance[1, 1])
    np.testing.assert_allclose(
        result["local_ground_radon_posterior_covariance"], covariance[0, 1]
    )
    assert result["negative_radon"][2]


def test_radon_temporal_posterior_matches_dense_joint_inverse():
    n, alpha, beta, gamma, rough = 5, 1.2, 0.1, 0.8, 2.0
    time = np.array([0.0, 1.0, 3.0, 5.0, 8.0])
    d, u = np.array([12.0, 13.0, 14.0, 11.0, 15.0]), np.array([3.0, 4.0, 5.0, 4.0, 4.0])
    sd, su = np.ones(n) * 2, np.ones(n)
    result = paired_detector_radon(
        time,
        d,
        u,
        downward_std=sd,
        upward_std=su,
        downward_radon_response=alpha,
        upward_ground_response=beta,
        upward_radon_response=gamma,
        roughness=rough,
    )
    design = np.block(
        [[np.eye(n), alpha * np.eye(n)], [beta * np.eye(n), gamma * np.eye(n)]]
    )
    weights = np.diag(np.r_[1 / sd**2, 1 / su**2])
    difference = np.zeros((n - 1, 2 * n))
    for i in range(n - 1):
        difference[i, n + i : n + i + 2] = [-1, 1] / np.sqrt(time[i + 1] - time[i])
    precision = design.T @ weights @ design + rough * difference.T @ difference
    covariance = np.linalg.inv(precision)
    mean = covariance @ design.T @ weights @ np.r_[d, u]
    np.testing.assert_allclose(result["radon_proxy"], mean[n:], atol=1e-12)
    np.testing.assert_allclose(result["terrestrial_u_rate"], mean[:n], atol=1e-12)
    np.testing.assert_allclose(
        result["radon_posterior_variance"], np.diag(covariance)[n:], atol=1e-12
    )
    np.testing.assert_allclose(
        result["terrestrial_posterior_variance"], np.diag(covariance)[:n], atol=1e-12
    )


def test_radon_segments_never_smooth_across_flight_reset():
    t = [0.0, 1.0, 0.0, 1.0]
    result = paired_detector_radon(
        t,
        [1.0, 1.0, 100.0, 100.0],
        [1.0, 1.0, 100.0, 100.0],
        downward_std=np.ones(4),
        upward_std=np.ones(4),
        downward_radon_response=1.0,
        upward_ground_response=0.0,
        upward_radon_response=1.0,
        roughness=1e4,
        segment_ids=[1, 1, 2, 2],
    )
    np.testing.assert_allclose(
        result["radon_proxy"], [1.0, 1.0, 100.0, 100.0], rtol=1e-10
    )
    with pytest.raises(ValueError, match="distinguish"):
        paired_detector_radon(
            [0.0, 1.0],
            [1.0, 1.0],
            [1.0, 1.0],
            downward_std=[1.0, 1.0],
            upward_std=[1.0, 1.0],
            downward_radon_response=1.0,
            upward_ground_response=1.0,
            upward_radon_response=1.0,
            roughness=0.0,
        )

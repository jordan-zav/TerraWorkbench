"""Prescribed-source fields, reference invariance and well-trajectory geometry."""

import numpy as np
import pytest

from terraworkbench_core.borehole import minimum_curvature_trajectory, log_depth_qc
from terraworkbench_core.self_potential import (
    prescribed_source_potential,
    invert_source_currents,
    adjust_reference_network,
)


def test_point_current_halfspace_analytic_and_reference_invariance():
    sources = [[-10.0, 0, -5], [10.0, 0, -5]]
    obs = np.column_stack([np.linspace(-30, 30, 21), np.full(21, 3.0), np.zeros(21)])
    ref = np.array([50.0, 0, 0])
    current, sigma = np.array([0.01, -0.01]), 0.1
    result = prescribed_source_potential(
        obs, ref, sources, current, conductivity_s_m=sigma
    )
    radius = np.linalg.norm(obs[:, None, :] - np.array(sources), axis=-1)
    ref_radius = np.linalg.norm(ref - np.array(sources), axis=-1)
    expected = (1 / radius - 1 / ref_radius) @ current / (2 * np.pi * sigma)
    np.testing.assert_allclose(result["potential_difference_v"], expected)
    full = prescribed_source_potential(
        obs, ref, sources, current, conductivity_s_m=sigma, space="full"
    )
    np.testing.assert_allclose(
        result["potential_difference_v"], 2 * full["potential_difference_v"]
    )
    changed = prescribed_source_potential(
        obs, obs[0], sources, current, conductivity_s_m=sigma
    )
    np.testing.assert_allclose(
        changed["potential_difference_v"], expected - expected[0], atol=1e-17
    )
    with pytest.raises(ValueError, match="conserved"):
        prescribed_source_potential(
            obs, ref, sources, [0.01, 0], conductivity_s_m=sigma
        )


def test_prescribed_source_current_recovery_and_network_adjustment():
    obs = np.column_stack([np.linspace(-30, 30, 21), np.full(21, 3.0), np.zeros(21)])
    sources = [[-10.0, 0, -5], [10.0, 0, -5], [0.0, 0, -15]]
    current = [0.01, -0.006, -0.004]
    data = prescribed_source_potential(
        obs, [50.0, 0, 0], sources, current, conductivity_s_m=0.1
    )["potential_difference_v"]
    fit = invert_source_currents(
        obs,
        [50.0, 0, 0],
        sources,
        data,
        voltage_std_v=np.full(21, 1e-6),
        conductivity_s_m=0.1,
        beta=1e-6,
    )
    np.testing.assert_allclose(fit["current_a"], current, atol=1e-9)
    assert abs(fit["current_a"].sum()) < 1e-15
    q = np.array([[0, 1], [1, 2], [2, 0], [2, 3]])
    potential = np.array([0.0, 0.02, -0.01, 0.03])
    voltage = potential[q[:, 0]] - potential[q[:, 1]]
    network = adjust_reference_network(
        q, voltage, voltage_std_v=np.full(4, 1e-4), node_count=4, anchors_v={0: 0.0}
    )
    np.testing.assert_allclose(network["node_potential_v"], potential, atol=1e-14)
    assert network["degrees_of_freedom"] == 1
    with pytest.raises(ValueError, match="Disconnected"):
        adjust_reference_network(
            [[0, 1], [2, 3]],
            [0.0, 0.0],
            voltage_std_v=[0.1, 0.1],
            node_count=4,
            anchors_v={0: 0.0},
        )


def test_minimum_curvature_vertical_horizontal_and_circular_arc():
    vertical = minimum_curvature_trajectory(
        [0.0, 50.0, 100.0],
        [0.0, 0.0, 0.0],
        [0.0, 30.0, 90.0],
        collar_enu_m=[500000.0, 6000000.0, 1000.0],
    )
    np.testing.assert_allclose(
        vertical["coordinates_enu_m"][-1], [500000.0, 6000000.0, 900.0]
    )
    horizontal = minimum_curvature_trajectory(
        [0.0, 100.0], [90.0, 90.0], [90.0, 90.0], collar_enu_m=[0.0, 0.0, 0.0]
    )
    np.testing.assert_allclose(
        horizontal["coordinates_enu_m"][-1], [100.0, 0.0, 0.0], atol=1e-12
    )
    arc = minimum_curvature_trajectory(
        [0.0, 100.0], [0.0, 90.0], [0.0, 0.0], collar_enu_m=[0.0, 0.0, 0.0]
    )
    np.testing.assert_allclose(
        arc["coordinates_enu_m"][-1], [0.0, 200 / np.pi, -200 / np.pi], atol=1e-12
    )
    with pytest.raises(ValueError, match="Antipodal"):
        minimum_curvature_trajectory(
            [0.0, 100.0], [0.0, 180.0], [0.0, 0.0], collar_enu_m=[0.0, 0.0, 0.0]
        )


def test_log_depth_qc_preserves_order_missing_and_reports_gaps():
    depth = [0.0, 1.0, 1.0, 20.0, 18.0]
    curves = [[1.0, 2.0], [-999.25, 3.0], [3.0, 4.0], [4.0, 5.0], [5.0, 6.0]]
    result = log_depth_qc(depth, curves, missing_value=-999.25, maximum_gap_m=5.0)
    assert not result["strictly_increasing"]
    np.testing.assert_array_equal(result["depth_m"], depth)
    np.testing.assert_array_equal(result["duplicate_intervals"], [1])
    np.testing.assert_array_equal(result["large_gap_intervals"], [2])
    assert np.isnan(result["curves"][1, 0])

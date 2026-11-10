"""Analytic multi-off-period stacking and bounded inverse contracts."""

import json
from pathlib import Path

import numpy as np
import pytest

from terraworkbench_core.ip_stacking import stack_ip_decay, fit_ip_stack
from terraworkbench_core.ip_waveform import ip_waveform_decay

EVENTS = np.array([-7.0, -6.0, -5.0, -4.0, -3.0, -2.0, -1.0, 0.0])
CURRENTS = np.array([1.0, 0.0, -2.0, 0.0, 0.8, 0.0, -1.5, 0.0])
OFFS = [1, 3, 5, 7]


def analytic_cycles(gates, m, tau):
    secondary, primary = [], []
    for index in OFFS:
        shifts = EVENTS[: index + 1] - EVENTS[index]
        levels = CURRENTS[: index + 1] / CURRENTS[index - 1]
        changes = np.diff(np.r_[0.0, levels])
        # Independent Debye gate integrals and final on-time voltage.
        values = np.zeros(len(gates))
        for shift, change in zip(shifts, changes):
            values -= (
                m
                * change
                * tau
                * (
                    np.exp(-(gates[:, 0] - shift) / tau)
                    - np.exp(-(gates[:, 1] - shift) / tau)
                )
                / (gates[:, 1] - gates[:, 0])
            )
        secondary.append(values)
        primary.append(1 - m * sum(changes[:-1] * np.exp(shifts[:-1] / tau)))
    return np.array(secondary), np.array(primary)


@pytest.mark.parametrize("normalization", ["dc", "pulse"])
@pytest.mark.parametrize("mode", ["mean_of_ratios", "ratio_of_sums"])
def test_stack_matches_independent_debye_gate_formula(normalization, mode):
    gates = np.array([[0.0, 0.1], [0.2, 0.4], [0.6, 1.0]])
    weights = np.array([1.0, 3.0, 2.0, 4.0]) / 10
    secondary, primary = analytic_cycles(gates, 0.2, 1.3)
    denominators = primary if normalization == "pulse" else np.ones(4)
    if mode == "mean_of_ratios":
        expected = weights @ (secondary / denominators[:, None])
    else:
        raw_weights = weights * abs(CURRENTS[np.array(OFFS) - 1])
        expected = raw_weights @ secondary / (raw_weights @ denominators)
    actual = stack_ip_decay(
        EVENTS,
        CURRENTS,
        OFFS,
        gates_s=gates,
        chargeability=0.2,
        tau_s=1.3,
        exponent=1.0,
        stack_weights=weights,
        stack_mode=mode,
        normalization=normalization,
    )
    np.testing.assert_allclose(actual["decay_v_v"], expected, atol=1e-14)
    np.testing.assert_allclose(actual["cycle_secondary_to_dc"], secondary, atol=1e-14)
    np.testing.assert_allclose(actual["cycle_primary_to_dc_ratio"], primary, atol=1e-14)


def test_modes_differ_and_full_current_reversal_preserves_stack():
    times = np.geomspace(0.001, 0.8, 14)
    a = stack_ip_decay(
        EVENTS,
        CURRENTS,
        OFFS,
        times_s=times,
        chargeability=0.2,
        stack_mode="mean_of_ratios",
    )
    b = stack_ip_decay(
        EVENTS,
        CURRENTS,
        OFFS,
        times_s=times,
        chargeability=0.2,
        stack_mode="ratio_of_sums",
    )
    assert np.max(abs(a["decay_v_v"] - b["decay_v_v"])) > 0.001
    flipped = stack_ip_decay(
        EVENTS,
        -3 * CURRENTS,
        OFFS,
        times_s=times,
        chargeability=0.2,
        stack_mode="ratio_of_sums",
    )
    np.testing.assert_allclose(flipped["decay_v_v"], b["decay_v_v"], atol=1e-14)
    np.testing.assert_allclose(
        flipped["cycle_reference_current_a"], -3 * b["cycle_reference_current_a"]
    )


def test_selected_single_cycle_preserves_all_previous_polarization():
    times = np.geomspace(0.002, 0.8, 12)
    actual = stack_ip_decay(
        EVENTS, CURRENTS, [5], times_s=times, stack_mode="mean_of_ratios"
    )["decay_v_v"]
    expected = ip_waveform_decay(EVENTS[:6] - EVENTS[5], CURRENTS[:6], times_s=times)[
        "decay_v_v"
    ]
    np.testing.assert_allclose(actual, expected, atol=1e-14)


@pytest.mark.parametrize("mode", ["mean_of_ratios", "ratio_of_sums"])
def test_curve_inverse_recovers_c_and_tau_for_complete_stack(mode):
    edges = np.geomspace(0.001, 0.9, 17)
    gates = np.c_[edges[:-1], edges[1:]]
    observed = stack_ip_decay(
        EVENTS,
        CURRENTS,
        OFFS,
        gates_s=gates,
        chargeability=0.13,
        tau_s=0.7,
        exponent=0.6,
        stack_mode=mode,
    )["decay_v_v"]
    fitted = fit_ip_stack(
        EVENTS,
        CURRENTS,
        OFFS,
        observed,
        gates_s=gates,
        stack_mode=mode,
        initial=[0.1, 0.5, 0.7],
        standard_deviation=1e-4,
    )
    assert fitted["success"] and fitted["data_rank"] == 3
    np.testing.assert_allclose(fitted["parameters"], [0.13, 0.7, 0.6], rtol=2e-5)


def test_spatial_ratio_is_applied_after_zone_mixing_and_cycle_sums():
    S = np.array([[0.7, 0.3], [0.2, 0.8], [0.5, 0.5]])
    parameters = np.array([[0.12, 0.5, 0.5], [0.08, 1.2, 0.8]])
    times = np.geomspace(0.002, 0.8, 13)
    response = stack_ip_decay(
        EVENTS,
        CURRENTS,
        OFFS,
        times_s=times,
        chargeability=parameters[:, 0],
        tau_s=parameters[:, 1],
        exponent=parameters[:, 2],
        sensitivity=S,
        stack_mode="ratio_of_sums",
    )
    amplitude = abs(CURRENTS[np.array(OFFS) - 1])
    expected = (
        np.tensordot(amplitude, response["cycle_secondary_to_dc"], axes=1)
        / (amplitude @ response["cycle_primary_to_dc_ratio"])[:, None]
    )
    np.testing.assert_allclose(response["decay_v_v"], expected, atol=1e-14)
    start = np.array([[0.1, 0.7, 0.6], [0.1, 1.0, 0.7]])
    fitted = fit_ip_stack(
        EVENTS,
        CURRENTS,
        OFFS,
        response["decay_v_v"],
        sensitivity=S,
        times_s=times,
        stack_mode="ratio_of_sums",
        initial=start,
        reference=start,
        beta=0.0,
        standard_deviation=1e-4,
    )
    assert fitted["success"] and fitted["data_rank"] == 6
    np.testing.assert_allclose(
        fitted["parameters"].reshape(-1, 3), parameters, rtol=2e-5
    )


@pytest.mark.parametrize(
    "indices",
    [[0], [2], [3, 1], [1, 1], [1.0], [True], [8], np.array([3, 1], dtype=np.uint64)],
)
def test_invalid_off_cycle_selection_is_rejected(indices):
    with pytest.raises(ValueError):
        stack_ip_decay(
            EVENTS, CURRENTS, indices, times_s=[0.1], stack_mode="mean_of_ratios"
        )


def test_weights_window_boundaries_budget_and_cancellation_are_explicit():
    for weights in ([0, 0, 0, 0], [1, -1, 1, 1], [np.nan] * 4, [1]):
        with pytest.raises(ValueError):
            stack_ip_decay(
                EVENTS,
                CURRENTS,
                OFFS,
                times_s=[0.1],
                stack_weights=weights,
                stack_mode="mean_of_ratios",
            )
    # A gate may end at the next switch, while a point sample at that switch
    # would include on-time voltage and is rejected.
    stack_ip_decay(
        EVENTS, CURRENTS, OFFS, gates_s=[[0.5, 1.0]], stack_mode="mean_of_ratios"
    )
    with pytest.raises(ValueError, match="off-period"):
        stack_ip_decay(
            EVENTS, CURRENTS, OFFS, times_s=[1.0], stack_mode="mean_of_ratios"
        )
    with pytest.raises(ValueError, match="4096"):
        stack_ip_decay(
            EVENTS,
            CURRENTS,
            OFFS,
            times_s=np.linspace(0, 0.9, 205),
            stack_mode="mean_of_ratios",
        )
    with pytest.raises(InterruptedError):
        stack_ip_decay(
            EVENTS,
            CURRENTS,
            OFFS,
            times_s=[0.1],
            stack_mode="mean_of_ratios",
            cancel=lambda: True,
        )
    with pytest.raises(ValueError, match="Choose"):
        stack_ip_decay(EVENTS, CURRENTS, OFFS, times_s=[0.1], stack_mode="unknown")


def test_redundant_zero_current_markers_do_not_truncate_an_off_period():
    actual = stack_ip_decay(
        [-4.0, -3.0, -2.0, -1.0, 0.0],
        [1.0, 0.0, 0.0, -1.0, 0.0],
        [1, 4],
        gates_s=[[0.5, 1.5]],
        stack_mode="mean_of_ratios",
    )
    expected = stack_ip_decay(
        [-4.0, -3.0, -1.0, 0.0],
        [1.0, 0.0, -1.0, 0.0],
        [1, 3],
        gates_s=[[0.5, 1.5]],
        stack_mode="mean_of_ratios",
    )
    np.testing.assert_allclose(actual["decay_v_v"], expected["decay_v_v"], atol=2e-12)


def test_zero_weight_cycles_are_explicit_and_do_not_change_the_stack():
    times = [0.01, 0.1, 0.5]
    full = stack_ip_decay(
        EVENTS,
        CURRENTS,
        OFFS,
        times_s=times,
        stack_weights=[0, 0, 1, 0],
        stack_mode="ratio_of_sums",
    )
    selected = stack_ip_decay(
        EVENTS, CURRENTS, [5], times_s=times, stack_mode="ratio_of_sums"
    )
    np.testing.assert_allclose(full["decay_v_v"], selected["decay_v_v"], atol=1e-14)


def test_near_zero_cycle_primary_is_not_confused_with_stacked_primary():
    m = 0.2
    previous = (1 / m - np.exp(-1.0)) / (np.exp(-3.0) - np.exp(-2.0))
    options = dict(
        event_times_s=[-3.0, -2.0, -1.0, 0.0],
        current_a=[previous, 0.0, 1.0, 0.0],
        off_event_indices=[1, 3],
        times_s=[0.01, 0.1],
        chargeability=m,
        tau_s=1.0,
        exponent=1.0,
    )
    with pytest.raises(ValueError, match="cycle primary"):
        stack_ip_decay(**options, stack_mode="mean_of_ratios")
    valid = stack_ip_decay(**options, stack_mode="ratio_of_sums")
    assert np.isfinite(valid["decay_v_v"]).all()
    ignored = stack_ip_decay(
        **options, stack_mode="mean_of_ratios", stack_weights=[1, 0]
    )
    assert np.isfinite(ignored["decay_v_v"]).all()


def test_spatial_stack_output_budget_and_explicit_prior_contract():
    with pytest.raises(ValueError, match="cycle-output"):
        stack_ip_decay(
            EVENTS,
            CURRENTS,
            OFFS,
            times_s=np.linspace(0.0, 0.9, 64),
            sensitivity=np.ones((1000, 1)),
            chargeability=[0.1],
            tau_s=[1.0],
            exponent=[0.5],
            stack_mode="mean_of_ratios",
        )
    with pytest.raises(ValueError, match="beta"):
        fit_ip_stack(
            EVENTS,
            CURRENTS,
            OFFS,
            np.ones((1, 4)),
            times_s=[0.01, 0.1, 0.2, 0.3],
            sensitivity=[[1.0]],
            initial=[[0.1, 1.0, 0.5]],
            standard_deviation=1e-4,
            stack_mode="mean_of_ratios",
        )


def test_workflow_recovers_stacked_curve_with_typed_result_reference(tmp_path):
    from terraworkbench_core.operation_jobs import load_core_job
    from terraworkbench_core.operation_workflows import run_core_workflow

    common = dict(
        event_times_s=EVENTS.tolist(),
        current_a=CURRENTS.tolist(),
        off_event_indices=OFFS,
        times_s=np.geomspace(0.002, 0.8, 14).tolist(),
        stack_mode="mean_of_ratios",
    )
    plan = {
        "steps": [
            {
                "id": "stack",
                "operation": "ip.stack_decay",
                "parameters": {
                    **common,
                    "chargeability": 0.12,
                    "tau_s": 0.7,
                    "exponent": 0.5,
                },
            },
            {
                "id": "fit",
                "operation": "ip.fit_stack",
                "parameters": {
                    **common,
                    "observed_v_v": {"$result": ["stack", "decay_v_v"]},
                    "initial": [0.1, 0.5, 0.6],
                    "standard_deviation": 1e-4,
                },
            },
        ]
    }
    output = Path(run_core_workflow(json.dumps(plan), tmp_path)["folder"])
    summary = json.loads((output / "workflow.json").read_text())
    loaded = load_core_job(output / summary["steps"][-1]["folder"])
    assert loaded["result"]["success"] and loaded["provenance"]["source_sha256"]
    np.testing.assert_allclose(
        loaded["result"]["parameters"], [0.12, 0.7, 0.5], rtol=2e-5
    )

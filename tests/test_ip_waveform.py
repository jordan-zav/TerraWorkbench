"""Independent pulse-history checks, inversion and workflow integration."""

import json

import numpy as np
import pytest
from scipy.special import erfcx

from terraworkbench_core.dispersive_ip import cole_cole_decay, dispersive_ip_forward
from terraworkbench_core.ip_waveform import (
    fit_ip_waveform,
    fit_spatial_ip_waveform,
    ip_waveform_decay,
    spatial_ip_waveform,
)


EVENTS = [-7.0, -5.0, -3.0, -1.0, 0.0]
CURRENTS = [2.0, 0.0, -2.0, 2.0, 0.0]


@pytest.mark.parametrize("c", [0.4, 0.5, 1.0])
@pytest.mark.parametrize("normalization", ["dc", "pulse"])
def test_single_pulse_is_compatible_with_existing_cole_cole(c, normalization):
    edges = np.geomspace(0.001, 8.0, 13)
    gates = np.c_[edges[:-1], edges[1:]]
    actual = ip_waveform_decay(
        [-1.3, 0],
        [-3.0, 0],
        gates_s=gates,
        chargeability=0.17,
        tau_s=0.8,
        exponent=c,
        normalization=normalization,
    )
    expected = cole_cole_decay(
        gates_s=gates,
        chargeability=0.17,
        tau_s=0.8,
        exponent=c,
        pulse_duration_s=1.3,
        normalization=normalization,
    )
    np.testing.assert_allclose(actual["decay_v_v"], expected, atol=3e-12, rtol=2e-10)
    assert actual["reference_current_a"] == -3.0


def test_bipolar_debye_gates_match_closed_form_signed_step_sum():
    gates = np.array([[0.0, 0.1], [0.2, 0.7], [1.0, 2.0]])
    tau, m = 1.1, 0.21
    # Relative switch increments are +1,-1,-1,+2,-1.
    coefficients = [1.0, -1.0, -1.0, 2.0, -1.0]
    decay = np.zeros(3)
    for time, coefficient in zip(EVENTS, coefficients):
        decay -= (
            coefficient
            * tau
            * (
                np.exp(-(gates[:, 0] - time) / tau)
                - np.exp(-(gates[:, 1] - time) / tau)
            )
            / (gates[:, 1] - gates[:, 0])
        )
    primary = 1.0 - m * sum(
        coefficient * np.exp(time / tau)
        for time, coefficient in zip(EVENTS[:-1], coefficients[:-1])
    )
    response = ip_waveform_decay(
        EVENTS,
        CURRENTS,
        gates_s=gates,
        chargeability=m,
        tau_s=tau,
        exponent=1.0,
    )
    np.testing.assert_allclose(response["decay_v_v"], m * decay / primary, atol=1e-14)
    assert response["primary_to_dc_ratio"] == pytest.approx(primary)


def test_half_order_matches_erfcx_superposition_and_signed_current_scaling():
    times = np.geomspace(0.001, 20.0, 22)
    tau, m = 2.5, 0.13
    weights = np.array([1, -1, -1, 2, -1])
    response = ip_waveform_decay(
        EVENTS,
        CURRENTS,
        times_s=times,
        chargeability=m,
        tau_s=tau,
        exponent=0.5,
    )
    relaxation = erfcx(np.sqrt((times[None, :] - np.array(EVENTS)[:, None]) / tau))
    primary = 1 - m * weights[:-1] @ erfcx(np.sqrt(-np.array(EVENTS[:-1]) / tau))
    np.testing.assert_allclose(
        response["decay_v_v"], -m * weights @ relaxation / primary, atol=2e-12
    )
    flipped = ip_waveform_decay(
        EVENTS,
        -3.0 * np.array(CURRENTS),
        times_s=times,
        chargeability=m,
        tau_s=tau,
        exponent=0.5,
    )
    np.testing.assert_allclose(flipped["decay_v_v"], response["decay_v_v"], atol=1e-14)
    assert flipped["reference_current_a"] == -6.0
    isolated = cole_cole_decay(
        times, m, tau, 0.5, pulse_duration_s=1.0, normalization="pulse"
    )
    assert np.max(abs(isolated - response["decay_v_v"])) > 0.005


def test_complete_history_gate_inverse_and_optimizer_status():
    edges = np.geomspace(0.005, 9.0, 17)
    gates = np.c_[edges[:-1], edges[1:]]
    observed = ip_waveform_decay(
        EVENTS, CURRENTS, gates_s=gates, chargeability=0.14, tau_s=0.9, exponent=0.6
    )["decay_v_v"]
    result = fit_ip_waveform(
        EVENTS,
        CURRENTS,
        observed,
        gates_s=gates,
        initial=[0.1, 0.6, 0.7],
        standard_deviation=1e-4,
    )
    assert result["success"] and result["data_rank"] == 3
    np.testing.assert_allclose(result["parameters"], [0.14, 0.9, 0.6], rtol=2e-5)
    assert result["forward_evaluations"] > result["optimizer_evaluations"]
    limited = fit_ip_waveform(
        EVENTS,
        CURRENTS,
        observed,
        gates_s=gates,
        initial=[0.1, 0.6, 0.7],
        standard_deviation=1e-4,
        max_evaluations=1,
    )
    assert not limited["success"]


def test_spatial_single_pulse_uses_common_primary_after_mixing_zones():
    S = np.array([[0.7, 0.3], [0.2, 0.8]])
    times = np.geomspace(0.01, 5.0, 12)
    parameters = ([0.12, 0.08], [0.6, 1.8], [0.5, 0.8])
    actual = spatial_ip_waveform(S, [-2.0, 0], [1, 0], *parameters, times_s=times)
    expected = dispersive_ip_forward(
        S,
        times,
        *parameters,
        domain="time",
        pulse_duration_s=2.0,
        normalization="pulse",
    )
    np.testing.assert_allclose(actual["decay_v_v"], expected, atol=3e-12)


def test_two_zone_bipolar_inverse_recovers_parameters():
    S = np.array([[0.7, 0.3], [0.2, 0.8], [0.5, 0.5]])
    times = np.geomspace(0.005, 8.0, 15)
    truth = np.array([[0.12, 0.6, 0.5], [0.08, 1.8, 0.8]])
    observed = spatial_ip_waveform(S, EVENTS, CURRENTS, *truth.T, times_s=times)[
        "decay_v_v"
    ]
    start = np.array([[0.1, 0.8, 0.6], [0.1, 1.2, 0.7]])
    result = fit_spatial_ip_waveform(
        S,
        EVENTS,
        CURRENTS,
        observed,
        times_s=times,
        initial=start,
        reference=start,
        standard_deviation=1e-4,
        beta=0.0,
    )
    assert result["success"] and result["data_rank"] == 6
    np.testing.assert_allclose(result["parameters"].reshape(-1, 3), truth, rtol=2e-5)


@pytest.mark.parametrize(
    "events,currents",
    [
        ([-1, 1], [1, 0]),
        ([-1, 0], [1, 1]),
        ([-1, 0], [0, 0]),
        ([-1, -1, 0], [1, 0, 0]),
        ([-1, 0], [np.nan, 0]),
        ([-3, -1, 0], [1e8, 1, 0]),
    ],
)
def test_invalid_current_histories_are_rejected(events, currents):
    with pytest.raises(ValueError):
        ip_waveform_decay(events, currents, times_s=[0.1])


def test_work_budget_masks_ambiguous_primary_and_cancellation_are_explicit():
    with pytest.raises(ValueError, match="4096"):
        ip_waveform_decay(EVENTS, CURRENTS, times_s=np.arange(1000))
    with pytest.raises(ValueError, match="Supply"):
        ip_waveform_decay(EVENTS, CURRENTS)
    with pytest.raises(ValueError):
        ip_waveform_decay(EVENTS, CURRENTS, gates_s=[[0.1, 0.1]])
    with pytest.raises(ValueError):
        ip_waveform_decay(
            EVENTS, np.ma.array(CURRENTS, mask=[1, 0, 0, 0, 0]), times_s=[0]
        )
    with pytest.raises(InterruptedError):
        ip_waveform_decay(EVENTS, CURRENTS, times_s=[0.1], cancel=lambda: True)
    # Large opposite prehistory can cancel the final pre-switch primary.
    m, tau = 0.2, 1.0
    previous = (1 / m - np.exp(-0.1 / tau)) / (np.exp(-0.2 / tau) - np.exp(-0.1 / tau))
    with pytest.raises(ValueError, match="primary"):
        ip_waveform_decay(
            [-0.2, -0.1, 0],
            [previous, 1, 0],
            times_s=[0.1],
            chargeability=m,
            tau_s=tau,
            exponent=1.0,
        )


def test_core_waveform_workflow_exports_provenance_and_typed_results(tmp_path):
    from terraworkbench_core.operation_jobs import load_core_job
    from terraworkbench_core.operation_workflows import run_core_workflow

    times = np.geomspace(0.01, 5, 12).tolist()
    common = dict(event_times_s=EVENTS, current_a=CURRENTS, times_s=times)
    plan = {
        "steps": [
            {
                "id": "decay",
                "operation": "ip.waveform_decay",
                "parameters": {
                    **common,
                    "chargeability": 0.12,
                    "tau_s": 0.7,
                    "exponent": 0.5,
                },
            },
            {
                "id": "fit",
                "operation": "ip.fit_waveform",
                "parameters": {
                    **common,
                    "observed_v_v": {"$result": ["decay", "decay_v_v"]},
                    "initial": [0.1, 1.0, 0.6],
                    "standard_deviation": 1e-4,
                },
            },
        ]
    }
    result = run_core_workflow(json.dumps(plan), tmp_path)
    from pathlib import Path

    folder = Path(result["folder"])
    summary = json.loads((folder / "workflow.json").read_text())
    step = next(step for step in summary["steps"] if step["id"] == "fit")
    loaded = load_core_job(folder / step["folder"])
    assert loaded["result"]["success"] and loaded["provenance"]["source_sha256"]
    np.testing.assert_allclose(
        loaded["result"]["parameters"], [0.12, 0.7, 0.5], rtol=2e-5
    )


def test_spatial_overflow_and_output_budget_are_rejected():
    with pytest.raises(ValueError, match="overflow"):
        spatial_ip_waveform(
            np.full((1, 2), 1e308),
            [-0.2, -0.1, 0],
            [1000, 1, 0],
            [0.2, 0.2],
            [1.0, 1.0],
            [1.0, 1.0],
            times_s=[0.1],
        )
    with pytest.raises(ValueError, match="sample budget"):
        spatial_ip_waveform(
            np.ones((2000, 1)),
            [-1, 0],
            [1, 0],
            [0.1],
            [1.0],
            [0.5],
            times_s=np.linspace(0.0, 1.0, 100),
        )

"""Independent Debye/half-order checks and spectral/transient inversion controls."""

import numpy as np
import pytest
from scipy.special import erfcx

from terraworkbench_core.dispersive_ip import (
    cole_cole_decay,
    fit_cole_cole_spectrum,
    fit_ip_decay,
    dispersive_ip_forward,
    fit_dispersive_ip,
)
from terraworkbench_core.electrical import cole_cole_resistivity


def test_relaxation_matches_debye_and_half_order_analytic_limits():
    times = np.r_[0.0, np.geomspace(1e-6, 1e5, 30)]
    for c in (1.0, 0.5):
        actual = cole_cole_decay(times, 0.2, 0.7, c)
        expected = 0.2 * (
            np.exp(-times / 0.7) if c == 1 else erfcx(np.sqrt(times / 0.7))
        )
        np.testing.assert_allclose(actual, expected, rtol=1e-7, atol=1e-11)
        # Debye tails legitimately underflow to repeated machine zeros.
        assert np.all(np.diff(actual) <= 0)


def test_pulse_and_exact_gate_averages_preserve_primary_convention():
    gates = np.array([[0.0, 0.01], [0.02, 0.1], [0.2, 0.8], [1.0, 3.0]])
    m, tau, ton = 0.2, 0.5, 0.8
    expected = (
        m
        * tau
        * (np.exp(-gates[:, 0] / tau) - np.exp(-gates[:, 1] / tau))
        / np.diff(gates)[:, 0]
        * (1.0 - np.exp(-ton / tau))
    )
    actual = cole_cole_decay(None, m, tau, 1.0, gates_s=gates, pulse_duration_s=ton)
    np.testing.assert_allclose(actual, expected, rtol=1e-12)
    measured = cole_cole_decay(
        None, m, tau, 1.0, gates_s=gates, pulse_duration_s=ton, normalization="pulse"
    )
    np.testing.assert_allclose(
        measured, expected / (1.0 - m * np.exp(-ton / tau)), rtol=1e-12
    )
    # For c=0.5 the time-domain response has an independent erfcx form.
    times = np.geomspace(0.001, 10.0, 20)
    half = m * (erfcx(np.sqrt(times / tau)) - erfcx(np.sqrt((times + ton) / tau)))
    np.testing.assert_allclose(
        cole_cole_decay(times, m, tau, 0.5, pulse_duration_s=ton),
        half,
        rtol=1e-8,
        atol=1e-11,
    )


def test_near_debye_limit_and_extreme_invalid_reference_are_explicit():
    times = np.array([0.0, 0.01, 0.1, 1.0, 10.0])
    np.testing.assert_allclose(
        cole_cole_decay(times, 0.1, 1.0, 0.999999), 0.1 * np.exp(-times), atol=1e-6
    )
    with pytest.raises(ValueError, match="Require"):
        fit_ip_decay(
            np.ones(5),
            times_s=times,
            initial=[0.1, 1.0, 0.5],
            reference=[-1.0, 1.0, 0.5],
            standard_deviation=0.01,
        )


def test_complex_spectrum_inverse_full_covariance_and_rank():
    f = np.geomspace(0.001, 1e4, 32)
    truth = [120.0, 0.15, 0.8, 0.65]
    data = cole_cole_resistivity(f, *truth)
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    fit = fit_cole_cole_spectrum(
        f, data, initial=[90.0, 0.1, 0.4, 0.8], data_covariance=cov
    )
    assert fit["success"] and fit["data_rank"] == 4
    np.testing.assert_allclose(fit["parameters"], truth, rtol=1e-5)
    assert fit["weighted_rms"] < 1e-5
    deficient = fit_cole_cole_spectrum(
        np.ones(8), np.repeat(data[10], 8), initial=truth, standard_deviation=0.2
    )
    assert deficient["data_rank"] <= 2


def test_gate_decay_inverse_uses_finite_pulse():
    edges = np.geomspace(0.002, 8.0, 19)
    gates = np.c_[edges[:-1], edges[1:]]
    truth = [0.12, 0.7, 0.5]
    data = cole_cole_decay(None, *truth, gates_s=gates, pulse_duration_s=1.0)
    fit = fit_ip_decay(
        data,
        gates_s=gates,
        initial=[0.08, 0.4, 0.7],
        standard_deviation=1e-4,
        pulse_duration_s=1.0,
    )
    assert fit["success"] and fit["data_rank"] == 3
    np.testing.assert_allclose(fit["parameters"], truth, rtol=1e-4)


@pytest.mark.parametrize("domain", ["frequency", "time"])
def test_spatial_dispersive_inverse_recovers_two_zones(domain):
    sensitivity = np.array([[0.8, 0.2], [0.6, 0.4], [0.3, 0.7], [0.1, 0.9]])
    samples = (
        np.geomspace(0.01, 100.0, 18)
        if domain == "frequency"
        else np.geomspace(0.005, 8.0, 18)
    )
    truth = np.array([[0.05, 0.4, 0.5], [0.12, 1.2, 0.8]])
    data = dispersive_ip_forward(sensitivity, samples, *truth.T, domain=domain)
    fit = fit_dispersive_ip(
        sensitivity,
        samples,
        data,
        initial=[[0.04, 0.3, 0.6], [0.1, 1.0, 0.7]],
        reference=truth,
        beta=1e-6,
        standard_deviation=1e-4,
        domain=domain,
    )
    assert fit["success"] and fit["data_rank"] == 6
    np.testing.assert_allclose(fit["parameters"].reshape(-1, 3), truth, rtol=1e-4)


@pytest.mark.parametrize("dimension", [2, 3])
def test_ip_pde_sensitivity_agrees_with_existing_static_ip(dimension):
    pytest.importorskip("simpeg")
    from terraworkbench_core.electrical_pde import electrical_forward, ip_sensitivity

    h = np.r_[8.0, 4.0, np.repeat(2.0, 8), 4.0, 8.0]
    z = np.r_[8.0, 4.0, np.repeat(2.0, 6)]
    args = dict(
        mesh_widths=[h, z],
        mesh_origin=[-h.sum() / 2, -z.sum()],
        electrodes=[
            [-9.0, 0.0, 0.0],
            [-3.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
            [9.0, 0.0, 0.0],
        ],
        abmn=[[0, 3, 1, 2]],
        parameter_labels=np.zeros(len(h) * len(z), int),
        conductivity_s_m=[0.01],
    )
    if dimension == 3:
        args.update(
            mesh_widths=[np.full(4, 5.0)] * 3,
            mesh_origin=[-10.0, -10.0, -20.0],
            parameter_labels=np.zeros(64, int),
        )
    operator = ip_sensitivity(**args)
    static = electrical_forward(**args, chargeability_v_v=[0.04])["predicted"]
    np.testing.assert_allclose(operator["sensitivity"] @ [0.04], static, rtol=1e-10)
    frequency = [0.0, 1.0, 1e8]
    spectral = dispersive_ip_forward(
        operator["sensitivity"], frequency, [0.04], [1.0], [0.5]
    )
    assert spectral[0, 0] == 0
    np.testing.assert_allclose(spectral[0, -1].real, static[0], rtol=1e-3)


def test_validation_budgets_cancellation_and_nonconverged_status():
    with pytest.raises(ValueError, match="OR"):
        cole_cole_decay([0.1], gates_s=[[0.0, 1.0]])
    with pytest.raises(ValueError, match="ends"):
        cole_cole_decay(gates_s=[[1.0, 0.0]])
    with pytest.raises(InterruptedError):
        cole_cole_decay([0.1], cancel=lambda: True)
    f = np.geomspace(0.01, 100.0, 10)
    data = cole_cole_resistivity(f, 100.0, 0.1, 1.0, 0.5)
    with pytest.raises(RuntimeError, match="budget"):
        fit_cole_cole_spectrum(
            f,
            data,
            initial=[80.0, 0.2, 0.3, 0.7],
            standard_deviation=1.0,
            max_forward_evaluations=1,
        )
    limited = fit_cole_cole_spectrum(
        f,
        data,
        initial=[80.0, 0.2, 0.3, 0.7],
        standard_deviation=1.0,
        max_evaluations=1,
    )
    assert not limited["success"] and limited["weighted_rms"] > 1.0


def test_new_ip_operations_are_callable_from_the_core_api():
    from terraworkbench_core.operations import operation_info, run_operation

    assert operation_info("ip.fit_decay")["domain"] == "time"
    response = run_operation(
        "ip.cole_cole_decay",
        times_s=[0.0, 1.0],
        chargeability=0.1,
        tau_s=1.0,
        exponent=1.0,
    )
    np.testing.assert_allclose(
        response["result"]["decay_v_v"], [0.1, 0.1 * np.exp(-1.0)]
    )


def test_spatial_fit_rejects_dense_work_before_covariance_allocation(monkeypatch):
    from terraworkbench_core import _calibration

    def forbidden(*args, **kwargs):
        raise AssertionError("Covariance was allocated before work-budget validation")

    monkeypatch.setattr(_calibration, "covariance_array", forbidden)
    with pytest.raises(ValueError, match="Jacobian"):
        fit_dispersive_ip(
            np.ones((5000, 2)),
            [1.0] * 100,
            np.ones((5000, 100), complex),
            initial=[[0.1, 1.0, 0.5]] * 2,
            reference=[[0.1, 1.0, 0.5]] * 2,
            beta=0.0,
            data_covariance=np.eye(2),
        )


def test_spatial_transient_supports_measured_finite_pulse_primary():
    times = np.geomspace(0.005, 8.0, 18)
    S = np.ones((2, 1))
    truth = [0.12, 0.7, 0.5]
    observed = dispersive_ip_forward(
        S,
        times,
        [truth[0]],
        [truth[1]],
        [truth[2]],
        domain="time",
        pulse_duration_s=1.0,
        normalization="pulse",
    )
    expected = cole_cole_decay(
        times, *truth, pulse_duration_s=1.0, normalization="pulse"
    )
    np.testing.assert_allclose(observed, np.tile(expected, (2, 1)), rtol=1e-10)
    fit = fit_dispersive_ip(
        S,
        times,
        observed,
        initial=[[0.1, 0.4, 0.7]],
        reference=[[0.08, 0.5, 0.6]],
        beta=0.0,
        standard_deviation=1e-4,
        domain="time",
        pulse_duration_s=1.0,
        normalization="pulse",
    )
    assert fit["success"]
    np.testing.assert_allclose(fit["parameters"], truth, rtol=1e-4)


def test_transient_forward_inverse_core_workflow_exports_typed_results(tmp_path):
    import json
    from pathlib import Path
    from terraworkbench_core.operation_workflows import run_core_workflow
    from terraworkbench_core.operation_jobs import load_core_job

    times = np.geomspace(0.005, 8.0, 16).tolist()
    plan = {
        "steps": [
            {
                "id": "decay",
                "operation": "ip.cole_cole_decay",
                "parameters": {
                    "times_s": times,
                    "chargeability": 0.12,
                    "tau_s": 0.7,
                    "exponent": 0.5,
                    "pulse_duration_s": 1.0,
                },
            },
            {
                "id": "recover",
                "operation": "ip.fit_decay",
                "parameters": {
                    "times_s": times,
                    "observed_v_v": {"$result": ["decay", "decay_v_v"]},
                    "pulse_duration_s": 1.0,
                    "initial": [0.08, 0.4, 0.7],
                    "standard_deviation": 1e-4,
                },
            },
        ]
    }
    completed = run_core_workflow(json.dumps(plan), tmp_path)
    folder = Path(completed["folder"])
    summary = json.loads((folder / "workflow.json").read_text())
    inverse_step = next(step for step in summary["steps"] if step["id"] == "recover")
    loaded = load_core_job(folder / inverse_step["folder"])
    assert loaded["result"]["success"]
    np.testing.assert_allclose(
        loaded["result"]["parameters"], [0.12, 0.7, 0.5], rtol=1e-4
    )
    assert loaded["provenance"]["source_sha256"]

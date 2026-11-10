"""Waveform TEM, recorded gates/stacking and MNF numerical contracts."""

import numpy as np
import pytest

from terraworkbench_core.radiometric_spectra import mnf_denoise
from terraworkbench_core.transient_processing import (
    gate_recorded_transients,
    stack_transients,
)


def test_mnf_full_rank_reconstruction_and_whitened_noise():
    from scipy.linalg import eigvalsh

    rng = np.random.default_rng(42)
    a = rng.normal(size=(5, 5))
    noise = a @ a.T + 0.1 * np.eye(5)
    train = rng.normal(size=(50, 5)) * [1.0, 2, 4, 3, 10] + 20
    target = rng.normal(size=(12, 5)) + 8
    result = mnf_denoise(train, noise, 5, spectra=target)
    np.testing.assert_allclose(result["spectra"], target, atol=1e-12)
    forward = result["forward_matrix"]
    np.testing.assert_allclose(forward.T @ noise @ forward, np.eye(5), atol=1e-12)
    np.testing.assert_allclose(
        result["conditional_output_noise_covariance"], noise, atol=1e-12
    )
    expected = eigvalsh(np.cov(train, rowvar=False), noise)[::-1]
    np.testing.assert_allclose(result["total_noise_eigenvalues"], expected, atol=1e-12)


def test_mnf_heldout_noise_reduction_not_retrained_on_target():
    rng = np.random.default_rng(17)
    basis = np.array([1.0, 0.8, 0.7, 0.5, 0.2, 0.1])
    noise = np.diag([2.0, 3, 2, 4, 3, 4])
    truth_train = 100 + rng.normal(0, 15, 600)[:, None] * basis
    training = truth_train + rng.multivariate_normal(np.zeros(6), noise, 600)
    truth = 100 + rng.normal(0, 15, 200)[:, None] * basis
    observed = truth + rng.multivariate_normal(np.zeros(6), noise, 200)
    fit = mnf_denoise(training, noise, 1, spectra=observed)
    assert np.mean((fit["spectra"] - truth) ** 2) < 0.4 * np.mean(
        (observed - truth) ** 2
    )
    other = mnf_denoise(training, noise, 1, spectra=observed + 10)
    np.testing.assert_allclose(fit["training_mean"], other["training_mean"])
    np.testing.assert_allclose(fit["forward_matrix"], other["forward_matrix"])
    projection = fit["forward_matrix"] @ fit["inverse_matrix"]
    np.testing.assert_allclose(
        fit["conditional_output_noise_covariance"], projection.T @ noise @ projection
    )


def test_mnf_errors_and_no_silent_clipping():
    training = np.array([[-2.0, -3], [-1, -2], [0, -1], [1, 0]])
    assert mnf_denoise(training, np.eye(2), 2)["negative"].any()
    for covariance in (
        np.zeros((2, 2)),
        [[1.0, 2], [2, 1]],
        [[1.0, 0], [0, 1e-12]],
        [[1.0, 0], [0.1, 1]],
    ):
        with pytest.raises(ValueError):
            mnf_denoise(training, covariance, 1)
    with pytest.raises(ValueError, match="budget"):
        mnf_denoise(training, np.eye(2), 1, max_elements=1)
    with pytest.raises(ValueError):
        mnf_denoise(training, np.eye(2), True)


def test_stack_polarity_rejections_missing_data_and_zero():
    # Five repeats, final one explicitly rejected. Missing is NaN, not zero.
    values = np.array(
        [[1.0, 0, 3], [-2, 0, -4], [3, 0, np.nan], [-4, 0, -5], [100, 100, 100]]
    )
    result = stack_transients(
        values, [1, -1, 1, -1, 1], accepted=[True, True, True, True, False]
    )
    np.testing.assert_allclose(result["mean"], [2.5, 0, 4])
    np.testing.assert_array_equal(result["count"], [4, 4, 3])
    assert result["sample_std"][0] == pytest.approx(np.std([1, 2, 3, 4], ddof=1))
    assert result["standard_error"][0] == pytest.approx(
        np.std([1, 2, 3, 4], ddof=1) / 2
    )
    assert result["rejected_repeats"] == 1
    short = stack_transients(values[:2], [1, -1])
    assert np.isnan(short["mean"]).all()
    empty = stack_transients(values[:2], [1, -1], accepted=[False, False])
    np.testing.assert_array_equal(empty["count"], 0)
    with pytest.raises(ValueError):
        stack_transients(values, [0, 1, 1, 1, 1])


def test_recorded_gates_exact_linear_means_overlap_and_nan_support():
    times = np.array([0.0, 0.1, 0.3, 0.5, 1.0])
    values = 3 + 2 * times
    gates = np.array([[0.05, 0.4], [0.3, 1], [0, 0.1]])
    result = gate_recorded_transients(times, values, gates)
    np.testing.assert_allclose(result["gate_mean"], 3 + 2 * gates.mean(axis=1))
    np.testing.assert_allclose(result["sample_weights"].sum(axis=1), 1)
    batch = gate_recorded_transients(times, [values, -values], gates)
    np.testing.assert_allclose(
        batch["gate_mean"], [result["gate_mean"], -result["gate_mean"]]
    )
    missing = values.copy()
    missing[-1] = np.nan
    gated = gate_recorded_transients(times, missing, gates)["gate_mean"]
    assert np.isfinite(gated[[0, 2]]).all() and np.isnan(gated[1])
    with pytest.raises(ValueError, match="budget"):
        gate_recorded_transients(times, values, gates, max_weight_elements=1)
    with pytest.raises(ValueError):
        gate_recorded_transients(times, values, [[-0.1, 0.1]])


def test_gate_before_stack_retains_temporal_covariance_in_noise():
    # Each shot has perfectly correlated temporal noise. Averaging gates must
    # not pretend that two samples provide two independent observations.
    noise = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    traces = 10 + noise[:, None] * np.ones((1, 3))
    gates = gate_recorded_transients([0.0, 0.5, 1.0], traces, [[0.0, 1.0]])["gate_mean"]
    result = stack_transients(gates, np.ones(5))
    assert result["standard_error"][0] == pytest.approx(
        np.std(noise, ddof=1) / np.sqrt(5)
    )


def test_tem_ramp_matches_integrated_analytic_step_and_moment_scaling():
    pytest.importorskip("simpeg")
    from geoana.em.tdem import VerticalMagneticDipoleHalfSpace
    from scipy.constants import mu_0
    from terraworkbench_core.layered_em import tem_waveform_layered

    times = np.logspace(-4, -2, 8)
    ramp_width = 3e-4
    geometry = dict(source_m=[0.0, 0, 0], receiver_m=[10.0, 0, 0])
    predicted = tem_waveform_layered(
        times,
        [0.03],
        [],
        waveform_times_s=[-ramp_width, 0],
        relative_current=[1.0, 0],
        **geometry,
    )
    nodes, weights = np.polynomial.legendre.leggauss(20)
    sample_times = times[:, None] + ramp_width * (nodes + 1) / 2
    analytic = VerticalMagneticDipoleHalfSpace(
        sample_times.ravel(), sigma=0.03, location=[0.0, 0, 0]
    )
    samples = (
        analytic.magnetic_field_time_derivative(np.array([10.0, 0]))[:, 2].reshape(
            sample_times.shape
        )
        * mu_0
    )
    reference = samples @ weights / 2
    np.testing.assert_allclose(predicted["dbdt_t_s"], reference, rtol=0.02, atol=1e-14)
    scaled = tem_waveform_layered(
        times,
        [0.03],
        [],
        waveform_times_s=[-ramp_width, 0],
        relative_current=[-0.5, 0],
        moment_a_m2=2.0,
        **geometry,
    )
    np.testing.assert_allclose(
        scaled["dbdt_t_s"], -predicted["dbdt_t_s"], rtol=1e-12, atol=1e-20
    )


def test_tem_waveform_step_limit_finite_pulse_and_time_translation():
    pytest.importorskip("simpeg")
    from terraworkbench_core.layered_em import tem_stepoff_layered, tem_waveform_layered

    times = np.logspace(-4, -2, 7)
    geometry = dict(source_m=[0.0, 0, 0], receiver_m=[10.0, 0, 0])
    step = tem_stepoff_layered(times, [0.02], [], **geometry)["dbdt_t_s"]
    narrow = tem_waveform_layered(
        times,
        [0.02],
        [],
        waveform_times_s=[-1e-7, 0],
        relative_current=[1.0, 0],
        **geometry,
    )["dbdt_t_s"]
    np.testing.assert_allclose(narrow, step, rtol=0.005, atol=1e-14)
    ramp = 1e-4
    off = tem_waveform_layered(
        times,
        [0.02],
        [],
        waveform_times_s=[-ramp, 0],
        relative_current=[1.0, 0],
        **geometry,
    )["dbdt_t_s"]
    # Turn-on ramp is the negative of a time-shifted turn-off ramp.
    shifted = tem_waveform_layered(
        times + 0.001,
        [0.02],
        [],
        waveform_times_s=[-ramp, 0],
        relative_current=[1.0, 0],
        **geometry,
    )["dbdt_t_s"]
    pulse = tem_waveform_layered(
        times,
        [0.02],
        [],
        waveform_times_s=[-0.001 - ramp, -0.001, -ramp, 0],
        relative_current=[0.0, 1, 1, 0],
        **geometry,
    )["dbdt_t_s"]
    np.testing.assert_allclose(pulse, off - shifted, rtol=0.005, atol=1e-14)


def test_tem_gate_waveform_convergence_and_reject_bad_knots():
    pytest.importorskip("simpeg")
    from terraworkbench_core.layered_em import tem_gate_average, tem_waveform_layered

    kwargs = dict(
        source_m=[0.0, 0, 0],
        receiver_m=[10.0, 0, 0],
        waveform_times_s=[-0.0002, 0],
        relative_current=[1.0, 0],
    )
    gates = [[0.0001, 0.0003], [0.001, 0.002]]
    a = tem_gate_average(gates, [0.03], [], quadrature_order=6, **kwargs)
    b = tem_gate_average(gates, [0.03], [], quadrature_order=12, **kwargs)
    np.testing.assert_allclose(a["gate_dbdt_t_s"], b["gate_dbdt_t_s"], rtol=1e-4)
    for knots, current in (
        ([0.0, -0.001], [1.0, 0]),
        ([-0.001, 0], [1.0, 0.1]),
        ([-0.001, 0, 0], [1.0, 0.5, 0]),
        ([-0.001, 0], [2.0, 0]),
    ):
        with pytest.raises(ValueError):
            tem_waveform_layered(
                [0.001],
                [0.03],
                [],
                waveform_times_s=knots,
                relative_current=current,
                source_m=[0.0, 0, 0],
                receiver_m=[10.0, 0, 0],
            )


def test_tem_two_layer_point_recovery_cancel_and_budgets():
    pytest.importorskip("simpeg")
    from terraworkbench_core.layered_em import tem_stepoff_layered, fit_tem_conductivity

    times = np.logspace(-5, -2, 12)
    geometry = dict(source_m=[0.0, 0, 0], receiver_m=[10.0, 0, 0])
    observed = tem_stepoff_layered(times, [0.025, 0.2], [20.0], **geometry)["dbdt_t_s"]
    args = dict(
        times_s=times,
        data_std_t_s=abs(observed) * 0.02 + 1e-16,
        initial_conductivity_s_m=[0.02, 0.15],
        thicknesses_m=[20.0],
        **geometry,
    )
    fit = fit_tem_conductivity(observed, **args)
    assert fit["success"] and fit["locally_full_rank"]
    np.testing.assert_allclose(fit["conductivity_s_m"], [0.025, 0.2], rtol=1e-4)
    assert fit["forward_evaluations"] > fit["evaluations"]
    np.testing.assert_allclose(fit["predicted_dbdt_t_s"], observed, rtol=1e-5)
    assert not fit_tem_conductivity(observed, max_evaluations=1, **args)["success"]
    with pytest.raises(RuntimeError, match="budget"):
        fit_tem_conductivity(observed, max_forward_evaluations=1, **args)
    with pytest.raises(InterruptedError):
        fit_tem_conductivity(observed, cancel=lambda: True, **args)


def test_tem_gate_waveform_conductivity_recovery():
    pytest.importorskip("simpeg")
    from terraworkbench_core.layered_em import tem_gate_average, fit_tem_conductivity

    starts = np.logspace(-4, -2, 8)
    gates = np.column_stack([starts, starts * 1.2])
    geometry = dict(
        source_m=[0.0, 0, 0],
        receiver_m=[10.0, 0, 0],
        waveform_times_s=[-2e-4, 0],
        relative_current=[1.0, 0],
    )
    observed = tem_gate_average(gates, [0.03], [], **geometry)["gate_dbdt_t_s"]
    fit = fit_tem_conductivity(
        observed,
        gates_s=gates,
        data_std_t_s=abs(observed) * 0.02 + 1e-16,
        initial_conductivity_s_m=[0.02],
        thicknesses_m=[],
        **geometry,
    )
    assert fit["success"]
    assert fit["conductivity_s_m"][0] == pytest.approx(0.03, rel=1e-4)


def test_recorded_noisy_tem_to_gates_stack_and_conductivity_end_to_end():
    pytest.importorskip("simpeg")
    from terraworkbench_core.operations import run_operation

    times = np.logspace(-4, -2, 241)
    starts = np.logspace(-4, np.log10(0.008), 10)
    gates = np.column_stack([starts, starts * 1.15])
    geometry = dict(source_m=[0.0, 0, 0], receiver_m=[10.0, 0, 0])
    noiseless = run_operation(
        "tem.stepoff_forward",
        times_s=times,
        conductivity_s_m=[0.03],
        thicknesses_m=[],
        **geometry,
    )["result"]["dbdt_t_s"]
    rng = np.random.default_rng(127)
    polarities = np.tile([1.0, -1.0], 20)
    # Repeat-specific gain noise is fully correlated across time, intentionally.
    traces = polarities[:, None] * noiseless * (1 + rng.normal(0, 0.03, (40, 1)))
    recorded = run_operation(
        "tem.integrate_recorded_gates", times_s=times, transients=traces, gates_s=gates
    )
    stacked = run_operation(
        "tem.stack_transients",
        transients=recorded["result"]["gate_mean"],
        polarity=polarities,
    )
    fit = run_operation(
        "tem.fit_conductivity",
        observed_dbdt_t_s=stacked["result"]["mean"],
        data_std_t_s=stacked["result"]["standard_error"],
        initial_conductivity_s_m=[0.02],
        thicknesses_m=[],
        gates_s=gates,
        **geometry,
    )
    assert fit["result"]["success"]
    assert fit["result"]["conductivity_s_m"][0] == pytest.approx(0.03, rel=0.03)
    for step in (recorded, stacked, fit):
        assert step["provenance"]["status"] == "completed"
        assert len(step["provenance"]["input_sha256"]) == 64


def test_tem_sampling_and_input_contracts_before_backend_work():
    from terraworkbench_core.layered_em import fit_tem_conductivity

    base = dict(
        data_std_t_s=[0.1, 0.1], initial_conductivity_s_m=[0.01], thicknesses_m=[]
    )
    with pytest.raises(ValueError, match="exactly one"):
        fit_tem_conductivity([1.0, 2.0], **base)
    with pytest.raises(ValueError, match="exactly one"):
        fit_tem_conductivity(
            [1.0, 2.0], times_s=[0.1, 0.2], gates_s=[[0.1, 0.2], [0.2, 0.3]], **base
        )
    with pytest.raises(ValueError, match="count"):
        fit_tem_conductivity([1.0, 2.0], times_s=[0.1], **base)
    with pytest.raises(ValueError, match="Both waveform"):
        fit_tem_conductivity(
            [1.0, 2.0], times_s=[0.1, 0.2], waveform_times_s=[-0.1, 0], **base
        )


def test_missing_samples_are_supported_through_public_operation_catalog():
    import json
    from terraworkbench_core.operations import run_operation

    arguments = dict(
        transients=[[1.0, np.nan], [2.0, 2.0], [3.0, 4.0]],
        polarity=[1.0, 1.0, 1.0],
        minimum_stack=2,
    )
    direct = stack_transients(**arguments)
    wrapped = run_operation("tem.stack_transients", **arguments)
    np.testing.assert_allclose(wrapped["result"]["mean"], direct["mean"])
    np.testing.assert_allclose(wrapped["result"]["mean"], [2.0, 3.0])
    assert wrapped["provenance"]["input_hash_scheme"] == "typed-tree-sha256-v2"
    json.dumps(wrapped["provenance"], allow_nan=False)

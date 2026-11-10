"""Current-source Cole-Cole IP after a prescribed finite current history.

Piecewise-constant current, initially unpolarized before the first switch.
All observation times/gates follow the final switch to zero at t=0.
No transmitter ramps, receiver transfer function, induction or steady-periodic
prehistory is inferred. Spatial calculations use fixed static-IP sensitivity.
"""

import numpy as np

from ._array_contract import as_array
from .dispersive_ip import _fit, _parameters, _relaxation_response


def _history(event_times_s, current_a, times_s, gates_s):
    events, currents = (as_array(v, float) for v in (event_times_s, current_a))
    if (
        events.ndim != 1
        or not 2 <= events.size <= 128
        or currents.shape != events.shape
        or not np.isfinite(events).all()
        or not np.isfinite(currents).all()
        or events[-1] != 0
        or events[0] < -1e12
        or np.any(np.diff(events) <= 0)
        or currents[-1] != 0
        or currents[-2] == 0
    ):
        raise ValueError(
            "Require 2..128 increasing switch times ending at zero and matching "
            "finite currents after switches; final current is zero, penultimate nonzero"
        )
    reference = currents[-2]
    relative = currents / reference
    if not np.isfinite(relative).all() or np.max(np.abs(relative)) > 1e6:
        raise ValueError(
            "Final on-current is too small relative to waveform amplitudes"
        )
    increments = np.diff(np.r_[0.0, relative])
    if (times_s is None) == (gates_s is None):
        raise ValueError("Supply times_s OR gates_s")
    gate = gates_s is not None
    samples = as_array(gates_s if gate else times_s, float)
    if (gate and (samples.ndim != 2 or samples.shape[1] != 2)) or (
        not gate and samples.ndim != 1
    ):
        raise ValueError("Times must be a vector; gates must have shape (n,2)")
    if (
        not samples.shape[0]
        or not np.isfinite(samples).all()
        or np.any(samples < 0)
        or np.max(samples) - events[0] > 1e12
        or (gate and np.any(samples[:, 1] <= samples[:, 0]))
        or samples.shape[0] * events.size + events.size - 1 > 4096
    ):
        raise ValueError(
            "Nonnegative ordered gates/times required; shifted time <=1e12 s "
            "and at most 4096 switch/sample relaxation terms"
        )
    shifted = (
        samples[None, :, :] - events[:, None, None]
        if gate
        else samples[None, :] - events[:, None]
    )
    return {
        "events": events.copy(),
        "currents": currents.copy(),
        "reference_current_a": float(reference),
        "increments": increments,
        "shifted": shifted,
        "samples": samples.copy(),
        "gate": gate,
    }


def _kernel(history, tau, c, cancel):
    shifted = history["shifted"]
    gate = history["gate"]
    n_events = len(history["events"])
    n_samples = len(history["samples"])
    if gate:
        means = _relaxation_response(
            shifted.reshape(-1, 2), tau, c, True, None, cancel
        )[:-1].reshape(n_events, n_samples)
        charging = _relaxation_response(
            -history["events"][:-1], tau, c, False, None, cancel
        )[:-1]
    else:
        combined = np.r_[shifted.ravel(), -history["events"][:-1]]
        relaxed = _relaxation_response(combined, tau, c, False, None, cancel)[:-1]
        means = relaxed[: shifted.size].reshape(n_events, n_samples)
        charging = relaxed[shifted.size :]
    weights = history["increments"]
    # Current has returned to zero. The instantaneous DC term is absent.
    decay = -weights @ means
    primary_memory = weights[:-1] @ charging
    return decay, float(primary_memory)


def _predict(history, m, tau, c, normalization, cancel):
    if normalization not in ("dc", "pulse"):
        raise ValueError("Normalization must be dc or pulse")
    decay, memory = _kernel(history, tau, c, cancel)
    primary = 1.0 - m * memory
    denominator = 1.0 if normalization == "dc" else primary
    if abs(denominator) < 1e-8:
        raise ValueError("Final pre-switch primary voltage is too close to zero")
    return m * decay / denominator, primary


def _metadata(history, normalization):
    return {
        "event_times_s": history["events"],
        "current_a": history["currents"],
        "reference_current_a": history["reference_current_a"],
        "normalization": normalization,
        "units": "V/V",
        "prehistory": "zero current and unpolarized before first prescribed switch",
        "primary_reference": "signed final on-current; pulse uses voltage immediately before t=0",
        "waveform": "prescribed finite piecewise-constant current; observations after final switch-off",
    }


def ip_waveform_decay(
    event_times_s,
    current_a,
    *,
    times_s=None,
    gates_s=None,
    chargeability=0.1,
    tau_s=1.0,
    exponent=0.5,
    normalization="pulse",
    cancel=None,
):
    """Off-time secondary V/V for a finite signed current-switch history.

    event_times_s ends at 0; current_a is current immediately AFTER each switch.
    Current is zero before the first event and after the last event. Times/gates
    are relative to the final switch-off. Normalization dc uses rho0 times the
    final signed on-current; pulse uses the predicted final pre-switch primary.
    """
    m, tau, c = _parameters(chargeability, tau_s, exponent)
    history = _history(event_times_s, current_a, times_s, gates_s)
    values, primary = _predict(history, m, tau, c, normalization, cancel)
    return {
        **_metadata(history, normalization),
        "decay_v_v": values,
        "primary_to_dc_ratio": primary,
    }


def _bounds(initial, reference, lower, upper):
    start = as_array(initial, float)
    prior = start.copy() if reference is None else as_array(reference, float)
    if start.shape != (3,) or prior.shape != (3,):
        raise ValueError("Initial/reference must be [m,tau_rho,c]")
    _parameters(*start)
    _parameters(*prior)
    low, high = as_array(lower, float), as_array(upper, float)
    if (
        low.shape != (3,)
        or high.shape != (3,)
        or low[0] < 0
        or high[0] >= 1
        or low[1] < 1e-12
        or high[1] > 1e12
        or low[2] <= 0
        or high[2] > 1
    ):
        raise ValueError("Waveform-IP parameter bounds exceed physical domains")
    return start, prior, low, high


def fit_ip_waveform(
    event_times_s,
    current_a,
    observed_v_v,
    *,
    times_s=None,
    gates_s=None,
    initial,
    standard_deviation,
    reference=None,
    beta=0.0,
    normalization="pulse",
    lower=(0.0, 1e-9, 0.1),
    upper=(0.95, 1e9, 1.0),
    **solver_options,
):
    """Fit intrinsic m, resistivity tau and c using the complete current history.

    Observations and their errors are V/V with the selected primary convention.
    Only post-final-off observations are supported; no stacking is inferred.
    """
    history = _history(event_times_s, current_a, times_s, gates_s)
    obs = as_array(observed_v_v, float)
    if obs.shape != (len(history["samples"]),) or obs.size < 4:
        raise ValueError("At least four observations matching times/gates required")
    start, prior, low, high = _bounds(initial, reference, lower, upper)
    cancel = solver_options.get("cancel")
    result = _fit(
        lambda p: _predict(history, *p, normalization, cancel)[0],
        obs,
        start,
        prior,
        low,
        high,
        [1],
        standard_deviation=standard_deviation,
        beta=beta,
        **solver_options,
    )
    result.update(_metadata(history, normalization))
    result.update(
        zip(("chargeability_v_v", "tau_rho_s", "exponent"), result["parameters"])
    )
    return result


def _spatial(sensitivity, chargeability, tau_s, exponent):
    S = as_array(sensitivity, float)
    vectors = [as_array(v, float) for v in (chargeability, tau_s, exponent)]
    if (
        S.ndim != 2
        or not S.shape[0]
        or not 1 <= S.shape[1] <= 32
        or S.size > 2_000_000
        or not np.isfinite(S).all()
        or any(v.shape != (S.shape[1],) for v in vectors)
    ):
        raise ValueError(
            "Require finite sensitivity and parameter vectors for 1..32 zones"
        )
    for row in zip(*vectors):
        _parameters(*row)
    return S, vectors


def _spatial_predict(S, history, vectors, normalization, cancel):
    if normalization not in ("dc", "pulse"):
        raise ValueError("Normalization must be dc or pulse")
    if S.shape[0] * len(history["samples"]) > 100000:
        raise ValueError("Spatial waveform-IP output sample budget exceeded")
    responses, memories = [], []
    for m, tau, c in zip(*vectors):
        decay, memory = _kernel(history, tau, c, cancel)
        responses.append(m * decay)
        memories.append(m * memory)
    with np.errstate(over="ignore", invalid="ignore"):
        primary = 1.0 - S @ np.asarray(memories)
        secondary = S @ np.asarray(responses)
    if not np.isfinite(primary).all() or not np.isfinite(secondary).all():
        raise ValueError(
            "Spatial waveform-IP voltage overflow; check sensitivity and current scale"
        )
    denominator = np.ones(len(primary)) if normalization == "dc" else primary
    if np.any(abs(denominator) < 1e-8):
        raise ValueError("Final pre-switch primary voltage is too close to zero")
    with np.errstate(over="ignore", invalid="ignore"):
        prediction = secondary / denominator[:, None]
    if not np.isfinite(prediction).all():
        raise ValueError("Spatial waveform-IP normalized voltage overflow")
    return prediction, primary


def spatial_ip_waveform(
    sensitivity,
    event_times_s,
    current_a,
    chargeability,
    tau_s,
    exponent,
    *,
    times_s=None,
    gates_s=None,
    normalization="pulse",
    cancel=None,
):
    """Quasi-static zone IP after prescribed switches; fixed spatial sensitivity.

    Rows are ABMN, columns off-time samples/gates. Small-polarization linearized
    spatial model; not a coupled complex-conductivity/Maxwell PDE solver.
    """
    S, vectors = _spatial(sensitivity, chargeability, tau_s, exponent)
    history = _history(event_times_s, current_a, times_s, gates_s)
    values, primary = _spatial_predict(S, history, vectors, normalization, cancel)
    return {
        **_metadata(history, normalization),
        "decay_v_v": values,
        "primary_to_dc_ratio": primary,
        "approximation": "small-polarization static sensitivity; conductivity and geometry fixed",
    }


def fit_spatial_ip_waveform(
    sensitivity,
    event_times_s,
    current_a,
    observed_v_v,
    *,
    times_s=None,
    gates_s=None,
    initial,
    reference,
    standard_deviation,
    beta,
    normalization="pulse",
    lower=(0.0, 1e-9, 0.1),
    upper=(0.5, 1e9, 1.0),
    **solver_options,
):
    """Recover [m,tau_rho,c] per fixed zone from a finite current history."""
    start, prior = as_array(initial, float), as_array(reference, float)
    if start.ndim != 2 or start.shape[1:] != (3,) or prior.shape != start.shape:
        raise ValueError("Initial/reference must have shape (n_zones,3)")
    S, _ = _spatial(sensitivity, *start.T)
    _spatial(S, *prior.T)
    for row, ref in zip(start, prior):
        _, _, low, high = _bounds(row, ref, lower, upper)
    history = _history(event_times_s, current_a, times_s, gates_s)
    obs = as_array(observed_v_v, float)
    if obs.shape != (S.shape[0], len(history["samples"])) or obs.shape[1] < 4:
        raise ValueError("Observed shape must be (n_ABMN,n_samples) with >=4 samples")
    cancel = solver_options.get("cancel")
    result = _fit(
        lambda p: _spatial_predict(
            S, history, p.reshape(-1, 3).T, normalization, cancel
        )[0],
        obs,
        start.ravel(),
        prior.ravel(),
        np.tile(low, len(start)),
        np.tile(high, len(start)),
        np.arange(1, start.size, 3),
        standard_deviation=standard_deviation,
        beta=beta,
        **solver_options,
    )
    model = result["parameters"].reshape(-1, 3)
    result.update(_metadata(history, normalization))
    result.update(
        chargeability_v_v=model[:, 0],
        tau_rho_s=model[:, 1],
        exponent=model[:, 2],
        approximation="small-polarization static sensitivity; conductivity and geometry fixed",
    )
    return result

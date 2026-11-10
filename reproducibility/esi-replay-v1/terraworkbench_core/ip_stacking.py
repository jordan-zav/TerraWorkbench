"""Explicit off-period stacking for a finite ideal-switch IP current history.

The caller selects actual switch-off events, sample/gate delays, cycle weights
and the stacking convention. No waveform detection or instrument recipe is
inferred. Fixed sensitivity optionally maps prescribed zones to ABMN records.
"""

import numpy as np

from ._array_contract import as_array
from .dispersive_ip import _fit, _parameters
from .ip_waveform import _bounds, _history, _predict, _spatial, _spatial_predict


def _prepare(
    event_times_s, current_a, off_event_indices, times_s, gates_s, stack_weights
):
    full = _history(event_times_s, current_a, [0.0], None)
    events, currents = full["events"], full["currents"]
    indices = as_array(off_event_indices)
    if (
        indices.ndim != 1
        or not 1 <= indices.size <= 64
        or not np.issubdtype(indices.dtype, np.integer)
        or np.any(indices < 1)
        or np.any(indices >= len(events))
        or np.any(indices[1:] <= indices[:-1])
        or np.any(currents[indices] != 0)
        or np.any(currents[indices - 1] == 0)
    ):
        raise ValueError(
            "Select 1..64 unique increasing integer switch-off indices (zero-based)"
        )
    indices = indices.astype(np.int64)
    weights = (
        np.ones(len(indices))
        if stack_weights is None
        else as_array(stack_weights, float)
    )
    if (
        weights.shape != indices.shape
        or not np.isfinite(weights).all()
        or np.any(weights < 0)
        or not np.any(weights > 0)
    ):
        raise ValueError(
            "Stack weights must be finite nonnegative cycle weights with positive total"
        )
    weights = weights / np.max(weights)
    weights /= weights.sum()
    histories = []
    work = 0
    for index in indices:
        history = _history(
            events[: index + 1] - events[index], currents[: index + 1], times_s, gates_s
        )
        samples = history["samples"]
        next_on = np.flatnonzero(currents[index + 1 :] != 0)
        if next_on.size:
            duration = events[index + 1 + next_on[0]] - events[index]
            if np.max(samples) > duration or (
                not history["gate"] and np.max(samples) == duration
            ):
                raise ValueError(
                    "Every selected observation must remain inside its off-period"
                )
        work += len(history["events"]) * len(samples) + len(history["events"]) - 1
        if work > 4096:
            raise ValueError("Stack exceeds 4096 current-history relaxation terms")
        histories.append(history)
    return {
        "histories": histories,
        "indices": indices.copy(),
        "weights": weights,
        "events": events,
        "currents": currents,
        "reference_currents": np.array([h["reference_current_a"] for h in histories]),
    }


def _combine(secondary, primary, prepared, normalization, stack_mode):
    if normalization not in ("dc", "pulse"):
        raise ValueError("Normalization must be dc or pulse")
    if stack_mode not in ("mean_of_ratios", "ratio_of_sums"):
        raise ValueError("Choose mean_of_ratios or ratio_of_sums explicitly")
    weights = prepared["weights"]
    selected = weights > 0
    denominator = np.ones_like(primary) if normalization == "dc" else primary
    secondary, denominator = secondary[selected], denominator[selected]
    weights = weights[selected]
    if stack_mode == "mean_of_ratios":
        if np.any(abs(denominator) < 1e-8):
            raise ValueError(
                "Selected cycle primary is too close to zero for mean of ratios"
            )
        combined = np.tensordot(weights, secondary / denominator[..., None], axes=1)
    else:
        # Raw voltages are polarity aligned. Their magnitudes also scale with
        # the absolute cycle on-current. A common current scale cancels.
        amplitudes = abs(prepared["reference_currents"][selected])
        coefficients = weights * (amplitudes / amplitudes.max())
        coefficients /= coefficients.sum()
        stacked_primary = np.tensordot(coefficients, denominator, axes=1)
        if np.any(abs(stacked_primary) < 1e-8):
            raise ValueError("Stacked primary is too close to zero for ratio of sums")
        combined = (
            np.tensordot(coefficients, secondary, axes=1)
            / np.asarray(stacked_primary)[..., None]
        )
    if not np.isfinite(combined).all():
        raise ValueError("Stacked IP response is nonfinite; check voltage scales")
    return combined


def _forward(prepared, parameters, sensitivity, normalization, stack_mode, cancel):
    if normalization not in ("dc", "pulse") or stack_mode not in (
        "mean_of_ratios",
        "ratio_of_sums",
    ):
        raise ValueError(
            "Choose dc/pulse normalization and mean_of_ratios/ratio_of_sums stacking"
        )
    data_shape = (len(prepared["histories"][0]["samples"]),)
    if sensitivity is not None:
        data_shape = (sensitivity.shape[0],) + data_shape
    if np.prod(data_shape) * len(prepared["histories"]) > 100000:
        raise ValueError("Stacked IP cycle-output sample budget exceeded")
    secondary, primary = [], []
    for history in prepared["histories"]:
        if sensitivity is None:
            values, ratio = _predict(history, *parameters, "dc", cancel)
        else:
            values, ratio = _spatial_predict(
                sensitivity, history, parameters.T, "dc", cancel
            )
        secondary.append(values)
        primary.append(ratio)
    secondary, primary = np.asarray(secondary), np.asarray(primary)
    combined = _combine(secondary, primary, prepared, normalization, stack_mode)
    return combined, secondary, primary


def _metadata(prepared, normalization, stack_mode, sensitivity):
    return {
        "event_times_s": prepared["events"],
        "current_a": prepared["currents"],
        "off_event_indices": prepared["indices"],
        "stack_weights": prepared["weights"],
        "cycle_reference_current_a": prepared["reference_currents"],
        "normalization": normalization,
        "stack_mode": stack_mode,
        "units": "V/V",
        "prehistory": "zero current and unpolarized before the first prescribed switch",
        "polarity": "each cycle aligned by the sign of its preceding on-current",
        "approximation": "intrinsic Cole-Cole curve"
        if sensitivity is None
        else "small-polarization static sensitivity; conductivity and geometry fixed",
    }


def stack_ip_decay(
    event_times_s,
    current_a,
    off_event_indices,
    *,
    stack_mode,
    times_s=None,
    gates_s=None,
    stack_weights=None,
    normalization="pulse",
    chargeability=0.1,
    tau_s=1.0,
    exponent=0.5,
    sensitivity=None,
    cancel=None,
):
    """Predict a stack of explicitly selected zero-current off-periods.

    stack_mode is mandatory: mean_of_ratios averages per-cycle V/V curves;
    ratio_of_sums divides polarity-aligned weighted raw secondary and primary
    voltage sums (therefore accounts for absolute on-current amplitudes).
    Delays are relative to each selected switch-off; gates may not cross the
    next on-switch. Optional sensitivity requires one [m,tau,c] triple per zone.
    """
    if sensitivity is None:
        S, parameters = None, _parameters(chargeability, tau_s, exponent)
    else:
        S, vectors = _spatial(sensitivity, chargeability, tau_s, exponent)
        parameters = np.array(vectors).T
    prepared = _prepare(
        event_times_s, current_a, off_event_indices, times_s, gates_s, stack_weights
    )
    values, secondary, primary = _forward(
        prepared, parameters, S, normalization, stack_mode, cancel
    )
    return {
        **_metadata(prepared, normalization, stack_mode, S),
        "decay_v_v": values,
        "cycle_secondary_to_dc": secondary,
        "cycle_primary_to_dc_ratio": primary,
    }


def fit_ip_stack(
    event_times_s,
    current_a,
    off_event_indices,
    observed_v_v,
    *,
    stack_mode,
    times_s=None,
    gates_s=None,
    stack_weights=None,
    normalization="pulse",
    initial,
    standard_deviation,
    reference=None,
    beta=None,
    sensitivity=None,
    lower=(0.0, 1e-9, 0.1),
    upper=(0.5, 1e9, 1.0),
    **solver_options,
):
    """Fit intrinsic [m,tau_rho,c] to an explicitly specified stacked response.

    Observations/errors are already stacked V/V. No raw-voltage processing or
    automatic uncertainty reduction is inferred. With sensitivity, initial and
    reference are (n_zones,3), and reference must be supplied explicitly.
    """
    start = as_array(initial, float)
    if sensitivity is None:
        start, prior, low, high = _bounds(start, reference, lower, upper)
        S, shape, n_zones = None, start.shape, 1
        beta = 0.0 if beta is None else beta
    else:
        if (
            reference is None
            or beta is None
            or start.ndim != 2
            or start.shape[1:] != (3,)
        ):
            raise ValueError(
                "Spatial stacks need explicit (n_zones,3) initial/reference models and beta"
            )
        prior = as_array(reference, float)
        if prior.shape != start.shape:
            raise ValueError("Spatial stack initial/reference shapes must match")
        S, _ = _spatial(sensitivity, *start.T)
        _spatial(S, *prior.T)
        for row, ref in zip(start, prior):
            _, _, low, high = _bounds(row, ref, lower, upper)
        shape, n_zones = start.shape, len(start)
    prepared = _prepare(
        event_times_s, current_a, off_event_indices, times_s, gates_s, stack_weights
    )
    samples = len(prepared["histories"][0]["samples"])
    observed = as_array(observed_v_v, float)
    expected = (samples,) if S is None else (S.shape[0], samples)
    if samples < 4 or observed.shape != expected:
        raise ValueError(
            "Stack observations must match geometry and at least four samples/gates"
        )
    cancel = solver_options.get("cancel")
    result = _fit(
        lambda p: _forward(
            prepared, p.reshape(shape), S, normalization, stack_mode, cancel
        )[0],
        observed,
        start.ravel(),
        prior.ravel(),
        np.tile(low, n_zones),
        np.tile(high, n_zones),
        np.arange(1, start.size, 3),
        standard_deviation=standard_deviation,
        beta=beta,
        **solver_options,
    )
    result.update(_metadata(prepared, normalization, stack_mode, S))
    model = result["parameters"].reshape(shape)
    values = model if S is None else model.T
    result.update(zip(("chargeability_v_v", "tau_rho_s", "exponent"), values))
    return result

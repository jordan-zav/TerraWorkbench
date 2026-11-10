"""Recorded TEM waveform stacking and finite-gate averages, NumPy/SciPy.

Sample values retain their supplied physical units. These operations do not
infer transmitter current, instrument response, calibration or gate timing.
"""

import numpy as np
from scipy import sparse

from ._array_contract import as_array


def stack_transients(
    transients, polarity, *, accepted=None, minimum_stack=3, max_elements=5_000_000
):
    """Polarity-corrected mean, sample standard deviation and SEM per sample.

    Rows are independent repeat transients, columns are samples or gates.
    polarity is an explicit +/-1 per row. accepted is an optional boolean
    shot mask; no automatic outlier rejection. NaNs mark missing individual
    samples, zeros remain observations. Too few contributions yields NaN.
    SEM assumes independent repeats: it excludes correlated/telluric noise,
    instrumental bias, waveform uncertainty and timing jitter.
    """
    values, sign = as_array(transients, float), as_array(polarity, float)
    if (
        values.ndim != 2
        or not min(values.shape)
        or values.size > max_elements
        or sign.shape != (values.shape[0],)
        or np.isinf(values).any()
        or not np.isfinite(sign).all()
        or np.any((sign != 1) & (sign != -1))
    ):
        raise ValueError(
            "Bounded (repeat,sample) data and explicit +/-1 polarities required"
        )
    if (
        isinstance(minimum_stack, bool)
        or not isinstance(minimum_stack, (int, np.integer))
        or minimum_stack < 2
    ):
        raise ValueError("minimum_stack must be an integer of at least two")
    keep = np.ones(len(values), dtype=bool) if accepted is None else as_array(accepted)
    if keep.shape != (len(values),) or keep.dtype.kind != "b":
        raise ValueError("accepted must be a boolean mask per repeat")
    corrected = values[keep] * sign[keep, None]
    finite = np.isfinite(corrected)
    counts = finite.sum(axis=0)
    total = np.where(finite, corrected, 0.0).sum(axis=0)
    mean = np.divide(total, counts, out=np.zeros(values.shape[1]), where=counts > 0)
    differences = np.where(finite, corrected - mean, 0.0)
    variance = np.divide(
        np.sum(differences**2, axis=0),
        counts - 1,
        out=np.full(mean.shape, np.nan),
        where=counts > 1,
    )
    enough = counts >= minimum_stack
    sem = np.sqrt(
        np.divide(variance, counts, out=np.full(mean.shape, np.nan), where=counts > 0)
    )
    return {
        "mean": np.where(enough, mean, np.nan),
        "sample_std": np.where(enough, np.sqrt(variance), np.nan),
        "standard_error": np.where(enough, sem, np.nan),
        "count": counts,
        "valid": enough,
        "accepted_repeats": int(keep.sum()),
        "rejected_repeats": int((~keep).sum()),
        "minimum_stack": int(minimum_stack),
        "noise_assumption": "independent repeat transients",
    }


def gate_recorded_transients(
    times_s, transients, gates_s, *, max_weight_elements=2_000_000
):
    """Exact boxcar means of piecewise-linearly interpolated recorded samples.

    Time is the last axis. Gates are contained in the sampled interval, with
    explicit edges in seconds. No extrapolation or center-sample approximation.
    NaN in a sample contributing to a gate propagates to that gate; it is not
    filled with zero. Gate each repeat BEFORE stacking to retain within-shot
    temporal correlation in empirical gate noise. The returned sparse weight
    operator also supports external covariance propagation W*C*W.T.
    """
    times, values, gates = [as_array(a, float) for a in (times_s, transients, gates_s)]
    if (
        times.ndim != 1
        or times.size < 2
        or not np.isfinite(times).all()
        or np.any(np.diff(times) <= 0)
        or values.ndim not in (1, 2)
        or values.shape[-1] != len(times)
        or np.isinf(values).any()
    ):
        raise ValueError(
            "Finite increasing times and matching 1D/2D samples required; missing samples may be NaN"
        )
    if (
        gates.ndim != 2
        or gates.shape[1] != 2
        or not 1 <= len(gates) <= 128
        or not np.isfinite(gates).all()
        or np.any(gates[:, 0] < times[0])
        or np.any(gates[:, 1] > times[-1])
        or np.any(gates[:, 1] <= gates[:, 0])
    ):
        raise ValueError(
            "Require 1..128 nonempty gates contained within sample support"
        )
    rows, columns, weights = [], [], []
    for row, (start, end) in enumerate(gates):
        first = max(0, np.searchsorted(times, start, side="right") - 1)
        stop = min(len(times) - 1, np.searchsorted(times, end, side="left"))
        if len(weights) + 2 * (stop - first) > max_weight_elements:
            raise ValueError("Recorded-gate sparse weight budget exceeded")
        for i in range(first, stop):
            low, high = max(start, times[i]), min(end, times[i + 1])
            if high <= low:
                continue
            width = times[i + 1] - times[i]
            right = ((high - times[i]) ** 2 - (low - times[i]) ** 2) / (2 * width)
            left = high - low - right
            for column, weight in ((i, left), (i + 1, right)):
                if weight > 0:
                    rows.append(row)
                    columns.append(column)
                    weights.append(weight / (end - start))
    operator = sparse.csr_matrix(
        (weights, (rows, columns)), shape=(len(gates), len(times))
    )
    result = (operator @ values.T).T
    return {
        "gate_mean": result,
        "gates_s": gates.copy(),
        "sample_weights": operator,
        "integration": "exact piecewise-linear boxcar mean",
        "units": "same as input samples",
    }

"""Independent edge-plane FFT preparations and supported-grid derivatives.

Legacy biharmonic fill and Burg axis prediction are explicit alternatives.
Neither uses the Geosoft runtime. Retained residuals and masks are preserved.
"""

import math
import numpy as np
from scipy.ndimage import binary_erosion, distance_transform_edt


def oasis_observed_fft_size(n):
    # Matches installed Expand_PGU sizes in the tested 15..512 range.
    sizes = sorted(
        {
            2**a * 3**b * 5**c * 7**d
            for a in range(5)
            for b in range(3)
            for c in range(2)
            for d in range(2)
        }
    )
    target = max(n + 2, math.ceil(n * 1.2))
    allowed = [size for size in sizes if size >= target and size % 2 == 0]
    if not allowed:
        raise ValueError(
            "Expansion exceeds audited FFT dimensions; use an explicit shape."
        )
    return allowed[0]


def prepare_independent(data, expanded_shape=None, max_unknown=250000):
    try:
        from skimage.restoration import inpaint_biharmonic
    except ImportError as exc:
        raise ImportError(
            "Biharmonic preparation requires scikit-image; install or select another preparation explicitly."
        ) from exc
    data = np.asarray(data, dtype=float)
    if data.ndim != 2:
        raise ValueError("Two-dimensional grid required")
    valid = np.isfinite(data)
    if valid.sum() < 3:
        raise ValueError("At least three finite cells required")
    yy, xx = np.indices(data.shape)
    edge = valid & ~binary_erosion(valid)
    design = np.stack((np.ones(data.shape), xx, yy), axis=-1)
    coefficients = np.linalg.lstsq(design[edge], data[edge], rcond=None)[0]
    residual = data - design @ coefficients
    if np.max(np.abs(residual[valid])) <= 32 * np.finfo(float).eps * max(
        1.0, np.max(np.abs(data[valid]))
    ):
        residual[valid] = 0.0
    if expanded_shape is None:
        expanded_shape = tuple(oasis_observed_fft_size(n) for n in data.shape)
    before = tuple((new - old) // 2 for new, old in zip(expanded_shape, data.shape))
    after = tuple(
        new - old - pad for new, old, pad in zip(expanded_shape, data.shape, before)
    )
    if min(before + after) < 1:
        raise ValueError("Expansion requires at least one surrounding cell")
    crop = tuple(slice(p, p + n) for p, n in zip(before, data.shape))
    known = np.zeros(expanded_shape, bool)
    known[crop] = valid
    work = np.zeros(expanded_shape)
    work[crop] = np.nan_to_num(residual)
    # Match fixed zero continuation at outer frame, then smooth missing region.
    known[[0, -1], :] = True
    known[:, [0, -1]] = True
    if (~known).sum() > max_unknown:
        raise ValueError("Biharmonic fill exceeds audited unknown-cell budget")
    work = inpaint_biharmonic(work, ~known, split_into_regions=True)
    original_known = np.zeros(expanded_shape, bool)
    original_known[crop] = valid
    # Documented vendor default: twice the smallest dummy edge dimension.
    roll_distance = 2 * min(before + after)
    distances = distance_transform_edt(~original_known)
    work *= np.clip(1 - distances / roll_distance, 0, 1)
    return (
        work,
        crop,
        {
            "trend": "OLS plane on four-connected valid boundary",
            "coefficients_cells": coefficients.tolist(),
            "expansion_shape": list(expanded_shape),
            "padding_before": list(before),
            "padding_after": list(after),
            "fill": "biharmonic interpolation with zero exterior frame",
            "rolloff": "linear to zero",
            "rolloff_distance_cells": roll_distance,
            "rolloff_rule": "twice smallest padded margin",
            "oasis_rolloff_default_cells": 2 * min(before + after),
            "unknown_cells": int((~known).sum()),
            "oasis_maximum_entropy_reproduced": False,
        },
    )


def _burg_predict(samples, count, filter_length):
    """Stable Burg AR fit on at most twice the requested filter length."""
    samples = np.asarray(samples[-2 * filter_length :], dtype=float)
    if not len(samples):
        raise ValueError("Prediction requires observed samples")
    scale = float(np.max(np.abs(samples)))
    if not scale:
        return np.zeros(count)
    if len(samples) < 3:
        return np.full(count, samples[-1])
    normalized = samples / scale
    forward = normalized[1:].copy()
    backward = normalized[:-1].copy()
    coefficients = np.array([1.0])
    for order in range(1, min(filter_length, len(samples) // 2) + 1):
        denominator = np.dot(forward, forward) + np.dot(backward, backward)
        if denominator < 1e-24:
            break
        reflection = np.clip(
            -2 * np.dot(backward, forward) / denominator, -0.9999, 0.9999
        )
        updated = np.zeros(order + 1)
        updated[:order] = coefficients
        updated[1:] += reflection * coefficients[::-1]
        coefficients = updated
        old = forward
        forward = (forward + reflection * backward)[1:]
        backward = (backward + reflection * old)[:-1]
    history = list(normalized)
    result = []
    for _ in range(count):
        value = -np.dot(coefficients[1:], history[-1 : -len(coefficients) : -1])
        if not np.isfinite(value):
            value = history[-1]
        history.append(value)
        result.append(value * scale)
    return np.asarray(result)


def _predict_axis(values, known, axis, filter_length):
    work = values.T if axis == 0 else values
    retained = known.T if axis == 0 else known
    out = np.full_like(work, np.nan)
    distance = np.full_like(work, np.inf)
    for row in range(len(work)):
        indices = np.flatnonzero(retained[row])
        if not len(indices):
            continue
        segments = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
        for segment in segments:
            start = int(segment[0])
            stop = int(segment[-1]) + 1
            previous = indices[indices < start]
            following = indices[indices >= stop]
            left = int(previous[-1]) + 1 if len(previous) else 0
            right = int(following[0]) if len(following) else work.shape[1]
            samples = work[row, segment]
            for targets, sequence in [
                (np.arange(stop, right), samples),
                (np.arange(start - 1, left - 1, -1), samples[::-1]),
            ]:
                if not len(targets):
                    continue
                prediction = _burg_predict(sequence, len(targets), filter_length)
                distances = np.arange(1, len(targets) + 1)
                use = distances < distance[row, targets]
                out[row, targets[use]] = prediction[use]
                distance[row, targets[use]] = distances[use]
    return (out.T, distance.T) if axis == 0 else (out, distance)


def prepare_prediction(data, expanded_shape=None, max_unknown=250000):
    """Remove the edge plane and predict missing values along both axes.

    The documented FFT-preparation defaults determine model length and rolloff.
    Burg fitting is independent Python, with distance-weighted axis predictions.
    It never calls Geosoft or changes retained measurements.
    """
    data = np.asarray(data, dtype=float)
    if data.ndim != 2 or np.isinf(data).any():
        raise ValueError("Finite or NaN 2D grid required")
    valid = np.isfinite(data)
    if valid.sum() < 3:
        raise ValueError("At least three finite cells required")
    yy, xx = np.indices(data.shape)
    edge = valid & ~binary_erosion(valid)
    design = np.stack((np.ones(data.shape), xx, yy), axis=-1)
    coefficients = np.linalg.lstsq(design[edge], data[edge], rcond=None)[0]
    residual = data - design @ coefficients
    if np.max(np.abs(residual[valid])) <= 32 * np.finfo(float).eps * max(
        1.0, np.max(np.abs(data[valid]))
    ):
        residual[valid] = 0.0
    if expanded_shape is None:
        expanded_shape = tuple(oasis_observed_fft_size(n) for n in data.shape)
    before = tuple((new - old) // 2 for new, old in zip(expanded_shape, data.shape))
    after = tuple(
        new - old - pad for new, old, pad in zip(expanded_shape, data.shape, before)
    )
    if len(expanded_shape) != 2 or min(before + after) < 1:
        raise ValueError("Expansion requires at least one surrounding cell")
    crop = tuple(slice(p, p + n) for p, n in zip(before, data.shape))
    known = np.zeros(expanded_shape, bool)
    known[crop] = valid
    if (~known).sum() > max_unknown:
        raise ValueError("Prediction fill exceeds audited unknown-cell budget")
    work = np.zeros(expanded_shape)
    work[crop] = np.nan_to_num(residual)
    length = min(min(before + after), 32)
    p0, d0 = _predict_axis(work, known, 0, length)
    p1, d1 = _predict_axis(work, known, 1, length)
    w0 = np.where(np.isfinite(p0), 1 / d0, 0)
    w1 = np.where(np.isfinite(p1), 1 / d1, 0)
    total = w0 + w1
    prediction = np.divide(
        np.nan_to_num(p0) * w0 + np.nan_to_num(p1) * w1,
        total,
        out=np.zeros_like(work),
        where=total > 0,
    )
    distance, nearest = distance_transform_edt(~known, return_indices=True)
    fallback = (~known) & (total == 0)
    prediction[fallback] = work[tuple(nearest)][fallback]
    work = np.where(known, work, prediction)
    roll_distance = 2 * min(before + after)
    work *= np.clip(1 - distance / roll_distance, 0, 1)
    if not np.isfinite(work).all():
        raise ValueError("Nonfinite predicted FFT workspace")
    return (
        work,
        crop,
        {
            "trend": "OLS plane on four-connected valid boundary",
            "coefficients_cells": coefficients.tolist(),
            "expansion_shape": list(expanded_shape),
            "padding_before": list(before),
            "padding_after": list(after),
            "fill": "independent Burg autoregressive axis prediction, inverse-distance combination",
            "prediction_filter_length": length,
            "prediction_sample_limit": 2 * length,
            "reflection_limit": 0.9999,
            "fallback": "nearest retained residual where neither axis has observations",
            "fallback_cells": int(fallback.sum()),
            "rolloff": "linear to zero",
            "rolloff_distance_cells": roll_distance,
            "rolloff_rule": "twice smallest padded margin",
            "unknown_cells": int((~known).sum()),
            "oasis_maximum_entropy_reproduced": False,
            "method_revision": "edge-plane-burg-1",
        },
    )


def central_valid(a, axis, spacing):
    padded = np.pad(
        a,
        [(1, 1) if i == axis else (0, 0) for i in range(a.ndim)],
        constant_values=np.nan,
    )
    minus = [slice(None)] * a.ndim
    plus = minus.copy()
    minus[axis] = slice(None, -2)
    plus[axis] = slice(2, None)
    left = padded[tuple(minus)]
    right = padded[tuple(plus)]
    both = np.isfinite(left) & np.isfinite(right)
    out = np.where(
        both,
        (right - left) / (2 * spacing),
        np.where(
            np.isfinite(right),
            (right - a) / spacing,
            np.where(np.isfinite(left), (a - left) / spacing, 0.0),
        ),
    )
    return np.where(np.isfinite(a), out, np.nan)


def composite_derivatives(
    values, spacing, vertical_positive="down", preparation="edge_plane_biharmonic"
):
    """Central horizontal derivatives and independently prepared FFT verticals.

    No Geosoft imports or process calls. Preparation selects legacy biharmonic
    filling or independent Burg prediction; neither claims exact vendor parity.
    """
    from .spectral import frequency_grid, apply_transfer

    if vertical_positive not in ("down", "up"):
        raise ValueError("Invalid vertical convention.")
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or min(values.shape) < 2:
        raise ValueError("Two cells per axis required.")
    missing = ~np.isfinite(values)
    dx = central_valid(values, 1, spacing[1])
    dy = central_valid(values, 0, spacing[0])
    if preparation not in ("edge_plane_biharmonic", "edge_plane_prediction"):
        raise ValueError("Unknown composite preparation")
    prepare = (
        prepare_prediction
        if preparation == "edge_plane_prediction"
        else prepare_independent
    )
    work, crop, metadata = prepare(values)
    _, _, radial = frequency_grid(work.shape, *spacing)
    dz = apply_transfer(work, radial if vertical_positive == "down" else -radial)[crop]
    dz2 = apply_transfer(work, radial**2)[crop]
    for array in (dx, dy, dz, dz2):
        array[missing] = np.nan
    metadata.update(
        horizontal_derivatives="central differences where both neighbors valid; one-sided with one valid neighbor; zero if isolated",
        vertical_positive=vertical_positive,
    )
    return dx, dy, dz, dz2, metadata

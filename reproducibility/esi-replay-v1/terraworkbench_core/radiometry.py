"""Shared numerical core for gamma-ray spectrometry processing.

The functions in this module are QGIS-independent so their equations and edge
cases can be tested without a desktop session. Inputs are assumed to be
co-registered arrays. Calibration-dependent operations deliberately require
their coefficients instead of hiding survey-specific constants.
"""

from __future__ import annotations

import numpy as np


DEFAULT_DOSE_COEFFICIENTS = (13.078, 5.675, 2.494)


def live_time_correction(count_rate, live_time_ms, sample_interval_ms=1000.):
    """Correct interval-normalized cps using measured live time (milliseconds).

    Not a dead-time model. Missing/zero/over-interval live times produce NaN.
    Do not apply to rates already normalized to live time.
    """
    if not np.isfinite(sample_interval_ms) or sample_interval_ms <= 0:
        raise ValueError("Sample interval must be positive and finite.")
    rate, live = np.broadcast_arrays(np.asarray(count_rate, dtype=float),
                                     np.asarray(live_time_ms, dtype=float))
    if np.isinf(rate).any() or np.any(rate < 0):
        raise ValueError("Raw rates must be nonnegative, finite or NaN.")
    valid = np.isfinite(rate) & np.isfinite(live) & (live > 0) & (live <= sample_interval_ms)
    result = np.full(rate.shape, np.nan)
    np.divide(rate * sample_interval_ms, live, out=result, where=valid)
    if np.isinf(result).any():
        raise ValueError("Live-time correction overflow.")
    return result


def accumulated_profile_ratios(k, u, th, profile, *, thresholds,
                               minimum_potassium, max_radius, canceled=None):
    """Ratios of accumulated concentrations in contiguous profile segments.

    Grow centered windows until ALL K/U/Th sums reach explicit thresholds.
    max_radius means samples per side; edges use available neighbors. Invalid,
    negative or low-K samples break segments. No sorting or gap interpolation.
    Callers must additionally split profile IDs at acquisition time gaps.
    This declared policy is not certified proprietary-processing equivalence.
    """
    data = np.asarray([k, u, th], dtype=float)
    groups = np.asarray(profile)
    limits = np.asarray(thresholds, dtype=float)
    if data.ndim != 2 or data.shape[0] != 3 or groups.shape != (data.shape[1],):
        raise ValueError("Three aligned 1D channels and profile IDs are required.")
    if limits.shape != (3,) or not np.isfinite(limits).all() or np.any(limits <= 0):
        raise ValueError("Three positive finite K/U/Th thresholds are required.")
    if not np.isfinite(minimum_potassium) or minimum_potassium < 0:
        raise ValueError("Minimum potassium must be nonnegative and finite.")
    if type(max_radius) is not int or not 0 <= max_radius <= 1000:
        raise ValueError("Radius must be an integer from 0 to 1000.")
    if any(v is None or (isinstance(v, (float, np.floating)) and not np.isfinite(v)) for v in groups):
        raise ValueError("Profile IDs must not be missing.")
    n = data.shape[1]
    ratios = np.full((3, n), np.nan)
    used = np.zeros(n, dtype=np.int32)
    valid = np.isfinite(data).all(axis=0) & (data >= 0).all(axis=0) & (data[0] >= minimum_potassium)
    if n:
        breaks = (groups[1:] != groups[:-1]) | ~valid[1:] | ~valid[:-1]
        bounds = np.r_[0, np.flatnonzero(breaks) + 1, n]
        for start, stop in zip(bounds[:-1], bounds[1:]):
            if canceled and canceled():
                raise InterruptedError("Radiometric ratios canceled.")
            if not valid[start]:
                continue
            prefix = np.pad(np.cumsum(data[:, start:stop], axis=1), ((0, 0), (1, 0)))
            pending = np.arange(stop - start)
            for radius in range(max_radius + 1):
                if canceled and canceled():
                    raise InterruptedError("Radiometric ratios canceled.")
                left = np.maximum(0, pending - radius)
                right = np.minimum(stop - start, pending + radius + 1)
                sums = prefix[:, right] - prefix[:, left]
                reached = (sums >= limits[:, None]).all(axis=0)
                selected = pending[reached] + start
                sk, su, st = sums[:, reached]
                ratios[:, selected] = np.array([su / st, su / sk, st / sk])
                used[selected] = (right - left)[reached]
                pending = pending[~reached]
                if not pending.size:
                    break
    recipe = {"operation": "accumulated_profile_ratios", "version": 1,
              "thresholds_k_u_th": limits.tolist(), "minimum_potassium": float(minimum_potassium),
              "max_radius_per_side": max_radius, "threshold_policy": "all_three",
              "edge_policy": "available_neighbors", "invalid_policy": "split_segment",
              "units": ["K percent", "eU ppm", "eTh ppm"], "numpy": np.__version__,
              "valid_outputs": int((used > 0).sum()), "rows": n}
    return {"u_th": ratios[0], "u_k": ratios[1], "th_k": ratios[2], "sample_count": used}, recipe


def safe_ratio(numerator, denominator, minimum_denominator=0.0):
    """Divide arrays, returning NaN where values are invalid or unstable."""
    numerator = np.asarray(numerator, dtype=np.float64)
    denominator = np.asarray(denominator, dtype=np.float64)
    valid = (
        np.isfinite(numerator)
        & np.isfinite(denominator)
        & (np.abs(denominator) > float(minimum_denominator))
    )
    result = np.full(np.broadcast_shapes(numerator.shape, denominator.shape), np.nan)
    np.divide(numerator, denominator, out=result, where=valid)
    return result


def terrestrial_dose_rate(
    potassium_percent,
    equivalent_uranium_ppm,
    equivalent_thorium_ppm,
    coefficients=DEFAULT_DOSE_COEFFICIENTS,
):
    """Return terrestrial absorbed dose rate in nGy/h from calibrated grids."""
    k, u, th = np.broadcast_arrays(
        np.asarray(potassium_percent, dtype=np.float64),
        np.asarray(equivalent_uranium_ppm, dtype=np.float64),
        np.asarray(equivalent_thorium_ppm, dtype=np.float64),
    )
    ck, cu, cth = (float(value) for value in coefficients)
    return ck * k + cu * u + cth * th


def alteration_f_parameter(
    potassium_percent, equivalent_uranium_ppm, equivalent_thorium_ppm, minimum_thorium=0.0
):
    """Compute the interpretive F parameter K*eU/eTh."""
    return safe_ratio(
        np.asarray(potassium_percent, dtype=np.float64)
        * np.asarray(equivalent_uranium_ppm, dtype=np.float64),
        equivalent_thorium_ppm,
        minimum_thorium,
    )


def robust_stretch(values, lower_percentile=2.0, upper_percentile=98.0):
    """Scale finite values to [0, 1] using configurable percentile clipping."""
    values = np.asarray(values, dtype=np.float64)
    result = np.full(values.shape, np.nan)
    finite = np.isfinite(values)
    if not finite.any():
        return result
    lower, upper = np.nanpercentile(
        values[finite], [float(lower_percentile), float(upper_percentile)]
    )
    if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
        result[finite] = 0.0
        return result
    result[finite] = np.clip((values[finite] - lower) / (upper - lower), 0.0, 1.0)
    return result


def ternary_rgb(
    potassium_percent,
    equivalent_uranium_ppm,
    equivalent_thorium_ppm,
    lower_percentile=2.0,
    upper_percentile=98.0,
    normalize=False,
):
    """Create K-red, eTh-green, eU-blue radiometric RGB bands."""
    red = robust_stretch(potassium_percent, lower_percentile, upper_percentile)
    green = robust_stretch(equivalent_thorium_ppm, lower_percentile, upper_percentile)
    blue = robust_stretch(equivalent_uranium_ppm, lower_percentile, upper_percentile)
    channels = np.stack((red, green, blue))
    if normalize:
        total = np.nansum(channels, axis=0)
        valid = np.all(np.isfinite(channels), axis=0) & (total > 0.0)
        normalized = np.full_like(channels, np.nan)
        np.divide(channels, total, out=normalized, where=valid[None, ...])
        channels = normalized
    return np.clip(np.rint(channels * 255.0), 0.0, 255.0)


def dead_time_correction(count_rate, dead_time_seconds):
    """Apply the non-paralyzable detector dead-time correction."""
    observed = np.asarray(count_rate, dtype=np.float64)
    denominator = 1.0 - float(dead_time_seconds) * observed
    if np.any(np.isfinite(observed) & (denominator <= 0.0)):
        raise ValueError("dead time and count rate produce a non-positive denominator")
    return observed / denominator


def background_correction(count_rate, aircraft=0.0, cosmic=0.0, radon=0.0):
    """Subtract explicitly supplied aircraft, cosmic and atmospheric backgrounds."""
    from ._array_contract import as_array

    observed, instrument, space, atmosphere = np.broadcast_arrays(
        *[as_array(v, float) for v in (count_rate, aircraft, cosmic, radon)]
    )
    if any(np.isinf(v).any() for v in (observed, instrument, space, atmosphere)):
        raise ValueError("Background channels must be finite or explicit NaN")
    return observed - instrument - space - atmosphere


def height_attenuation_correction(
    count_rate, survey_height, reference_height, attenuation_coefficient
):
    """Normalize count rate to a reference clearance using exponential attenuation."""
    count_rate, survey_height = np.broadcast_arrays(
        np.asarray(count_rate, dtype=np.float64),
        np.asarray(survey_height, dtype=np.float64),
    )
    return count_rate * np.exp(
        float(attenuation_coefficient)
        * (survey_height - float(reference_height))
    )


def sensitivity_calibration(corrected_count_rate, sensitivity, offset=0.0):
    """Convert corrected count rate to concentration with survey calibration."""
    sensitivity = float(sensitivity)
    if not np.isfinite(sensitivity) or sensitivity <= 0.0:
        raise ValueError("sensitivity must be positive")
    return (np.asarray(corrected_count_rate, dtype=np.float64) - float(offset)) / sensitivity


def spectral_unmix(observed_k, observed_u, observed_th, cross_talk):
    """Solve a user-supplied 3x3 window-response system for true channel rates."""
    matrix = np.asarray(cross_talk, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("window response matrix must be finite and 3x3")
    if np.linalg.cond(matrix) > 1e10:
        raise ValueError("window response matrix is singular or ill-conditioned")
    k, u, th = np.broadcast_arrays(
        np.asarray(observed_k, dtype=np.float64),
        np.asarray(observed_u, dtype=np.float64),
        np.asarray(observed_th, dtype=np.float64),
    )
    flat = np.stack((k.ravel(), u.ravel(), th.ravel()))
    result = np.full_like(flat, np.nan)
    valid = np.all(np.isfinite(flat), axis=0)
    result[:, valid] = np.linalg.solve(matrix, flat[:, valid])
    return result.reshape((3,) + k.shape)


def channel_qc(values, expected_minimum=0.0):
    """Return JSON-serializable quality indicators for one radiometric channel."""
    values = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(values)
    finite_values = values[finite]
    result = {
        "cells": int(values.size),
        "finite_cells": int(finite.sum()),
        "missing_cells": int((~finite).sum()),
        "negative_cells": int(np.sum(finite_values < float(expected_minimum))),
    }
    if finite_values.size:
        result.update(
            minimum=float(np.min(finite_values)),
            maximum=float(np.max(finite_values)),
            mean=float(np.mean(finite_values)),
            standard_deviation=float(np.std(finite_values)),
            p02=float(np.percentile(finite_values, 2.0)),
            median=float(np.median(finite_values)),
            p98=float(np.percentile(finite_values, 98.0)),
        )
    return result


def median_mad_despike(values, radius=1, threshold=5.0):
    """Replace isolated local outliers using a median/MAD decision rule."""
    from scipy.ndimage import median_filter

    values = np.asarray(values, dtype=np.float64)
    radius = int(radius)
    threshold = float(threshold)
    if radius < 1:
        raise ValueError("despike radius must be at least one cell")
    if threshold <= 0.0:
        raise ValueError("despike threshold must be positive")
    finite = np.isfinite(values)
    if not finite.any():
        return values.copy(), np.zeros(values.shape, dtype=bool)
    filled = values.copy()
    filled[~finite] = float(np.nanmedian(values))
    size = 2 * radius + 1
    local_median = median_filter(filled, size=size, mode="reflect")
    deviation = np.abs(filled - local_median)
    local_mad = median_filter(deviation, size=size, mode="reflect")
    robust_scale = 1.4826 * local_mad
    positive_scale = robust_scale[finite & (robust_scale > 0.0)]
    fallback = float(np.median(positive_scale)) if positive_scale.size else 0.0
    numerical_floor = np.finfo(np.float64).eps * np.maximum(np.abs(local_median), 1.0)
    effective_scale = np.where(
        robust_scale > 0.0,
        robust_scale,
        max(fallback, 0.0) + numerical_floor,
    )
    spikes = finite & (deviation > threshold * effective_scale)
    result = values.copy()
    result[spikes] = local_median[spikes]
    return result, spikes

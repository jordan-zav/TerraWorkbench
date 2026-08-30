"""Numerical core for gamma-ray spectrometry processing.

The functions in this module are QGIS-independent so their equations and edge
cases can be tested without a desktop session. Inputs are assumed to be
co-registered arrays. Calibration-dependent operations deliberately require
their coefficients instead of hiding survey-specific constants.
"""

from __future__ import annotations

import numpy as np


DEFAULT_DOSE_COEFFICIENTS = (13.078, 5.675, 2.494)


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
        np.divide(channels, total, out=normalized, where=valid[None, :, :])
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
    return np.asarray(count_rate, dtype=np.float64) - (
        float(aircraft) + float(cosmic) + float(radon)
    )


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

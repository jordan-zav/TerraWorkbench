"""Numerical corrections for ordered moving-platform geophysical surveys."""

from __future__ import annotations

import numpy as np


EARTH_ANGULAR_SPEED = 7.2921150e-5  # rad/s
MEAN_EARTH_RADIUS = 6_371_008.8  # m


def interpolate_base_variation(survey_time, base_time, base_value, reference=None):
    """Interpolate base-station variation at survey times without extrapolation."""
    survey_time = np.asarray(survey_time, dtype=np.float64)
    base_time = np.asarray(base_time, dtype=np.float64)
    base_value = np.asarray(base_value, dtype=np.float64)
    valid = np.isfinite(base_time) & np.isfinite(base_value)
    base_time = base_time[valid]
    base_value = base_value[valid]
    if base_time.size < 2:
        raise ValueError("at least two finite base-station observations are required")
    order = np.argsort(base_time)
    base_time = base_time[order]
    base_value = base_value[order]
    unique_time, inverse = np.unique(base_time, return_inverse=True)
    if unique_time.size != base_time.size:
        totals = np.bincount(inverse, weights=base_value)
        counts = np.bincount(inverse)
        base_value = totals / counts
        base_time = unique_time
    if reference is None:
        reference = float(np.median(base_value))
    variation = np.full(survey_time.shape, np.nan)
    inside = (
        np.isfinite(survey_time)
        & (survey_time >= base_time[0])
        & (survey_time <= base_time[-1])
    )
    variation[inside] = np.interp(survey_time[inside], base_time, base_value) - float(reference)
    return variation


def lag_shift(time, values, lag_seconds):
    """Sample an ordered channel at ``time + signed lag`` without extrapolation."""
    time = np.asarray(time, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    result = np.full(values.shape, np.nan)
    valid = np.isfinite(time) & np.isfinite(values)
    if valid.sum() < 2:
        return result
    valid_indices = np.flatnonzero(valid)
    order = np.argsort(time[valid])
    t = time[valid][order]
    v = values[valid][order]
    query = t + float(lag_seconds)
    inside = (query >= t[0]) & (query <= t[-1])
    shifted = np.full(t.shape, np.nan)
    shifted[inside] = np.interp(query[inside], t, v)
    result[valid_indices[order]] = shifted
    return result


def hampel_filter_1d(values, radius=3, threshold=4.5):
    """Replace isolated samples using a sliding median and normalized MAD."""
    values = np.asarray(values, dtype=np.float64)
    radius = int(radius)
    if radius < 1 or float(threshold) <= 0.0:
        raise ValueError("Hampel radius and threshold must be positive")
    result = values.copy()
    replaced = np.zeros(values.shape, dtype=bool)
    for index, value in enumerate(values):
        if not np.isfinite(value):
            continue
        start = max(0, index - radius)
        stop = min(values.size, index + radius + 1)
        window = values[start:stop]
        window = window[np.isfinite(window)]
        if window.size < 3:
            continue
        median = float(np.median(window))
        scale = 1.4826 * float(np.median(np.abs(window - median)))
        floor = np.finfo(float).eps * max(abs(median), 1.0)
        if abs(value - median) > float(threshold) * max(scale, floor):
            result[index] = median
            replaced[index] = True
    return result, replaced


def heading_correction(azimuth_degrees, cosine_coefficient=0.0, sine_coefficient=0.0):
    """Return a first-harmonic heading correction in channel units."""
    azimuth = np.deg2rad(np.asarray(azimuth_degrees, dtype=np.float64))
    return float(cosine_coefficient) * np.cos(azimuth) + float(sine_coefficient) * np.sin(azimuth)


def segment_velocity(easting, northing, time_seconds):
    """Estimate centered east/north velocity components from an ordered line."""
    easting = np.asarray(easting, dtype=np.float64)
    northing = np.asarray(northing, dtype=np.float64)
    time_seconds = np.asarray(time_seconds, dtype=np.float64)
    if not (easting.shape == northing.shape == time_seconds.shape):
        raise ValueError("coordinate and time arrays must have the same shape")
    if easting.size < 2:
        return np.full(easting.shape, np.nan), np.full(easting.shape, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        east_velocity = np.gradient(easting) / np.gradient(time_seconds)
        north_velocity = np.gradient(northing) / np.gradient(time_seconds)
    invalid = ~np.isfinite(east_velocity) | ~np.isfinite(north_velocity)
    east_velocity[invalid] = np.nan
    north_velocity[invalid] = np.nan
    return east_velocity, north_velocity


def azimuth_from_velocity(east_velocity, north_velocity):
    """Return degrees clockwise from geographic/grid north."""
    return np.mod(
        np.rad2deg(
            np.arctan2(
                np.asarray(east_velocity, dtype=np.float64),
                np.asarray(north_velocity, dtype=np.float64),
            )
        ),
        360.0,
    )


def eotvos_correction(
    latitude_degrees,
    east_velocity,
    north_velocity,
    earth_radius=MEAN_EARTH_RADIUS,
):
    """Return the moving-platform Eötvös acceleration in mGal.

    Positive east velocity produces the conventional positive correction term.
    A caller must choose whether its meter/reduction convention adds or subtracts it.
    """
    latitude, east, north = np.broadcast_arrays(
        np.asarray(latitude_degrees, dtype=np.float64),
        np.asarray(east_velocity, dtype=np.float64),
        np.asarray(north_velocity, dtype=np.float64),
    )
    coriolis = 2.0 * EARTH_ANGULAR_SPEED * east * np.cos(np.deg2rad(latitude))
    centrifugal = (east**2 + north**2) / float(earth_radius)
    return (coriolis + centrifugal) * 1e5


def linear_drift(time_seconds, rate_per_hour, reference_time=None):
    """Return linear instrument drift in field units from a stated rate."""
    time_seconds = np.asarray(time_seconds, dtype=np.float64)
    finite = time_seconds[np.isfinite(time_seconds)]
    if reference_time is None:
        reference_time = float(finite.min()) if finite.size else 0.0
    return float(rate_per_hour) * (time_seconds - float(reference_time)) / 3600.0

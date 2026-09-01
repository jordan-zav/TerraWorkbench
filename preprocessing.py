"""Numerical helpers for survey preprocessing and quality control."""

from __future__ import annotations

import numpy as np


QC_INVALID = 1
QC_TIME_GAP = 2
QC_SPACING = 4
QC_SPEED = 8
QC_TURN = 16
QC_CLEARANCE = 32
QC_VALUE_RATE = 64

BASE_INVALID = 1
BASE_TIME_GAP = 2
BASE_SPIKE = 4
BASE_RATE = 8
BASE_DRIFT = 16


def unwrap_time_seconds(values, period=86400.0):
    """Unwrap a numeric time-of-day sequence across one or more rollovers."""
    time = np.asarray(values, dtype=np.float64)
    if time.ndim != 1:
        raise ValueError("time must be one-dimensional")
    result = time.copy()
    offset = 0.0
    previous = np.nan
    for index, value in enumerate(time):
        if not np.isfinite(value):
            continue
        candidate = value + offset
        if np.isfinite(previous) and candidate < previous - period / 2.0:
            offset += period
            candidate = value + offset
        result[index] = candidate
        previous = candidate
    return result


def _pearson(first, second):
    valid = np.isfinite(first) & np.isfinite(second)
    if np.count_nonzero(valid) < 3:
        return np.nan, int(np.count_nonzero(valid))
    x = np.asarray(first[valid], dtype=float)
    y = np.asarray(second[valid], dtype=float)
    x -= np.mean(x)
    y -= np.mean(y)
    denominator = np.sqrt(np.sum(x * x) * np.sum(y * y))
    if denominator <= 0.0:
        return np.nan, int(x.size)
    return float(np.sum(x * y) / denominator), int(x.size)


def estimate_time_lag(
    response_time,
    response_values,
    reference_time,
    reference_values,
    *,
    maximum_lag,
    lag_step,
    use_derivative=False,
):
    """Estimate response delay by correlation against an interpolated reference.

    Positive lag means the response channel occurs late and its timestamps should
    be shifted earlier by the returned number of seconds.
    """
    response_time = np.asarray(response_time, dtype=np.float64)
    response = np.asarray(response_values, dtype=np.float64)
    reference_time = np.asarray(reference_time, dtype=np.float64)
    reference = np.asarray(reference_values, dtype=np.float64)
    if response_time.shape != response.shape or reference_time.shape != reference.shape:
        raise ValueError("each time array must match its value array")
    if maximum_lag < 0.0 or lag_step <= 0.0:
        raise ValueError("maximum_lag and lag_step must define a positive search")
    response_order = np.argsort(response_time)
    reference_order = np.argsort(reference_time)
    response_time, response = response_time[response_order], response[response_order]
    reference_time, reference = reference_time[reference_order], reference[reference_order]
    valid_reference = np.isfinite(reference_time) & np.isfinite(reference)
    reference_time, reference = reference_time[valid_reference], reference[valid_reference]
    if reference_time.size < 3 or np.any(np.diff(reference_time) <= 0.0):
        raise ValueError("reference time must contain at least three unique ordered samples")
    lags = np.arange(-maximum_lag, maximum_lag + lag_step * 0.5, lag_step)
    correlations = np.full(lags.size, np.nan, dtype=float)
    counts = np.zeros(lags.size, dtype=int)
    for index, lag in enumerate(lags):
        # A delayed response recorded at t corresponds to the reference at t-lag.
        sample_time = response_time - lag
        inside = (
            np.isfinite(sample_time)
            & np.isfinite(response)
            & (sample_time >= reference_time[0])
            & (sample_time <= reference_time[-1])
        )
        interpolated = np.full(response.size, np.nan, dtype=float)
        interpolated[inside] = np.interp(sample_time[inside], reference_time, reference)
        comparison = response.copy()
        if use_derivative:
            comparison = np.gradient(comparison, response_time)
            interpolated = np.gradient(interpolated, response_time)
        correlations[index], counts[index] = _pearson(comparison, interpolated)
    if not np.any(np.isfinite(correlations)):
        raise ValueError("no lag candidate has at least three overlapping finite samples")
    best = int(np.nanargmax(np.abs(correlations)))
    return {
        "lag": float(lags[best]),
        "correlation": float(correlations[best]),
        "overlap": int(counts[best]),
        "lags": lags,
        "correlations": correlations,
        "counts": counts,
    }


def base_station_quality(
    time_seconds,
    values,
    *,
    maximum_time_gap=0.0,
    spike_window=5,
    spike_sigma=0.0,
    maximum_rate=0.0,
    maximum_drift_rate=0.0,
):
    """Return transparent base-station QC metrics and bit flags."""
    time = np.asarray(time_seconds, dtype=np.float64)
    channel = np.asarray(values, dtype=np.float64)
    if time.shape != channel.shape or time.ndim != 1:
        raise ValueError("time and values must be matching one-dimensional arrays")
    size = time.size
    interval = np.full(size, np.nan)
    rate = np.full(size, np.nan)
    if size > 1:
        interval[1:] = np.diff(time)
        valid = np.isfinite(interval[1:]) & (interval[1:] > 0.0)
        rate[1:] = np.divide(
            np.abs(np.diff(channel)), interval[1:], out=np.full(size - 1, np.nan), where=valid
        )
    window = max(1, int(spike_window))
    local_median = np.full(size, np.nan)
    local_sigma = np.full(size, np.nan)
    for index in range(size):
        start, stop = max(0, index - window), min(size, index + window + 1)
        neighborhood = channel[start:stop]
        neighborhood = neighborhood[np.isfinite(neighborhood)]
        if neighborhood.size:
            median = float(np.median(neighborhood))
            local_median[index] = median
            local_sigma[index] = 1.4826 * float(np.median(np.abs(neighborhood - median)))
    residual = channel - local_median
    finite = np.isfinite(time) & np.isfinite(channel)
    drift_rate = np.nan
    if np.count_nonzero(finite) >= 2:
        centered_time = time[finite] - np.mean(time[finite])
        denominator = float(np.sum(centered_time**2))
        if denominator > 0.0:
            drift_rate = float(
                np.sum(centered_time * (channel[finite] - np.mean(channel[finite])))
                / denominator
            )
    flags = np.zeros(size, dtype=np.int64)
    flags[~finite] |= BASE_INVALID
    invalid_step = (np.arange(size) > 0) & (
        (~np.isfinite(interval)) | (interval <= 0.0)
    )
    flags[invalid_step] |= BASE_INVALID
    if maximum_time_gap > 0.0:
        flags[np.isfinite(interval) & (interval > maximum_time_gap)] |= BASE_TIME_GAP
    if spike_sigma > 0.0:
        scale = local_sigma.copy()
        global_scale = 1.4826 * np.nanmedian(np.abs(channel - np.nanmedian(channel)))
        scale[(~np.isfinite(scale)) | (scale <= 0.0)] = global_scale
        flags[np.isfinite(residual) & (scale > 0.0) & (np.abs(residual) > spike_sigma * scale)] |= BASE_SPIKE
    if maximum_rate > 0.0:
        flags[np.isfinite(rate) & (rate > maximum_rate)] |= BASE_RATE
    if maximum_drift_rate > 0.0 and np.isfinite(drift_rate) and abs(drift_rate) > maximum_drift_rate:
        flags[finite] |= BASE_DRIFT
    return {
        "interval": interval,
        "rate": rate,
        "local_median": local_median,
        "residual": residual,
        "drift_rate": drift_rate,
        "flags": flags,
    }


def line_spacing_quality(line_centers, line_azimuths, expected_spacing=0.0, tolerance=0.25):
    """Measure cross-line spacing from line centers and axial azimuths."""
    centers = np.asarray(line_centers, dtype=np.float64)
    azimuths = np.asarray(line_azimuths, dtype=np.float64)
    if centers.ndim != 2 or centers.shape[1] != 2 or centers.shape[0] != azimuths.size:
        raise ValueError("line centers must be N x 2 and match azimuths")
    valid_azimuth = np.isfinite(azimuths)
    if np.count_nonzero(valid_azimuth) == 0:
        raise ValueError("at least one finite line azimuth is required")
    doubled = np.deg2rad(2.0 * azimuths[valid_azimuth])
    survey_azimuth = 0.5 * np.rad2deg(
        np.arctan2(np.mean(np.sin(doubled)), np.mean(np.cos(doubled)))
    ) % 180.0
    normal = np.array([np.cos(np.deg2rad(survey_azimuth)), -np.sin(np.deg2rad(survey_azimuth))])
    offsets = centers @ normal
    order = np.argsort(offsets)
    spacing = np.full(offsets.size, np.nan)
    if offsets.size > 1:
        spacing[order[1:]] = np.diff(offsets[order])
    finite_spacing = spacing[np.isfinite(spacing) & (spacing > 0.0)]
    nominal = float(expected_spacing) if expected_spacing > 0.0 else (
        float(np.median(finite_spacing)) if finite_spacing.size else np.nan
    )
    flags = np.zeros(offsets.size, dtype=bool)
    if np.isfinite(nominal) and nominal > 0.0:
        flags[np.isfinite(spacing)] = np.abs(spacing[np.isfinite(spacing)] - nominal) > tolerance * nominal
    return {
        "survey_azimuth": float(survey_azimuth),
        "offset": offsets,
        "spacing": spacing,
        "nominal": nominal,
        "flag": flags,
        "order": order,
    }


def magnetic_elements(east, north, up):
    """Return total field, horizontal field, declination and down-positive inclination."""
    east, north, up = np.broadcast_arrays(
        np.asarray(east, dtype=np.float64),
        np.asarray(north, dtype=np.float64),
        np.asarray(up, dtype=np.float64),
    )
    horizontal = np.hypot(east, north)
    total = np.sqrt(east**2 + north**2 + up**2)
    declination = np.rad2deg(np.arctan2(east, north))
    inclination = np.rad2deg(np.arctan2(-up, horizontal))
    return total, horizontal, declination, inclination


def angular_difference(first, second):
    """Return the smallest signed angular difference in degrees."""
    first, second = np.broadcast_arrays(
        np.asarray(first, dtype=np.float64), np.asarray(second, dtype=np.float64)
    )
    return (first - second + 180.0) % 360.0 - 180.0


def flight_line_metrics(easting, northing, time_seconds, values=None, clearance=None):
    """Calculate ordered per-sample navigation and channel-change metrics."""
    east = np.asarray(easting, dtype=np.float64)
    north = np.asarray(northing, dtype=np.float64)
    time = np.asarray(time_seconds, dtype=np.float64)
    if not (east.shape == north.shape == time.shape):
        raise ValueError("coordinates and time must have the same shape")
    size = time.size
    interval = np.full(size, np.nan, dtype=np.float64)
    spacing = np.full(size, np.nan, dtype=np.float64)
    speed = np.full(size, np.nan, dtype=np.float64)
    azimuth = np.full(size, np.nan, dtype=np.float64)
    turn = np.full(size, np.nan, dtype=np.float64)
    value_rate = np.full(size, np.nan, dtype=np.float64)
    if size > 1:
        interval[1:] = np.diff(time)
        delta_east = np.diff(east)
        delta_north = np.diff(north)
        spacing[1:] = np.hypot(delta_east, delta_north)
        valid_step = np.isfinite(interval[1:]) & (interval[1:] > 0.0)
        speed[1:] = np.divide(
            spacing[1:],
            interval[1:],
            out=np.full(size - 1, np.nan),
            where=valid_step,
        )
        azimuth[1:] = np.mod(np.rad2deg(np.arctan2(delta_east, delta_north)), 360.0)
        if size > 2:
            turn[2:] = np.abs(angular_difference(azimuth[2:], azimuth[1:-1]))
        if values is not None:
            channel = np.asarray(values, dtype=np.float64)
            if channel.shape != time.shape:
                raise ValueError("values and time must have the same shape")
            value_rate[1:] = np.divide(
                np.abs(np.diff(channel)),
                interval[1:],
                out=np.full(size - 1, np.nan),
                where=valid_step,
            )
    if clearance is None:
        clearance_values = np.full(size, np.nan, dtype=np.float64)
    else:
        clearance_values = np.asarray(clearance, dtype=np.float64)
        if clearance_values.shape != time.shape:
            raise ValueError("clearance and time must have the same shape")
    return {
        "interval": interval,
        "spacing": spacing,
        "speed": speed,
        "azimuth": azimuth,
        "turn": turn,
        "value_rate": value_rate,
        "clearance": clearance_values,
    }


def flight_quality_flags(
    metrics,
    *,
    maximum_time_gap=0.0,
    maximum_spacing=0.0,
    minimum_speed=0.0,
    maximum_speed=0.0,
    maximum_turn=0.0,
    minimum_clearance=0.0,
    maximum_clearance=0.0,
    maximum_value_rate=0.0,
):
    """Encode configurable QC failures in a stable integer bit mask."""
    size = np.asarray(metrics["interval"]).size
    flags = np.zeros(size, dtype=np.int64)
    interval = np.asarray(metrics["interval"], dtype=float)
    spacing = np.asarray(metrics["spacing"], dtype=float)
    speed = np.asarray(metrics["speed"], dtype=float)
    turn = np.asarray(metrics["turn"], dtype=float)
    clearance = np.asarray(metrics["clearance"], dtype=float)
    value_rate = np.asarray(metrics["value_rate"], dtype=float)

    invalid_step = np.arange(size) > 0
    invalid_step &= (~np.isfinite(interval)) | (interval <= 0.0)
    flags[invalid_step] |= QC_INVALID
    if maximum_time_gap > 0.0:
        flags[np.isfinite(interval) & (interval > maximum_time_gap)] |= QC_TIME_GAP
    if maximum_spacing > 0.0:
        flags[np.isfinite(spacing) & (spacing > maximum_spacing)] |= QC_SPACING
    if minimum_speed > 0.0:
        flags[np.isfinite(speed) & (speed < minimum_speed)] |= QC_SPEED
    if maximum_speed > 0.0:
        flags[np.isfinite(speed) & (speed > maximum_speed)] |= QC_SPEED
    if maximum_turn > 0.0:
        flags[np.isfinite(turn) & (turn > maximum_turn)] |= QC_TURN
    if minimum_clearance != 0.0:
        flags[np.isfinite(clearance) & (clearance < minimum_clearance)] |= QC_CLEARANCE
    if maximum_clearance > 0.0:
        flags[np.isfinite(clearance) & (clearance > maximum_clearance)] |= QC_CLEARANCE
    if maximum_value_rate > 0.0:
        flags[np.isfinite(value_rate) & (value_rate > maximum_value_rate)] |= QC_VALUE_RATE
    return flags

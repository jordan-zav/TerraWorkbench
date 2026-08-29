"""Numerical helpers for two-dimensional Fourier-domain raster filters."""

from __future__ import annotations

import numpy as np


def _trend_surface(values, order):
    """Fit no trend (-1), a mean (0), or a least-squares plane (1)."""
    values = np.asarray(values, dtype=np.float64)
    order = int(order)
    if order == -1:
        return np.zeros_like(values)
    if order == 0:
        return np.full_like(values, float(np.mean(values)))
    if order != 1:
        raise ValueError("FFT detrend order must be -1, 0, or 1")
    rows, columns = values.shape
    y, x = np.meshgrid(
        np.linspace(-1.0, 1.0, rows),
        np.linspace(-1.0, 1.0, columns),
        indexing="ij",
    )
    design = np.column_stack((np.ones(values.size), x.ravel(), y.ravel()))
    coefficients = np.linalg.lstsq(design, values.ravel(), rcond=None)[0]
    return (design @ coefficients).reshape(values.shape)


def _padding_window(shape, pad_rows, pad_columns, taper_percent):
    """Return an edge taper that leaves the original unpadded footprint intact."""
    rows, columns = shape
    window_y = np.ones(rows, dtype=np.float64)
    window_x = np.ones(columns, dtype=np.float64)
    taper_percent = float(taper_percent)
    if taper_percent < 0.0 or taper_percent > 100.0:
        raise ValueError("FFT taper percent must be between 0 and 100")

    for window, padding in ((window_y, pad_rows), (window_x, pad_columns)):
        taper = min(padding, int(round(padding * taper_percent / 100.0)))
        if taper > 0:
            ramp = np.sin(np.linspace(0.0, 0.5 * np.pi, taper + 1))[:-1]
            window[:taper] = ramp
            window[-taper:] = ramp[::-1]
    return np.outer(window_y, window_x)


def prepare_fft_grid(
    values,
    detrend_order=1,
    padding_percent=25.0,
    taper_percent=100.0,
):
    """Detrend, reflect-pad, and taper a grid for geophysical 2D FFT filtering.

    Returns the prepared grid and a state dictionary consumed by
    :func:`finish_fft_grid`.
    """
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or min(values.shape) < 2:
        raise ValueError("FFT filtering requires a two-dimensional grid")
    padding_percent = float(padding_percent)
    if padding_percent < 0.0 or padding_percent > 100.0:
        raise ValueError("FFT padding percent must be between 0 and 100")
    trend = _trend_surface(values, detrend_order)
    residual = values - trend
    pad_rows = int(round(values.shape[0] * padding_percent / 100.0))
    pad_columns = int(round(values.shape[1] * padding_percent / 100.0))
    padding = ((pad_rows, pad_rows), (pad_columns, pad_columns))
    prepared = np.pad(residual, padding, mode="reflect") if any(padding[0] + padding[1]) else residual.copy()
    if pad_rows or pad_columns:
        prepared *= _padding_window(
            prepared.shape, pad_rows, pad_columns, taper_percent
        )
    state = {
        "trend": trend,
        "row_slice": slice(pad_rows, pad_rows + values.shape[0]),
        "column_slice": slice(pad_columns, pad_columns + values.shape[1]),
    }
    return prepared, state


def finish_fft_grid(filtered, state, restore_trend=True):
    """Crop an FFT result to the original footprint and optionally restore trend."""
    result = np.asarray(filtered, dtype=np.float64)[
        state["row_slice"], state["column_slice"]
    ]
    if restore_trend:
        result = result + state["trend"]
    return result


def frequency_grid(shape, spacing_northing, spacing_easting):
    """Return east, north and radial angular wavenumbers in radians/unit."""
    rows, columns = shape
    east = 2.0 * np.pi * np.fft.fftfreq(columns, d=abs(float(spacing_easting)))
    north = 2.0 * np.pi * np.fft.fftfreq(rows, d=abs(float(spacing_northing)))
    k_east, k_north = np.meshgrid(east, north)
    return k_east, k_north, np.hypot(k_east, k_north)


def apply_transfer(values, transfer):
    """Apply a real-valued or complex Fourier transfer function."""
    transformed = np.fft.fft2(np.asarray(values, dtype=np.float64))
    return apply_spectrum(transformed, transfer)


def apply_spectrum(transformed, transfer):
    """Apply a transfer function to an existing 2D Fourier spectrum."""
    result = np.fft.ifft2(np.asarray(transformed) * transfer)
    return np.real_if_close(result, tol=1000).real.astype(np.float64)


def cutoff_wavenumber(wavelength):
    """Convert wavelength in ground units to angular wavenumber."""
    wavelength = float(wavelength)
    if wavelength <= 0:
        raise ValueError("Wavelength must be greater than zero")
    return 2.0 * np.pi / wavelength


def butterworth_lowpass(radial, wavelength, order):
    cutoff = cutoff_wavenumber(wavelength)
    order = int(order)
    if order < 1:
        raise ValueError("Butterworth order must be at least one")
    return 1.0 / np.sqrt(1.0 + (radial / cutoff) ** (2 * order))


def butterworth_highpass(radial, wavelength, order):
    cutoff = cutoff_wavenumber(wavelength)
    order = int(order)
    if order < 1:
        raise ValueError("Butterworth order must be at least one")
    response = np.zeros_like(radial)
    nonzero = radial > 0
    response[nonzero] = 1.0 / np.sqrt(1.0 + (cutoff / radial[nonzero]) ** (2 * order))
    return response


def butterworth_bandpass(radial, long_wavelength, short_wavelength, order):
    _validate_wavelength_band(long_wavelength, short_wavelength)
    return butterworth_highpass(radial, long_wavelength, order) * butterworth_lowpass(
        radial, short_wavelength, order
    )


def ideal_bandpass(radial, long_wavelength, short_wavelength):
    _validate_wavelength_band(long_wavelength, short_wavelength)
    low = cutoff_wavenumber(long_wavelength)
    high = cutoff_wavenumber(short_wavelength)
    return ((radial >= low) & (radial <= high)).astype(np.float64)


def cosine_rolloff_lowpass(radial, long_wavelength, short_wavelength, degree):
    """Smoothly roll from one to zero between two wavelength cutoffs."""
    _validate_wavelength_band(long_wavelength, short_wavelength)
    degree = int(degree)
    if degree < 1:
        raise ValueError("Cosine degree must be at least one")
    start = cutoff_wavenumber(long_wavelength)
    end = cutoff_wavenumber(short_wavelength)
    response = np.ones_like(radial)
    response[radial >= end] = 0.0
    transition = (radial > start) & (radial < end)
    phase = 0.5 * np.pi * (radial[transition] - start) / (end - start)
    response[transition] = np.cos(phase) ** degree
    return response


def directional_cosine(k_east, k_north, azimuth, degree):
    """Pass structures oriented along a clockwise-from-north azimuth."""
    degree = int(degree)
    if degree < 1:
        raise ValueError("Directional cosine degree must be at least one")
    strike = np.deg2rad(float(azimuth) % 180.0)
    wave_azimuth = np.arctan2(k_east, k_north)
    normal = strike + 0.5 * np.pi
    response = np.abs(np.cos(wave_azimuth - normal)) ** degree
    response[(k_east == 0.0) & (k_north == 0.0)] = 1.0
    return response


def stabilized_downward_continuation(
    radial, height, lowpass_wavelength, order, max_gain
):
    """Return downward continuation limited by a Butterworth taper and gain cap."""
    height = float(height)
    max_gain = float(max_gain)
    if height <= 0 or max_gain <= 1:
        raise ValueError("Height must be positive and maximum gain must exceed one")
    exponent = np.minimum(radial * height, np.log(max_gain))
    continuation = np.exp(exponent)
    return continuation * butterworth_lowpass(radial, lowpass_wavelength, order)


def integration_transfer(component, radial):
    """Return a stable zero-mean integration operator for one derivative component."""
    response = np.zeros(component.shape, dtype=np.complex128)
    nonzero = np.abs(component) > np.finfo(float).eps
    response[nonzero] = 1.0 / (1j * component[nonzero])
    response[radial == 0.0] = 0.0
    return response


def vertical_integration_transfer(radial):
    response = np.zeros_like(radial)
    nonzero = radial > 0.0
    response[nonzero] = 1.0 / radial[nonzero]
    return response


def magnetic_direction_factor(k_east, k_north, radial, inclination, declination):
    """Return the frequency-domain directional factor for a magnetic vector."""
    inclination = np.deg2rad(float(inclination))
    declination = np.deg2rad(float(declination))
    east = np.sin(declination) * np.cos(inclination)
    north = np.cos(declination) * np.cos(inclination)
    down = np.sin(inclination)
    factor = np.full(radial.shape, complex(down), dtype=np.complex128)
    nonzero = radial > 0.0
    factor[nonzero] += (
        1j * (east * k_east[nonzero] + north * k_north[nonzero]) / radial[nonzero]
    )
    return factor


def magnetic_field_transform(
    k_east,
    k_north,
    radial,
    source_inclination,
    source_declination,
    target_inclination,
    target_declination,
    magnetization_inclination=None,
    magnetization_declination=None,
    max_gain=100.0,
):
    """Transform induced/remanent total-field anomalies between field directions."""
    if (magnetization_inclination is None) != (magnetization_declination is None):
        raise ValueError("Provide both magnetization angles or leave both empty")
    if magnetization_inclination is None:
        magnetization_inclination = source_inclination
        magnetization_declination = source_declination
    source_field = magnetic_direction_factor(
        k_east, k_north, radial, source_inclination, source_declination
    )
    source_magnetization = magnetic_direction_factor(
        k_east,
        k_north,
        radial,
        magnetization_inclination,
        magnetization_declination,
    )
    target = magnetic_direction_factor(
        k_east, k_north, radial, target_inclination, target_declination
    )
    denominator = source_field * source_magnetization
    response = np.zeros(radial.shape, dtype=np.complex128)
    stable = (radial > 0.0) & (np.abs(denominator) > np.finfo(float).eps)
    response[stable] = target[stable] ** 2 / denominator[stable]
    max_gain = float(max_gain)
    if max_gain <= 1.0:
        raise ValueError("Maximum gain must exceed one")
    amplitude = np.abs(response)
    excessive = amplitude > max_gain
    response[excessive] *= max_gain / amplitude[excessive]
    return response


def radial_power_spectrum(values, spacing_northing, spacing_easting, bins=96):
    """Return radial wavenumber centers and mean power for preview plots."""
    _east, _north, radial = frequency_grid(
        np.asarray(values).shape, spacing_northing, spacing_easting
    )
    power = np.abs(np.fft.fft2(np.asarray(values, dtype=np.float64))) ** 2
    edges = np.linspace(0.0, float(radial.max()), int(bins) + 1)
    indices = np.digitize(radial.ravel(), edges) - 1
    sums = np.bincount(indices, weights=power.ravel(), minlength=bins + 1)[:bins]
    counts = np.bincount(indices, minlength=bins + 1)[:bins]
    means = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
    return 0.5 * (edges[:-1] + edges[1:]), means


def _validate_wavelength_band(long_wavelength, short_wavelength):
    long_wavelength = float(long_wavelength)
    short_wavelength = float(short_wavelength)
    if short_wavelength <= 0 or long_wavelength <= short_wavelength:
        raise ValueError(
            "Long wavelength must be greater than the positive short wavelength"
        )

"""Directional frequency-domain microleveling helpers."""

from __future__ import annotations

import numpy as np


def microlevel_grid(values, dx, dy, line_azimuth, across_wavelength, along_wavelength):
    """Return corrected grid and estimated line-corrugation component.

    Azimuth is clockwise from north. The correction isolates wavelengths shorter
    than ``across_wavelength`` across flight lines while retaining wavelengths
    longer than ``along_wavelength`` along them.
    """
    data = np.asarray(values, dtype=float)
    if data.ndim != 2 or min(data.shape) < 2:
        raise ValueError("Microleveling requires a two-dimensional grid.")
    if not np.isfinite(data).all():
        raise ValueError("Microleveling requires a complete finite grid.")
    if min(abs(dx), abs(dy), across_wavelength, along_wavelength) <= 0.0:
        raise ValueError("Pixel sizes and wavelengths must be positive.")
    ky = np.fft.fftfreq(data.shape[0], d=abs(dy))
    kx = np.fft.fftfreq(data.shape[1], d=abs(dx))
    grid_kx, grid_ky = np.meshgrid(kx, ky)
    azimuth = np.deg2rad(float(line_azimuth))
    # Unit vectors: along line (sin az, cos az), across (cos az, -sin az).
    k_along = grid_kx * np.sin(azimuth) + grid_ky * np.cos(azimuth)
    k_across = grid_kx * np.cos(azimuth) - grid_ky * np.sin(azimuth)
    across_cutoff = 1.0 / float(across_wavelength)
    along_cutoff = 1.0 / float(along_wavelength)
    high_across = 1.0 - np.exp(-0.5 * (np.abs(k_across) / across_cutoff) ** 4)
    low_along = np.exp(-0.5 * (np.abs(k_along) / along_cutoff) ** 2)
    transfer = high_across * low_along
    correction = np.fft.ifft2(np.fft.fft2(data - np.mean(data)) * transfer).real
    return data - correction, correction

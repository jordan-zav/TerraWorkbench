"""Explicit tabulated radial Fourier filters; no vendor control-file parser."""

import numpy as np

from ._array_contract import as_array
from ._calibration import integer_budget
from .spectral import frequency_grid


def tabulated_radial_filter(
    values,
    spacing,
    wavenumbers_rad_per_m,
    gains,
    *,
    max_abs_gain,
    max_cells=4_000_000,
    canceled=None,
):
    """Filter a complete periodic level grid using a real radial gain table.

    Spacing is (northing,easting) metres. Table wavenumbers are angular rad/m,
    increasing from zero. Linear interpolation is explicit; the last gain is
    retained above the last tabulated wavenumber. A gain at zero changes the
    mean. Negative gains reverse sign, not a phase-recovery operation. The
    caller supplies a finite positive gain budget; values beyond it are
    rejected, not clipped. No fill, padding or hidden normalization is applied.
    """
    integer_budget(max_cells, "Maximum cells")
    data, spacing, k, gain = (
        as_array(value, float)
        for value in (values, spacing, wavenumbers_rad_per_m, gains)
    )
    if (
        data.ndim != 2
        or min(data.shape) < 2
        or data.size > max_cells
        or not np.isfinite(data).all()
    ):
        raise ValueError(
            "A complete finite 2-D grid within the cell budget is required"
        )
    if spacing.shape != (2,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("Spacing must be positive (northing,easting) metres")
    maximum = float(max_abs_gain)
    if not np.isfinite(maximum) or maximum <= 0:
        raise ValueError("Explicit positive finite maximum absolute gain is required")
    if (
        k.ndim != 1
        or gain.shape != k.shape
        or k.size < 2
        or not np.isfinite(k).all()
        or not np.isfinite(gain).all()
    ):
        raise ValueError(
            "Finite matching wavenumber/gain vectors with at least two knots are required"
        )
    if k[0] != 0 or np.any(np.diff(k) <= 0) or np.any(abs(gain) > maximum):
        raise ValueError(
            "Wavenumbers must increase from zero and gains must respect the explicit budget"
        )
    if canceled is not None and canceled():
        raise RuntimeError("Radial filter canceled")
    _east, _north, radial = frequency_grid(data.shape, *spacing)
    transfer = np.interp(radial, k, gain)
    result = np.fft.ifft2(np.fft.fft2(data) * transfer).real
    if not np.isfinite(result).all():
        raise ValueError("Filtered values exceed finite range")
    if canceled is not None and canceled():
        raise RuntimeError("Radial filter canceled")
    return dict(
        filtered=result,
        recipe=dict(
            wavenumbers_rad_per_m=k.tolist(),
            gains=gain.tolist(),
            spacing_m=spacing.tolist(),
            interpolation="linear",
            above_last="constant last gain",
            gain_at_zero=float(gain[0]),
            max_abs_gain=maximum,
            domain="Periodic complete grid; output units equal input units",
        ),
    )

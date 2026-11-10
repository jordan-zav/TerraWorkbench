"""Quantitative spectra on complete, planar, uniformly sampled grids.

Axes are (northing, easting), metres. Wavenumbers are angular (rad/m).
PSD is a two-sided density per cycles/m in each axis: its discrete integral
is the window-weighted mean square after detrending. Depth fits use angular
wavenumber, never cycles/m. No automatic geological layer interpretation.
"""

import numpy as np
from scipy import signal

from ._array_contract import as_array


def grid_power_spectrum(values, spacing, *, detrend="plane", window="hann"):
    """Return PSD, angular axes and normalization diagnostics; reject NoData.

    spacing is (dy, dx). Hann is periodic. Plane removal is least squares on
    the whole grid, before windowing. Spectra are not gap-filled or padded.
    """
    a = as_array(values, dtype=float)
    ds = as_array(spacing, dtype=float)
    if a.ndim != 2 or min(a.shape) < 4 or not np.isfinite(a).all():
        raise ValueError("A complete finite grid of at least 4 by 4 is required")
    if ds.shape != (2,) or not np.isfinite(ds).all() or np.any(ds <= 0):
        raise ValueError("spacing must be positive finite (dy, dx) in metres")
    if detrend == "plane":
        y, x = np.meshgrid(
            np.linspace(-1, 1, a.shape[0]),
            np.linspace(-1, 1, a.shape[1]),
            indexing="ij",
        )
        design = np.column_stack([np.ones(a.size), x.ravel(), y.ravel()])
        trend = design @ np.linalg.lstsq(design, a.ravel(), rcond=None)[0]
        residual = a - trend.reshape(a.shape)
    elif detrend == "mean":
        residual = a - a.mean()
    elif detrend == "none":
        residual = a.copy()
    else:
        raise ValueError("detrend must be plane, mean or none")
    if window == "hann":
        w = np.outer(
            signal.windows.hann(a.shape[0], sym=False),
            signal.windows.hann(a.shape[1], sym=False),
        )
    elif window == "none":
        w = np.ones(a.shape)
    else:
        raise ValueError("window must be hann or none")
    psd = np.abs(np.fft.fft2(residual * w)) ** 2 * np.prod(ds) / np.sum(w * w)
    ky = 2 * np.pi * np.fft.fftfreq(a.shape[0], ds[0])
    kx = 2 * np.pi * np.fft.fftfreq(a.shape[1], ds[1])
    cell_frequency_area = 1 / (a.size * np.prod(ds))
    return {
        "psd": psd,
        "kx": kx,
        "ky": ky,
        "weighted_mean_square": float(np.sum((residual * w) ** 2) / np.sum(w * w)),
        "integrated_power": float(psd.sum() * cell_frequency_area),
        "frequency_cell_area": float(cell_frequency_area),
        "spacing_m": ds,
        "detrend": detrend,
        "window": window,
        "wavenumber_units": "rad/m",
        "psd_density_axes": "cycles/m",
    }


def binned_power_spectrum(spectrum, edges, *, azimuth_deg=None, half_width_deg=15):
    """Annular mean PSD, sample spread and counts; optional axial sector.

    Azimuth is counterclockwise from easting, modulo 180 degrees. Both
    conjugate sectors are included. Restrict to the inscribed Nyquist disk.
    Pixel counts are NOT independent degrees of freedom, especially with a
    window. Empty bins are NaN; DC is always excluded.
    """
    psd = as_array(spectrum["psd"], float)
    kx, ky = as_array(spectrum["kx"]), as_array(spectrum["ky"])
    edges = as_array(edges, float)
    if (
        edges.ndim != 1
        or edges.size < 2
        or not np.isfinite(edges).all()
        or edges[0] < 0
        or np.any(np.diff(edges) <= 0)
    ):
        raise ValueError("edges must be increasing nonnegative rad/m")
    if psd.shape != (ky.size, kx.size) or not np.isfinite(psd).all() or np.any(psd < 0):
        raise ValueError("Invalid spectrum")
    xx, yy = np.meshgrid(kx, ky)
    radial = np.hypot(xx, yy)
    cutoff = np.pi / max(as_array(spectrum["spacing_m"]))
    keep = (radial > 0) & (radial <= cutoff * (1 + 1e-12))
    if azimuth_deg is not None:
        if not np.isfinite(azimuth_deg) or not 0 < half_width_deg <= 90:
            raise ValueError("Invalid axial sector")
        angle = np.rad2deg(np.arctan2(yy, xx))
        delta = (angle - azimuth_deg + 90) % 180 - 90
        keep &= np.abs(delta) <= half_width_deg
    index = np.searchsorted(edges, radial, side="right") - 1
    index[radial == edges[-1]] = edges.size - 2
    count, mean, spread, wave = [], [], [], []
    for i in range(edges.size - 1):
        take = keep & (index == i)
        n = int(take.sum())
        count.append(n)
        mean.append(float(psd[take].mean()) if n else np.nan)
        spread.append(float(psd[take].std(ddof=1)) if n > 1 else np.nan)
        wave.append(float(radial[take].mean()) if n else np.nan)
    return {
        "wavenumber": np.array(wave),
        "power": np.array(mean),
        "pixel_std": np.array(spread),
        "count": np.array(count),
        "edges": edges.copy(),
        "azimuth_deg": azimuth_deg,
        "half_width_deg": half_width_deg,
        "uncertainty_note": "Conjugate/windowed pixels are correlated",
    }


def fit_spectral_depth(
    wavenumber, power, *, fit_range, geometry_exponent=0.0, log_power_std=None
):
    """Fit P(k)=A*k**p*exp(-2*h*k), explicitly chosen p and k range.

    h is a model-dependent distance below the observation plane, not an
    absolute elevation or automatically the top/bottom/Curie depth. Reported
    standard error is conditional regression error, not geological uncertainty.
    Bins are equally weighted unless independent log-power errors are supplied.
    """
    k, p = as_array(wavenumber, float), as_array(power, float)
    bounds = as_array(fit_range, float)
    if (
        k.ndim != 1
        or p.shape != k.shape
        or bounds.shape != (2,)
        or not np.isfinite(bounds).all()
        or not 0 < bounds[0] < bounds[1]
        or not np.isfinite(geometry_exponent)
    ):
        raise ValueError("Invalid spectrum or explicit positive fit range")
    use = (
        np.isfinite(k) & np.isfinite(p) & (p > 0) & (k >= bounds[0]) & (k <= bounds[1])
    )
    if use.sum() < 4:
        raise ValueError("At least four positive finite bins in fit range are required")
    x = k[use]
    y = np.log(p[use]) - geometry_exponent * np.log(x)
    if np.unique(x).size < 4:
        raise ValueError("At least four distinct wavenumbers are required")
    if log_power_std is None:
        std = np.ones(x.size)
    else:
        errors = as_array(log_power_std, float)
        if (
            errors.shape != k.shape
            or not np.isfinite(errors[use]).all()
            or np.any(errors[use] <= 0)
        ):
            raise ValueError("log_power_std must be positive on fitted bins")
        std = errors[use]
    # Centering avoids unstable intercept/slope covariance on tiny k ranges.
    center = np.average(x, weights=1 / std**2)
    design = np.column_stack([np.ones(x.size), x - center])
    weighted = design / std[:, None]
    fit, _, rank, _ = np.linalg.lstsq(weighted, y / std, rcond=None)
    if rank != 2:
        raise ValueError("Rank-deficient spectral fit")
    residual = y - design @ fit
    covariance = np.linalg.inv(weighted.T @ weighted)
    if log_power_std is None:
        covariance *= np.sum((residual / std) ** 2) / (x.size - 2)
    depth = -fit[1] / 2
    total = np.sum(((y - np.average(y, weights=1 / std**2)) / std) ** 2)
    return {
        "depth_m": float(depth),
        "physical_decay": bool(depth >= 0),
        "conditional_depth_std_m": float(np.sqrt(covariance[1, 1]) / 2),
        "log_amplitude": float(fit[0] - fit[1] * center),
        "slope": float(fit[1]),
        "geometry_exponent": float(geometry_exponent),
        "r_squared": float(1 - np.sum((residual / std) ** 2) / total)
        if total
        else np.nan,
        "used": use,
        "log_residual": residual,
        "fit_range_rad_m": bounds,
        "assumption": "P(k)=A*k**p*exp(-2*h*k); planar statistical source model",
    }


def wiener_inverse_transfer(transfer, signal_psd, noise_psd):
    """Linear MMSE inverse for y=H*x+n; spectra refer to x and observed n.

    Returns a transfer only. No inferred noise floor or silent amplification
    cap. Zero signal and noise gives zero transfer, not division by zero.
    """
    h, s, n = np.broadcast_arrays(
        as_array(transfer, complex),
        as_array(signal_psd, float),
        as_array(noise_psd, float),
    )
    if (
        not (np.isfinite(h).all() and np.isfinite(s).all() and np.isfinite(n).all())
        or np.any(s < 0)
        or np.any(n < 0)
    ):
        raise ValueError("Finite transfer and nonnegative signal/noise PSD required")
    denominator = abs(h) ** 2 * s + n
    return np.divide(
        h.conj() * s, denominator, out=np.zeros_like(h), where=denominator > 0
    )

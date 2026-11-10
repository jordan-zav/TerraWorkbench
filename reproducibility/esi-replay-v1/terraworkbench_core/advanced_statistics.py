"""Explicit statistical models for spectra and small linear inverse problems."""

import numpy as np
from scipy import signal

from ._array_contract import as_array
from .inversion_diagnostics import linear_resolution


def linear_gaussian_ensemble(
    sensitivity,
    observed,
    data_std,
    regularization,
    *,
    reference,
    beta,
    sample_count,
    seed,
    max_elements=2_000_000,
):
    """Exact unconstrained LINEAR Gaussian posterior draws with a fixed prior.

    Requires proper precision. Not a posterior from nonlinear, constrained,
    IRLS or adaptive-beta inversion. Samples may violate physical bounds;
    none are clipped. Geometry/forward-model uncertainty is excluded.
    """
    g, data, std, reg, prior = [
        as_array(a, float)
        for a in (sensitivity, observed, data_std, regularization, reference)
    ]
    if (
        g.ndim != 2
        or data.shape != (g.shape[0],)
        or prior.shape != (g.shape[1],)
        or not np.isfinite(data).all()
        or not np.isfinite(prior).all()
    ):
        raise ValueError(
            "Finite data/reference matching linear forward matrix required"
        )
    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, (int, np.integer))
        or sample_count < 2
    ):
        raise ValueError("sample_count must be an explicit integer >=2")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("An explicit nonnegative integer seed is required")
    if (
        sample_count * g.shape[1] + g.size + reg.size + 6 * g.shape[1] ** 2
        > max_elements
    ):
        raise ValueError("Dense posterior sample budget exceeded")
    audit = linear_resolution(g, std, reg, beta=beta, max_elements=max_elements)
    covariance = audit["posterior_covariance"]
    rhs = g.T @ (data / std**2) + beta * (reg.T @ reg) @ prior
    mean = covariance @ rhs
    factor = np.linalg.cholesky((covariance + covariance.T) / 2)
    samples = (
        mean
        + np.random.default_rng(seed).normal(size=(sample_count, len(mean))) @ factor.T
    )
    return {
        "posterior_mean": mean,
        "posterior_covariance": covariance,
        "samples": samples,
        "percentiles_2_5_50_97_5": np.percentile(samples, [2.5, 50, 97.5], axis=0),
        "seed": int(seed),
        "model": "fixed unconstrained linear Gaussian",
        "resolution": audit["resolution"],
    }


def matched_layer_filters(
    angular_wavenumber,
    depths_m,
    amplitudes,
    *,
    geometry_exponents,
    noise_psd,
    max_elements=5_000_000,
):
    """Wiener shares for independent prescribed Pj=Aj*k**pj*exp(-2*hj*k).

    Supplied depths, geometry powers, scales and observed noise PSD; no unique
    geological layers inferred. Filters act on the observed field, not as
    downward continuation. DC response follows the exponent (0**0 is 1).
    """
    k, depth, amplitude, power, noise = [
        as_array(a, float)
        for a in (
            angular_wavenumber,
            depths_m,
            amplitudes,
            geometry_exponents,
            noise_psd,
        )
    ]
    if (
        k.ndim not in (1, 2)
        or not k.size
        or depth.ndim != 1
        or not 1 <= depth.size <= 64
        or amplitude.shape != depth.shape
        or power.shape != depth.shape
        or noise.shape not in ((), k.shape)
        or not all(np.isfinite(a).all() for a in (k, depth, amplitude, power, noise))
        or np.any(k < 0)
        or np.any(depth < 0)
        or np.any(amplitude < 0)
        or np.any(power < 0)
        or np.any(noise < 0)
    ):
        raise ValueError(
            "Nonnegative angular k, layer depths/scales/powers and matching noise PSD required"
        )
    if len(depth) * k.size > max_elements:
        raise ValueError("Matched-layer spectral budget exceeded")
    shape = (-1,) + (1,) * k.ndim
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        layers = (
            amplitude.reshape(shape)
            * k ** power.reshape(shape)
            * np.exp(-2 * depth.reshape(shape) * k)
        )
    total = layers.sum(axis=0) + noise
    if not np.isfinite(layers).all() or not np.isfinite(total).all():
        raise ValueError("Layer spectra overflow; check physical scales and units")
    filters = np.divide(layers, total, out=np.zeros_like(layers), where=total > 0)
    remainder = np.divide(
        np.broadcast_to(noise, k.shape), total, out=np.zeros(k.shape), where=total > 0
    )
    return {
        "layer_filters": filters,
        "noise_remainder_filter": remainder,
        "layer_psd": layers,
        "model": "independent prescribed exponential statistical layers",
        "warning": "Layer geometry/depths supplied, not independently inferred",
    }


def profile_admittance_coherence(
    reference,
    observed,
    spacing_m,
    *,
    segment_samples,
    overlap_samples,
    reference_psd_floor,
):
    """Welch cross-spectra: admittance=Pxy/Pxx and magnitude-squared coherence.

    Spatial sampling m; angular k rad/m, PSD per cycles/m. CSD convention
    conj(reference_fft)*observed_fft. Multiple Hann segments, overlapping
    segments are correlated. No automatic flexure or causal interpretation.
    """
    x, y = as_array(reference, float), as_array(observed, float)
    if (
        x.ndim != 1
        or y.shape != x.shape
        or not np.isfinite(x).all()
        or not np.isfinite(y).all()
        or not np.isfinite([spacing_m, reference_psd_floor]).all()
        or spacing_m <= 0
        or reference_psd_floor <= 0
    ):
        raise ValueError(
            "Finite paired profiles, spacing and explicit positive PSD floor required"
        )
    if (
        isinstance(segment_samples, bool)
        or not isinstance(segment_samples, (int, np.integer))
        or not 8 <= segment_samples <= len(x) // 2
        or isinstance(overlap_samples, bool)
        or not isinstance(overlap_samples, (int, np.integer))
        or not 0 <= overlap_samples < segment_samples
    ):
        raise ValueError(
            "Integer Welch segment/overlap with at least two segments required"
        )
    options = dict(
        fs=1 / spacing_m,
        window="hann",
        nperseg=segment_samples,
        noverlap=overlap_samples,
        detrend="constant",
        scaling="density",
    )
    frequency, pxx = signal.welch(x, **options)
    _, pyy = signal.welch(y, **options)
    _, pxy = signal.csd(x, y, **options)
    valid = (pxx > reference_psd_floor) & (pyy > 0)
    admittance = np.divide(pxy, pxx, out=np.full(pxy.shape, np.nan + 0j), where=valid)
    coherence = np.divide(
        abs(pxy) ** 2, pxx * pyy, out=np.full(pxx.shape, np.nan), where=valid
    )
    return {
        "angular_wavenumber_rad_m": 2 * np.pi * frequency,
        "admittance": admittance,
        "coherence": coherence,
        "reference_psd": pxx,
        "observed_psd": pyy,
        "cross_psd": pxy,
        "segment_count": 1
        + (len(x) - segment_samples) // (segment_samples - overlap_samples),
        "uncertainty_note": "Overlapping/tapered segments correlated; no confidence interval inferred",
    }

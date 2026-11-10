"""Full-spectrum count processing; NumPy/SciPy only, no survey assumptions.

Inputs are raw nonnegative counts, never already stripped concentrations.
No aircraft, atmospheric radon, dead-time or height correction is inferred.
Noise estimates below assume independent Poisson raw channel counts.
"""

import numpy as np
from scipy import linalg, sparse
from scipy.optimize import nnls

from ._array_contract import as_array


def _edges(values):
    a = as_array(values, float)
    if a.ndim != 1 or a.size < 2 or not np.isfinite(a).all() or np.any(np.diff(a) <= 0):
        raise ValueError("Energy edges must be finite and strictly increasing")
    return a


def energy_rebin(counts, input_edges, output_edges):
    """Conservative overlap rebinning, assuming uniform density within a bin.

    Counts outside target support are reported, not redistributed. Fractional
    rebinning produces correlated channels. variance_diagonal alone does NOT
    describe the output covariance; rebin_matrix preserves the full operator.
    Cov(out)=A*diag(raw_counts)*A.T for each independent raw-count spectrum.
    """
    old, new = _edges(input_edges), _edges(output_edges)
    c = as_array(counts, float)
    if (
        c.ndim < 1
        or c.shape[-1] != old.size - 1
        or not np.isfinite(c).all()
        or np.any(c < 0)
    ):
        raise ValueError("Nonnegative counts must match the input energy bins")
    rows, columns, weights = [], [], []
    i = j = 0
    while i < old.size - 1 and j < new.size - 1:
        overlap = min(old[i + 1], new[j + 1]) - max(old[i], new[j])
        if overlap > 0:
            rows.append(j)
            columns.append(i)
            weights.append(overlap / (old[i + 1] - old[i]))
        if old[i + 1] <= new[j + 1]:
            i += 1
        else:
            j += 1
    operator = sparse.csr_matrix(
        (weights, (rows, columns)), shape=(new.size - 1, old.size - 1)
    )
    flat = c.reshape(-1, c.shape[-1])
    rebinned = (operator @ flat.T).T.reshape((*c.shape[:-1], new.size - 1))
    variance = (operator.power(2) @ flat.T).T.reshape(rebinned.shape)
    return {
        "counts": rebinned,
        "variance_diagonal": variance,
        "lost_counts": c.sum(axis=-1) - rebinned.sum(axis=-1),
        "rebin_matrix": operator,
        "output_edges": new.copy(),
    }


def fit_energy_calibration(channel_peaks, energy_peaks, *, energy_std=None):
    """Linear E=offset+gain*channel fit with optional absolute energy errors.

    At least three peaks allow a residual check; two are insufficient for
    assessing nonlinearity. Returns covariance in (offset, gain) order.
    """
    x, y = as_array(channel_peaks, float), as_array(energy_peaks, float)
    if (
        x.ndim != 1
        or x.size < 3
        or y.shape != x.shape
        or not np.isfinite(x).all()
        or not np.isfinite(y).all()
        or np.unique(x).size < 3
    ):
        raise ValueError(
            "At least three finite distinct peak-channel/energy pairs required"
        )
    std = np.ones(x.shape) if energy_std is None else as_array(energy_std, float)
    if std.shape != x.shape or not np.isfinite(std).all() or np.any(std <= 0):
        raise ValueError("Peak energy errors must be finite and positive")
    center = np.average(x, weights=1 / std**2)
    design = np.column_stack([np.ones(x.size), x - center]) / std[:, None]
    params, _, rank, _ = np.linalg.lstsq(design, y / std, rcond=None)
    if rank != 2 or params[1] <= 0:
        raise ValueError("Rank-deficient or nonpositive-gain calibration")
    residual = y - (params[0] + params[1] * (x - center))
    cov = np.linalg.inv(design.T @ design)
    if energy_std is None:
        cov *= np.sum((residual / std) ** 2) / (x.size - 2)
    transform = np.array([[1.0, -center], [0.0, 1.0]])
    return {
        "offset": float(params[0] - params[1] * center),
        "gain": float(params[1]),
        "covariance": transform @ cov @ transform.T,
        "residual": residual,
        "degrees_of_freedom": x.size - 2,
    }


def poisson_nasvd(counts, rank, *, exposure_s=None, max_elements=5_000_000):
    """Uncentered noise-adjusted SVD with separable Poisson expected counts.

    E[count(i,j)]=exposure(i)*mean_rate(j). Whiten by sqrt(E), truncate at
    caller-selected rank, then unwhiten. Zero-total channels/rows stay zero.
    Negative reconstructions are flagged, NOT clipped. Noise whitening is
    estimated, so singular values are not a universal rank/significance test.
    The explicit matrix budget prevents accidental survey-scale dense SVD.
    """
    c = as_array(counts, float)
    if c.ndim != 2 or min(c.shape) < 2 or not np.isfinite(c).all() or np.any(c < 0):
        raise ValueError("Finite nonnegative (spectra, channels) counts required")
    if c.size > max_elements:
        raise ValueError("Dense NASVD matrix budget exceeded; process training blocks")
    if (
        isinstance(rank, bool)
        or not isinstance(rank, (int, np.integer))
        or not 1 <= rank <= min(c.shape)
    ):
        raise ValueError("rank must be an explicit integer from 1 to min(shape)")
    exposure = (
        np.ones(c.shape[0]) if exposure_s is None else as_array(exposure_s, float)
    )
    if (
        exposure.shape != (c.shape[0],)
        or not np.isfinite(exposure).all()
        or np.any(exposure <= 0)
    ):
        raise ValueError("Exposure must be positive seconds per spectrum")
    rate = c.sum(axis=0) / exposure.sum()
    active = rate > 0
    result = np.zeros_like(c)
    if not active.any():
        return {
            "counts": result,
            "negative": result < 0,
            "singular_values": np.array([]),
            "rank": 0,
            "active_channels": active,
            "mean_rate": rate,
        }
    row_scale = np.sqrt(exposure)
    channel_scale = np.sqrt(rate[active])
    whitened = c[:, active] / row_scale[:, None] / channel_scale
    u, singular, vh = np.linalg.svd(whitened, full_matrices=False)
    use_rank = min(rank, len(singular))
    result[:, active] = (
        ((u[:, :use_rank] * singular[:use_rank]) @ vh[:use_rank])
        * row_scale[:, None]
        * channel_scale
    )
    return {
        "counts": result,
        "negative": result < 0,
        "singular_values": singular,
        "rank": use_rank,
        "active_channels": active,
        "mean_rate": rate,
    }


def integrate_energy_windows(counts, energy_edges, windows):
    """Fractional energy-window counts and complete plug-in Poisson covariance.

    Covariance accounts for shared raw bins even between overlapping windows.
    Windows must be contained in the calibrated spectrum support. Fractional
    bin weights presume uniform within-bin count density.
    """
    edges = _edges(energy_edges)
    c, bounds = as_array(counts, float), as_array(windows, float)
    if (
        c.ndim < 1
        or c.shape[-1] != edges.size - 1
        or not np.isfinite(c).all()
        or np.any(c < 0)
    ):
        raise ValueError("Nonnegative raw counts matching energy bins required")
    if (
        bounds.ndim != 2
        or bounds.shape[1] != 2
        or len(bounds) < 1
        or len(bounds) > 128
        or not np.isfinite(bounds).all()
        or np.any(bounds[:, 1] <= bounds[:, 0])
        or np.any(bounds[:, 0] < edges[0])
        or np.any(bounds[:, 1] > edges[-1])
    ):
        raise ValueError(
            "Require 1..128 nonempty energy windows inside spectrum support"
        )
    overlap = np.maximum(
        0.0,
        np.minimum(bounds[:, 1, None], edges[None, 1:])
        - np.maximum(bounds[:, 0, None], edges[None, :-1]),
    )
    weights = overlap / np.diff(edges)
    totals = c @ weights.T
    covariance = np.einsum("wi,...i,vi->...wv", weights, c, weights)
    return {
        "counts": totals,
        "covariance": covariance,
        "weights": weights,
        "windows": bounds.copy(),
        "noise_model": "independent raw Poisson bins",
    }


def linear_covariance_transform(values, covariance, matrix):
    """Propagate a fixed calibration/stripping operator and full covariance.

    Operator uncertainty itself is not included. Negative stripped estimates
    remain negative; clipping would change the uncertainty model.
    """
    x, cov, a = (
        as_array(values, float),
        as_array(covariance, float),
        as_array(matrix, float),
    )
    if (
        x.ndim != 1
        or cov.shape != (x.size, x.size)
        or a.ndim != 2
        or a.shape[1] != x.size
    ):
        raise ValueError("Incompatible value, covariance and operator dimensions")
    if not all(np.isfinite(v).all() for v in (x, cov, a)) or not np.allclose(
        cov, cov.T
    ):
        raise ValueError("Finite inputs and symmetric covariance required")
    if np.linalg.eigvalsh(cov).min() < -1e-10 * max(1.0, abs(cov).max()):
        raise ValueError("Covariance must be positive semidefinite")
    return {"values": a @ x, "covariance": a @ cov @ a.T}


def fit_full_spectrum(counts, response, *, count_std, max_elements=2_000_000):
    """Weighted nonnegative template fit, response=(channels, components).

    Response must already include exposure and calibration; include background
    templates explicitly. Requires externally justified positive uncertainties
    (not sqrt(0) or automatically fabricated uncertainties). Conditional
    active-set covariance is not a full nonnegative Bayesian posterior.
    """
    y, a, std = (
        as_array(counts, float),
        as_array(response, float),
        as_array(count_std, float),
    )
    if (
        y.ndim != 1
        or a.ndim != 2
        or a.shape[0] != len(y)
        or std.shape != y.shape
        or a.shape[1] < 1
        or a.shape[1] > a.shape[0]
        or a.size > max_elements
        or not all(np.isfinite(v).all() for v in (y, a, std))
        or np.any(y < 0)
        or np.any(a < 0)
        or np.any(std <= 0)
    ):
        raise ValueError(
            "Nonnegative counts/templates and positive errors with bounded dimensions required"
        )
    weighted = a / std[:, None]
    if np.linalg.matrix_rank(weighted) != a.shape[1]:
        raise ValueError("Response templates are not identifiable")
    coefficients, _ = nnls(weighted, y / std)
    active = coefficients > 0
    covariance = np.full((len(coefficients), len(coefficients)), np.nan)
    if active.any():
        covariance[np.ix_(active, active)] = linalg.inv(
            weighted[:, active].T @ weighted[:, active]
        )
    predicted = a @ coefficients
    return {
        "coefficients": coefficients,
        "predicted": predicted,
        "residual": y - predicted,
        "chi_squared": float(np.sum(((y - predicted) / std) ** 2)),
        "active": active,
        "conditional_covariance": covariance,
    }


def mnf_denoise(
    training_spectra,
    noise_covariance,
    rank,
    *,
    spectra=None,
    max_elements=5_000_000,
    maximum_noise_condition=1e10,
):
    """Noise-whitened linear MNF, retaining caller-selected high-SNR modes.

    Rows are spectra, columns share channel units. Supply a stationary SPD
    noise covariance in those units squared, independently measured or modeled.
    Raw Poisson counts are heteroscedastic: a single noise covariance is not
    automatically valid; use suitable normalization/calibration or NASVD.
    Training determines the mean and rotations; optional spectra are held-out
    data transformed without refitting. Eigenvalues are total/noise variance,
    descending; no automatic rank or significance interpretation.
    Negative reconstructed values are flagged, never clipped. Output noise
    covariance is conditional on this fixed trained transform, not uncertainty
    in the covariance estimate, selected rank or changing instrumental noise.
    """
    train, noise = as_array(training_spectra, float), as_array(noise_covariance, float)
    if train.ndim != 2 or train.shape[0] < 3 or train.shape[1] < 1:
        raise ValueError(
            "At least three training spectra with nonempty channel axis required"
        )
    n_channel = train.shape[1]
    target = train if spectra is None else as_array(spectra, float)
    if (
        noise.shape != (n_channel, n_channel)
        or target.ndim != 2
        or not len(target)
        or target.shape[1] != n_channel
        or not all(np.isfinite(a).all() for a in (train, noise, target))
    ):
        raise ValueError(
            "Finite training/target spectra and matching noise covariance required"
        )
    if train.size + target.size + 10 * n_channel**2 > max_elements:
        raise ValueError("Dense MNF matrix budget exceeded")
    if (
        isinstance(rank, bool)
        or not isinstance(rank, (int, np.integer))
        or not 1 <= rank <= n_channel
    ):
        raise ValueError("rank must be an explicit integer from 1 to channel count")
    if not np.isfinite(maximum_noise_condition) or maximum_noise_condition < 1:
        raise ValueError("maximum_noise_condition must be finite and at least one")
    if not np.allclose(noise, noise.T, rtol=1e-10, atol=0):
        raise ValueError("Noise covariance must be symmetric")
    noise = (noise + noise.T) / 2
    eigen_noise = np.linalg.eigvalsh(noise)
    if (
        eigen_noise[0] <= 0
        or eigen_noise[-1] / eigen_noise[0] > maximum_noise_condition
    ):
        raise ValueError(
            "Noise covariance must be positive definite and well conditioned"
        )
    lower = linalg.cholesky(noise, lower=True)
    mean = train.mean(axis=0)
    whitened = linalg.solve_triangular(lower, (train - mean).T, lower=True).T
    covariance = whitened.T @ whitened / (len(train) - 1)
    eigenvalues, vectors = linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues, vectors = eigenvalues[order], vectors[:, order]
    retained = vectors[:, :rank]
    forward = linalg.solve_triangular(lower.T, retained, lower=False)
    inverse = retained.T @ lower.T
    scores = (target - mean) @ forward
    reconstruction = scores @ inverse + mean
    projection = forward @ inverse
    conditional_noise = projection.T @ noise @ projection
    return {
        "spectra": reconstruction,
        "negative": reconstruction < 0,
        "scores": scores,
        "training_mean": mean,
        "forward_matrix": forward,
        "inverse_matrix": inverse,
        "total_noise_eigenvalues": eigenvalues,
        "rank": int(rank),
        "noise_covariance": noise.copy(),
        "conditional_output_noise_covariance": conditional_noise,
        "warning": "Stationary supplied noise covariance; transform/rank uncertainty excluded",
    }

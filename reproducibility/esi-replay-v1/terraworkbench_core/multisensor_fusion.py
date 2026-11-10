"""Masked raster RGB/PCA fusion and explicit percentile anomaly coincidence.

Method families: Kvamme (2006), doi:10.1002/arp.268; Kvamme et al.
(2019), doi:10.1016/B978-0-12-812429-1.00009-X. Percentile bounds,
absolute anomaly channels and thresholds are application parameters, not
claimed reproductions of a published site experiment or probabilities.
"""

import numpy as np

MAX_CELLS = 4_000_000


def stack_layers(layers):
    arrays = [np.ma.asarray(a, dtype=float).filled(np.nan) for a in layers]
    if not arrays or arrays[0].ndim != 2 or arrays[0].size > MAX_CELLS:
        raise ValueError("Fusion requires 2D rasters with at most 4 million cells.")
    if any(a.shape != arrays[0].shape for a in arrays):
        raise ValueError(
            "Fusion grids must share an identical shape and spatial lattice."
        )
    values = np.stack(arrays, axis=-1)
    mask = np.isfinite(values).all(axis=-1)
    if mask.sum() < 3:
        raise ValueError("Fusion requires at least three jointly observed cells.")
    return values, mask


def rgb_composite(layers, percentiles=(2.0, 98.0), bounds=None):
    values, mask = stack_layers(layers)
    if values.shape[-1] != 3:
        raise ValueError("RGB requires exactly three channels.")
    if not 0 <= percentiles[0] < percentiles[1] <= 100:
        raise ValueError("Invalid stretch percentiles.")
    if bounds is None:
        bounds = np.percentile(values[mask], percentiles, axis=0).T
    bounds = np.asarray(bounds, dtype=float)
    if (
        bounds.shape != (3, 2)
        or not np.isfinite(bounds).all()
        or (bounds[:, 1] < bounds[:, 0]).any()
    ):
        raise ValueError("RGB bounds must be three finite increasing pairs.")
    rgb = np.full(values.shape, np.nan)
    for j, (lo, hi) in enumerate(bounds):
        rgb[..., j][mask] = (
            np.clip((values[..., j][mask] - lo) / (hi - lo), 0, 1) if hi > lo else 0.0
        )
    return rgb, dict(
        bounds=bounds.tolist(),
        common_cells=int(mask.sum()),
        units="unitless display RGB",
    )


def pca_fusion(layers, percentiles=(2.0, 98.0)):
    values, mask = stack_layers(layers)
    if not 0 <= percentiles[0] < percentiles[1] <= 100:
        raise ValueError("Invalid PCA clipping percentiles.")
    x = values[mask]
    bounds = np.percentile(x, percentiles, axis=0)
    clipped = np.clip(x, bounds[0], bounds[1])
    means = clipped.mean(axis=0)
    scales = clipped.std(axis=0, ddof=1)
    active = scales > np.finfo(float).eps * np.maximum(1, np.abs(means))
    scales = np.where(active, scales, 1.0)
    standardized = (clipped - means) / scales
    covariance = standardized.T @ standardized / (len(x) - 1)
    eigenvalues, loadings = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = np.maximum(eigenvalues[order], 0)
    loadings = loadings[:, order]
    # Deterministic sign; PCA sign alone has no physical interpretation.
    for j in range(loadings.shape[1]):
        if loadings[np.argmax(np.abs(loadings[:, j])), j] < 0:
            loadings[:, j] *= -1
    components = np.full(values.shape, np.nan)
    components[mask] = standardized @ loadings
    total = float(eigenvalues.sum())
    return components, dict(
        common_cells=int(mask.sum()),
        clip_bounds=bounds.T.tolist(),
        means=means.tolist(),
        scales=scales.tolist(),
        active_channels=active.tolist(),
        eigenvalues=eigenvalues.tolist(),
        loadings=loadings.tolist(),
        explained_variance_ratio=(
            eigenvalues / total if total else np.zeros_like(eigenvalues)
        ).tolist(),
        units="unitless standardized component",
        ground_truth_validated=False,
    )


def anomaly_coincidence(layers, percentile=90.0):
    values, mask = stack_layers(layers)
    if values.shape[-1] != 3:
        raise ValueError("Coincidence classes require three channels.")
    if not np.isfinite(percentile) or not 0 < percentile < 100:
        raise ValueError("Threshold percentile must be between 0 and 100.")
    thresholds = np.percentile(values[mask], percentile, axis=0)
    anomaly = (values > thresholds) & mask[..., None]
    codes = np.full(mask.shape, np.nan)
    codes[mask] = sum(anomaly[..., j][mask] * (1 << j) for j in range(3))
    pair_metrics = {}
    n = int(mask.sum())
    for a, b in ((0, 1), (0, 2), (1, 2)):
        ca = int(anomaly[..., a].sum())
        cb = int(anomaly[..., b].sum())
        overlap = int((anomaly[..., a] & anomaly[..., b]).sum())
        expected = ca * cb / n
        pair_metrics[f"{a}-{b}"] = dict(
            count_a=ca,
            count_b=cb,
            overlap_cells=overlap,
            dice=2 * overlap / (ca + cb) if ca + cb else 0.0,
            independence_reference_cells=expected,
            overlap_to_independence=overlap / expected if expected else None,
        )
    return codes, dict(
        percentile=float(percentile),
        thresholds=thresholds.tolist(),
        common_cells=n,
        class_counts={str(k): int(np.sum(codes == k)) for k in range(8)},
        pairs=pair_metrics,
        interpretation="Thresholded co-occurrence, not archaeological confidence or ground truth.",
    )


def shift_without_wrap(array, dy, dx):
    """Integer-cell diagnostic translation with missing borders; never wraps."""
    array = np.ma.asarray(array, dtype=float).filled(np.nan)
    if array.ndim != 2 or int(dy) != dy or int(dx) != dx:
        raise ValueError("Shift requires a 2D grid and integer offsets.")
    dy = int(dy)
    dx = int(dx)
    height, width = array.shape
    result = np.full(array.shape, np.nan)
    if abs(dy) >= height or abs(dx) >= width:
        return result
    result[
        max(0, dy) : min(height, height + dy), max(0, dx) : min(width, width + dx)
    ] = array[
        max(0, -dy) : min(height, height - dy), max(0, -dx) : min(width, width - dx)
    ]
    return result

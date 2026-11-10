"""Truth-based model recovery assessment, separate from data-fit/solver success.

Criteria are caller-declared before a campaign. Truth belongs to validation,
never automatically to a production inversion's prior or parameter selection.
"""

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree, distance
from scipy.optimize import linear_sum_assignment

from ._array_contract import as_array
from ._calibration import integer_budget

_CRITERIA = {
    "location_tolerance_m",
    "volume_relative_tolerance",
    "contrast_relative_tolerance",
    "support_dice_min",
    "direction_tolerance_deg",
    "model_relative_tolerance",
}


def _regions(xyz, mask, volumes, radius, max_links, canceled, edges=None):
    take = np.flatnonzero(mask)
    if not len(take):
        return [], 0
    if canceled is not None and canceled():
        raise InterruptedError("Model recovery assessment canceled")
    if edges is None:
        tree = cKDTree(xyz[take])
        count = int(
            (
                tree.query_ball_point(xyz[take], radius, return_length=True).sum()
                - len(take)
            )
            // 2
        )
        if count > max_links:
            raise ValueError("Recovery connectivity link budget exceeded")
        pairs = tree.query_pairs(radius, output_type="ndarray")
    else:
        selected = edges[mask[edges].all(axis=1)]
        pairs = np.searchsorted(take, selected)
    graph = coo_matrix(
        (np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(take), len(take))
    ).tocsr()
    n, labels = connected_components(graph, directed=False)
    if n > 64:
        return [], int(n)
    result = []
    for i in range(n):
        indices = take[labels == i]
        weights = volumes[indices]
        result.append(
            dict(
                indices=indices,
                volume=float(weights.sum()),
                centroid=np.average(xyz[indices], axis=0, weights=weights),
            )
        )
    return result, int(n)


def model_recovery_metrics(
    coordinates_enu_m,
    cell_volumes_m3,
    recovered,
    truth,
    *,
    criteria,
    connectivity_radius_m=None,
    connectivity_edges=None,
    support_fraction=0.5,
    vector=False,
    max_cells=20_000,
    max_links=200_000,
    canceled=None,
):
    """Assess location, volume, support, contrast, direction and volume-weighted L2.

    Scalars use (n,) properties, vectors use cell-major ENU (n,3). All properties
    must share physical units. Support threshold is support_fraction times the
    maximum TRUE amplitude, used for scoring only. Connected components use an
    either an explicit center-distance radius or caller-supplied cell-adjacency
    edges. The radius is not an adaptive-mesh face topology; explicit edges let
    a caller supply that topology without falsely fragmenting coarse cells.
    Predicted/truth component centroids are matched by minimum total distance.
    Count mismatch, missing/fragmented bodies and undefined direction fail the
    requested recovery criteria. Contrast/direction use recovered values in
    true body regions; other criteria jointly penalize leakage/displacement.
    Output is a deterministic benchmark assessment, not confidence/probability.
    """
    integer_budget(max_cells, "max_cells")
    integer_budget(max_links, "max_links")
    if type(vector) is not bool:
        raise ValueError("vector must be boolean")
    xyz, volumes, model, actual = [
        as_array(v, float)
        for v in (coordinates_enu_m, cell_volumes_m3, recovered, truth)
    ]
    if xyz.ndim != 2 or xyz.shape[1] != 3:
        raise ValueError("Finite ENU centers shaped (n,3) required")
    expected = (len(xyz), 3) if vector else (len(xyz),)
    if (
        xyz.ndim != 2
        or xyz.shape[1] != 3
        or not 1 <= len(xyz) <= max_cells
        or volumes.shape != (len(xyz),)
        or model.shape != expected
        or actual.shape != expected
        or not all(np.isfinite(v).all() for v in (xyz, volumes, model, actual))
        or np.any(volumes <= 0)
    ):
        raise ValueError(
            "Aligned finite centers/positive volumes and scalar/vector model/truth required"
        )
    if (
        not isinstance(criteria, dict)
        or set(criteria) != _CRITERIA
        or not all(
            np.isscalar(v)
            and not isinstance(v, (bool, np.bool_, str))
            and np.isfinite(v)
            for v in criteria.values()
        )
    ):
        raise ValueError(
            "Supply all six explicit finite recovery criteria, without unknown keys"
        )
    if (
        criteria["location_tolerance_m"] <= 0
        or criteria["model_relative_tolerance"] <= 0
        or not 0 <= criteria["support_dice_min"] <= 1
        or not 0 <= criteria["volume_relative_tolerance"] <= 1
        or not 0 <= criteria["contrast_relative_tolerance"] <= 1
        or not 0 < criteria["direction_tolerance_deg"] <= 180
        or not np.isfinite(support_fraction)
        or not 0 < support_fraction <= 1
    ):
        raise ValueError(
            "Invalid recovery tolerances, support fraction or connectivity radius"
        )
    if len(np.unique(xyz, axis=0)) != len(xyz):
        raise ValueError("Recovery metrics require distinct cell centers")
    if connectivity_edges is None:
        if (
            not isinstance(connectivity_radius_m, (int, float, np.integer, np.floating))
            or isinstance(connectivity_radius_m, (bool, np.bool_))
            or not np.isfinite(connectivity_radius_m)
            or connectivity_radius_m <= 0
        ):
            raise ValueError(
                "Supply a positive connectivity radius or explicit adjacency edges"
            )
        edges = None
    else:
        edges = as_array(connectivity_edges)
        if (
            connectivity_radius_m is not None
            or edges.ndim != 2
            or edges.shape[1] != 2
            or not np.issubdtype(edges.dtype, np.integer)
            or len(edges) > max_links
            or np.any(edges < 0)
            or np.any(edges >= len(xyz))
            or np.any(edges[:, 0] == edges[:, 1])
        ):
            raise ValueError(
                "Adjacency edges require bounded integer cell pairs within the link budget, without a radius"
            )

    def amplitudes(values):
        if not vector:
            return abs(values)
        scale = abs(values).max()
        return (
            np.linalg.norm(values / scale, axis=1) * scale
            if scale
            else np.zeros(len(values))
        )

    a, m = amplitudes(actual), amplitudes(model)
    if (
        not np.isfinite(volumes.sum())
        or not np.isfinite(a).all()
        or not np.isfinite(m).all()
    ):
        raise ValueError("Recovery arithmetic exceeds finite volume/amplitude range")
    if not np.any(a > 0):
        raise ValueError("Recovery scoring needs nonzero independent truth")
    threshold = float(support_fraction * a.max())
    true_support, predicted_support = a >= threshold, m >= threshold
    true_regions, true_count = _regions(
        xyz, true_support, volumes, connectivity_radius_m, max_links, canceled, edges
    )
    predicted_regions, predicted_count = _regions(
        xyz,
        predicted_support,
        volumes,
        connectivity_radius_m,
        max_links,
        canceled,
        edges,
    )
    if true_count > 64:
        raise ValueError("At most 64 truth components supported by the audit matcher")
    matched = []
    location = None
    if predicted_regions and len(predicted_regions) <= 64:
        costs = distance.cdist(
            np.array([r["centroid"] for r in true_regions]),
            np.array([r["centroid"] for r in predicted_regions]),
        )
        rows, cols = linear_sum_assignment(costs)
        location = float(costs[rows, cols].max())
        matched = [
            dict(
                truth_component=int(i),
                predicted_component=int(j),
                distance_m=float(costs[i, j]),
            )
            for i, j in zip(rows, cols)
        ]
    true_volume = float(volumes[true_support].sum())
    predicted_volume = float(volumes[predicted_support].sum())
    intersection = float(volumes[true_support & predicted_support].sum())
    dice = 2 * intersection / (true_volume + predicted_volume)
    scale = max(abs(actual).max(), abs(model).max())
    scaled_model, scaled_actual = model / scale, actual / scale
    delta = (
        np.sum((scaled_model - scaled_actual) ** 2, axis=1)
        if vector
        else (scaled_model - scaled_actual) ** 2
    )
    energy = np.sum(scaled_actual**2, axis=1) if vector else scaled_actual**2
    relative_volumes = volumes / volumes.max()
    model_error = float(
        np.sqrt(np.sum(relative_volumes * delta) / np.sum(relative_volumes * energy))
    )
    if not np.isfinite(model_error):
        raise ValueError("Recovery relative error exceeds finite arithmetic range")
    body_metrics = []
    direction_errors = []
    for i, region in enumerate(true_regions):
        if canceled is not None and canceled():
            raise InterruptedError("Model recovery assessment canceled")
        ix = region["indices"]
        weights = volumes[ix]
        true_contrast = float(np.average(a[ix], weights=weights))
        recovered_contrast = float(np.average(m[ix], weights=weights))
        item = dict(
            component=i,
            true_contrast=true_contrast,
            recovered_contrast=recovered_contrast,
            contrast_relative_error=abs(recovered_contrast - true_contrast)
            / true_contrast,
        )
        if vector:
            t = np.average(actual[ix], axis=0, weights=weights)
            r = np.average(model[ix], axis=0, weights=weights)
            nt, nr = float(amplitudes(t[None, :])[0]), float(amplitudes(r[None, :])[0])
            angle = (
                float(np.rad2deg(np.arccos(np.clip((t / nt) @ (r / nr), -1.0, 1.0))))
                if nt > 1e-12 * true_contrast and nr > 1e-12 * true_contrast
                else None
            )
            item["direction_error_deg"] = angle
            direction_errors.append(angle)
        else:
            item["polarity_correct"] = bool(
                np.sum((weights / weights.sum()) * scaled_actual[ix] * scaled_model[ix])
                > 0
            )
        body_metrics.append(item)
    contrast_error = max(r["contrast_relative_error"] for r in body_metrics)
    count_matches = predicted_count == true_count
    checks = dict(
        location=count_matches
        and location is not None
        and location <= criteria["location_tolerance_m"],
        volume=abs(predicted_volume - true_volume) / true_volume
        <= criteria["volume_relative_tolerance"],
        support=dice >= criteria["support_dice_min"],
        contrast=contrast_error <= criteria["contrast_relative_tolerance"],
        model=model_error <= criteria["model_relative_tolerance"],
    )
    if vector:
        checks["direction"] = all(
            v is not None and v <= criteria["direction_tolerance_deg"]
            for v in direction_errors
        )
    else:
        checks["polarity"] = all(r["polarity_correct"] for r in body_metrics)

    def effective_volume(amplitude):
        peak = amplitude.max()
        normalized = amplitude / peak if peak else amplitude
        denom = float(np.sum(normalized**2 * relative_volumes))
        return (
            float(np.sum(normalized * relative_volumes) ** 2 / denom * volumes.max())
            if denom > 0
            else 0.0
        )

    passed = bool(all(checks.values()))
    return dict(
        recovery_status="recovery_passed" if passed else "recovery_failed",
        recovery_passed=passed,
        checks={k: bool(v) for k, v in checks.items()},
        connectivity="explicit_cell_adjacency"
        if edges is not None
        else "center_distance_radius",
        failed_criteria=[k for k, v in checks.items() if not v],
        criteria={k: float(v) for k, v in criteria.items()},
        support_threshold=threshold,
        support_fraction=float(support_fraction),
        truth_component_count=true_count,
        predicted_component_count=predicted_count,
        matched_centroids=matched,
        maximum_location_error_m=location,
        true_volume_m3=true_volume,
        recovered_volume_m3=predicted_volume,
        volume_relative_error=abs(predicted_volume - true_volume) / true_volume,
        support_dice=dice,
        model_relative_error=model_error,
        maximum_contrast_relative_error=contrast_error,
        body_metrics=body_metrics,
        true_effective_volume_m3=effective_volume(a),
        recovered_effective_volume_m3=effective_volume(m),
        scope="Truth-based, declared-threshold validation; not a posterior or production prior",
    )

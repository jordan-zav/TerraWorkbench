"""Bounded planar semivariograms and local ordinary kriging.

Caller supplies projected metric coordinates and an explicit covariance model.
Nugget is microscale process variance, not an inferred measurement-error model.
No automatic variogram fitting, resampling or geological uncertainty claim.
"""

import numpy as np
from scipy.linalg import lu_factor, lu_solve
from scipy.spatial import cKDTree, distance

from ._array_contract import as_array
from ._calibration import integer_budget


def _points(coordinates, values):
    xy, z = as_array(coordinates, float), as_array(values, float)
    if (
        xy.ndim != 2
        or xy.shape[1] != 2
        or z.shape != (len(xy),)
        or len(xy) < 3
        or not np.isfinite(xy).all()
        or not np.isfinite(z).all()
    ):
        raise ValueError(
            "At least three finite planar points and aligned values required"
        )
    if len(np.unique(xy, axis=0)) != len(xy):
        raise ValueError("Duplicate coordinates require explicit prior aggregation")
    return xy, z


def empirical_variogram(
    coordinates,
    values,
    lag_edges_m,
    *,
    max_pairs=200_000,
    seed=0,
    azimuth_deg=None,
    angular_tolerance_deg=90.0,
    canceled=None,
):
    """Classical half-squared-difference lag means, complete or sampled pairs.

    For large surveys, sample independent uniform ordered distinct-index pairs
    with replacement. Repeated sampled pairs remain repeated draws; pair counts
    are not counts of independent data. Direction is axial, clockwise from north.
    No uncertainty from pair independence is fabricated. Bins are [left,right)
    except the final bin includes its right edge.
    """
    xy, z = _points(coordinates, values)
    integer_budget(max_pairs, "max_pairs")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    edges = as_array(lag_edges_m, float)
    if (
        edges.ndim != 1
        or len(edges) < 2
        or len(edges) > 1001
        or not np.isfinite(edges).all()
        or edges[0] < 0
        or np.any(np.diff(edges) <= 0)
    ):
        raise ValueError("Increasing finite nonnegative lag edges required")
    if (
        not np.isfinite(angular_tolerance_deg)
        or not 0 < angular_tolerance_deg <= 90
        or (azimuth_deg is not None and not np.isfinite(azimuth_deg))
    ):
        raise ValueError("Finite direction and angular tolerance in (0,90] required")
    if canceled is not None and canceled():
        raise InterruptedError("Variogram canceled")
    total = len(z) * (len(z) - 1) // 2
    if total <= max_pairs:
        i, j = np.triu_indices(len(z), 1)
        sampling = "all unordered distinct pairs"
    else:
        rng = np.random.default_rng(seed)
        i = rng.integers(0, len(z), max_pairs)
        j = rng.integers(0, len(z) - 1, max_pairs)
        j += j >= i
        sampling = "uniform ordered distinct-index pairs, with replacement"
    delta = xy[j] - xy[i]
    separation = np.linalg.norm(delta, axis=1)
    valid = (separation >= edges[0]) & (separation <= edges[-1])
    if azimuth_deg is not None:
        angle = np.rad2deg(np.arctan2(delta[:, 0], delta[:, 1]))
        difference = abs((angle - azimuth_deg + 90) % 180 - 90)
        valid &= difference <= angular_tolerance_deg
    bins = np.minimum(
        np.searchsorted(edges, separation[valid], side="right") - 1, len(edges) - 2
    )
    count = np.bincount(bins, minlength=len(edges) - 1)
    sums = np.bincount(
        bins, weights=0.5 * (z[j[valid]] - z[i[valid]]) ** 2, minlength=len(count)
    )
    lag_sum = np.bincount(bins, weights=separation[valid], minlength=len(count))
    if not np.isfinite(sums).all() or not np.isfinite(lag_sum).all():
        raise ValueError("Variogram arithmetic overflow; rescale values or coordinates")
    semivariance = np.divide(
        sums, count, out=np.full(len(count), np.nan), where=count > 0
    )
    mean_lag = np.divide(
        lag_sum, count, out=np.full(len(count), np.nan), where=count > 0
    )
    if canceled is not None and canceled():
        raise InterruptedError("Variogram canceled")
    return dict(
        lag_edges_m=edges,
        mean_lag_m=mean_lag,
        semivariance=semivariance,
        pair_count=count,
        recipe=dict(
            estimator="classical half squared differences",
            sampling=sampling,
            seed=int(seed),
            considered_pairs=len(i),
            possible_unordered_pairs=total,
            azimuth_deg=azimuth_deg,
            angular_tolerance_deg=angular_tolerance_deg,
            uncertainty="No independence-based error bars for shared/repeated pairs",
        ),
    )


def _gamma(separation, range_m, partial_sill, nugget, model):
    h = np.asarray(separation) / range_m
    if model == "spherical":
        bounded = np.minimum(h, 1.0)
        core = 1.5 * bounded - 0.5 * bounded**3
    elif model == "exponential":
        core = 1 - np.exp(-3 * h)
    else:
        core = 1 - np.exp(-3 * h * h)
    return np.where(separation == 0, 0.0, nugget + partial_sill * core)


def ordinary_kriging(
    coordinates,
    values,
    query_coordinates,
    range_m,
    partial_sill,
    nugget=0.0,
    *,
    model="spherical",
    neighbors=32,
    search_radius_m=0.0,
    maximum_condition=1e10,
    max_elements=10_000_000,
    max_systems=10_000,
    canceled=None,
):
    """Local ordinary kriging with declared parameters and conditional variance.

    partial_sill excludes nugget. Exponential/Gaussian range is the distance
    reaching 1-exp(-3) of the structured sill. An observed coordinate is an
    exact interpolation, including nugget; this is not nugget-error smoothing.
    A positive search radius leaves unsupported queries as NaN. A zero radius
    permits extrapolation, which is disclosed, not a confidence certificate.
    Shared neighborhoods reuse factorizations; distinct-system and element
    budgets prevent silently constructing a survey-size dense solve.
    """
    xy, z = _points(coordinates, values)
    query = as_array(query_coordinates, float)
    for value, name in (
        (neighbors, "neighbors"),
        (max_elements, "max_elements"),
        (max_systems, "max_systems"),
    ):
        integer_budget(value, name)
    if not 3 <= neighbors <= 128 or model not in (
        "spherical",
        "exponential",
        "gaussian",
    ):
        raise ValueError(
            "Choose spherical/exponential/gaussian model and 3..128 neighbors"
        )
    if (
        query.ndim != 2
        or query.shape[1] != 2
        or not len(query)
        or not np.isfinite(query).all()
    ):
        raise ValueError("Finite nonempty planar query coordinates required")
    if (
        not np.isfinite(
            [range_m, partial_sill, nugget, search_radius_m, maximum_condition]
        ).all()
        or range_m <= 0
        or partial_sill <= 0
        or nugget < 0
        or search_radius_m < 0
        or maximum_condition < 1
    ):
        raise ValueError(
            "Positive range/partial sill, nonnegative nugget/radius and condition >=1 required"
        )
    k = min(neighbors, len(z))
    if len(query) * k + 4 * (k + 1) ** 2 > max_elements:
        raise ValueError("Kriging element budget exceeded")
    if canceled is not None and canceled():
        raise InterruptedError("Kriging canceled")
    dist, indices = cKDTree(xy).query(query, k=k)
    support = dist <= search_radius_m if search_radius_m else np.ones(dist.shape, bool)
    # Sort each support set for neighborhood reuse; unsupported slots are -1.
    sets = np.sort(np.where(support, indices, -1), axis=1)
    unique, inverse = np.unique(sets, axis=0, return_inverse=True)
    if len(unique) > max_systems:
        raise ValueError("Distinct kriging system budget exceeded")
    prediction = np.full(len(query), np.nan)
    variance = np.full(len(query), np.nan)
    condition = np.full(len(query), np.nan)
    count = support.sum(axis=1)
    scale = partial_sill + nugget
    if not np.isfinite(scale):
        raise ValueError("Total sill arithmetic overflow")
    exact = dist[:, 0] == 0
    prediction[exact] = z[indices[exact, 0]]
    variance[exact] = 0.0
    condition[exact] = 1.0
    # Group once instead of scanning every query for every local system.
    order = np.argsort(inverse, kind="stable")
    boundaries = np.r_[0, np.cumsum(np.bincount(inverse, minlength=len(unique)))]
    for group, selection in enumerate(unique):
        if canceled is not None and canceled():
            raise InterruptedError("Kriging canceled")
        selection = selection[selection >= 0]
        if len(selection) < 3:
            continue
        rows = order[boundaries[group] : boundaries[group + 1]]
        rows = rows[~exact[rows]]
        if not len(rows):
            continue
        coords = xy[selection]
        matrix = np.ones((len(selection) + 1, len(selection) + 1))
        matrix[-1, -1] = 0.0
        matrix[:-1, :-1] = (
            _gamma(distance.cdist(coords, coords), range_m, partial_sill, nugget, model)
            / scale
        )
        cond = np.linalg.cond(matrix)
        if not np.isfinite(cond) or cond > maximum_condition:
            raise ValueError(
                "Kriging neighborhood is ill-conditioned; inspect variogram/sampling"
            )
        factor = lu_factor(matrix)
        # Bound RHS work even when a large query tile shares one neighborhood.
        for start in range(0, len(rows), 4096):
            if canceled is not None and canceled():
                raise InterruptedError("Kriging canceled")
            chosen = rows[start : start + 4096]
            gamma = _gamma(
                distance.cdist(coords, query[chosen]),
                range_m,
                partial_sill,
                nugget,
                model,
            )
            rhs = np.vstack([gamma / scale, np.ones(len(chosen))])
            weights = lu_solve(factor, rhs)
            prediction[chosen] = z[selection] @ weights[:-1]
            raw = np.sum(weights[:-1] * gamma, axis=0) + weights[-1] * scale
            tolerance = 1e-9 * scale
            if np.any(raw < -tolerance):
                raise ValueError("Negative kriging variance beyond roundoff")
            variance[chosen] = np.maximum(raw, 0.0)
            condition[chosen] = cond
    if np.isinf(prediction).any() or np.isinf(variance).any():
        raise ValueError("Kriging arithmetic overflow")
    return dict(
        predicted=prediction,
        variance=variance,
        neighbor_count=count,
        design_condition=condition,
        recipe=dict(
            method="local ordinary kriging",
            model=model,
            range_m=range_m,
            partial_sill=partial_sill,
            nugget=nugget,
            neighbors=k,
            search_radius_m=search_radius_m,
            distinct_neighborhoods=len(unique),
            coordinate_unit="projected metres",
            exact_at_observations=True,
            uncertainty="Conditional on fixed isotropic variogram and local constant mean; no parameter/CRS/geological uncertainty",
        ),
    )

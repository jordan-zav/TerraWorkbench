"""Paired-flight magnetic differences with explicit height and sampling support.

calculate_pair works on an already shared physical grid, with X/Y/Z point
coordinates in metres. Callers align rasters onto an explicit lattice first.
Values are (high field - low field) / (high height - low height), in nT/m.
Inputs must have compatible field baselines, height datums and magnetic units.
No site-specific heights, separation gates, sensors or grid sizes are selected.
The module is a processing API; it does not modify the GUI configuration.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class PairOptions:
    height_mode: str
    min_separation_m: float
    max_separation_m: float
    max_point_distance_m: float
    high_height_agl_m: float | None = None
    low_height_agl_m: float | None = None
    output_mode: str = "masked"
    confidence_threshold: float | None = None

    def __post_init__(self):
        if self.output_mode not in ("masked", "unmasked", "both"):
            raise ValueError("output_mode must be masked, unmasked or both")
        if self.confidence_threshold is not None and (
            not np.isfinite(self.confidence_threshold)
            or not 0 <= self.confidence_threshold <= 1
        ):
            raise ValueError("Confidence threshold must be between zero and one")
        if self.height_mode not in ("recorded_z", "dtm_nominal_z"):
            raise ValueError("height_mode must be recorded_z or dtm_nominal_z")
        values = (
            self.min_separation_m,
            self.max_separation_m,
            self.max_point_distance_m,
        )
        if not all(np.isfinite(v) for v in values):
            raise ValueError("Separation and support distances must be finite")
        if not 0 < self.min_separation_m <= self.max_separation_m:
            raise ValueError("Separation must be positive and ordered high minus low")
        if self.max_point_distance_m < 0:
            raise ValueError("Point distance cannot be negative")
        if self.height_mode == "dtm_nominal_z":
            if any(
                v is None or not np.isfinite(v)
                for v in (self.high_height_agl_m, self.low_height_agl_m)
            ):
                raise ValueError("Both nominal sensor heights are required")
            if self.high_height_agl_m <= self.low_height_agl_m:
                raise ValueError("High nominal height must exceed low nominal height")


@dataclass
class PairResult:
    gradient: np.ndarray
    delta_field: np.ndarray
    delta_height: np.ndarray
    mask: np.ndarray
    high_point_distance: np.ndarray
    low_point_distance: np.ndarray
    metadata: dict
    gradient_unmasked: np.ndarray | None = None
    gradient_masked: np.ndarray | None = None
    geometry_mask: np.ndarray | None = None
    confidence: np.ndarray | None = None


def calculate_pair(
    high,
    low,
    centers_xy,
    high_points,
    low_points,
    options,
    *,
    dtm=None,
    confidence=None,
):
    """Return masked differences on one shared grid; never alter input arrays.

    Point arrays contain X, Y and recorded Z (metres) for recorded_z, or X/Y
    for dtm_nominal_z. Supply explicitly selected sensors before calling.
    Invalid point coordinates are excluded. Recorded-Z mode also excludes
    missing heights before finding the nearest sample, matching the historical
    survey workflow. DTM mode requires finite terrain at the comparison cell.
    """
    high, low = np.asarray(high), np.asarray(low)
    if high.ndim != 2 or high.shape != low.shape:
        raise ValueError("High and low fields must share a two-dimensional grid")
    xy = np.asarray(centers_xy, dtype=float)
    if xy.shape != (high.size, 2) or not np.isfinite(xy).all():
        raise ValueError("Provide finite X/Y coordinates for every grid cell")
    nearest = []
    for points in (high_points, low_points):
        points = np.asarray(points, dtype=float)
        required = 3 if options.height_mode == "recorded_z" else 2
        if points.ndim != 2 or points.shape[1] < required:
            raise ValueError(
                "Point coordinates do not include the required X/Y/Z columns"
            )
        points = points[np.isfinite(points[:, :required]).all(axis=1)]
        if not len(points):
            raise ValueError("Each flight requires at least one valid sample point")
        distances, ids = cKDTree(points[:, :2]).query(xy)
        nearest.append((distances.reshape(high.shape), points, ids))
    hd, hp, hi = nearest[0]
    ld, lp, li = nearest[1]
    support = np.isfinite(high) & np.isfinite(low)
    support &= (hd <= options.max_point_distance_m) & (
        ld <= options.max_point_distance_m
    )
    if options.height_mode == "recorded_z":
        dz = (hp[hi, 2] - lp[li, 2]).reshape(high.shape)
    else:
        terrain = np.asarray(dtm) if dtm is not None else np.asarray([])
        if terrain.shape != high.shape:
            raise ValueError("DTM must share the comparison grid")
        # Subtracting the nominal heights avoids cancellation in large elevations.
        dz = np.full(high.shape, options.high_height_agl_m - options.low_height_agl_m)
        support &= np.isfinite(terrain)
    mask = support & np.isfinite(dz)
    mask &= (dz >= options.min_separation_m) & (dz <= options.max_separation_m)
    geometry_mask = mask.copy()
    confidence_array = None
    if confidence is not None:
        confidence_array = np.asarray(confidence, dtype=float)
        if confidence_array.shape != high.shape or np.isinf(confidence_array).any():
            raise ValueError(
                "Confidence must share the grid and contain zero-to-one scores or missing values"
            )
        finite = np.isfinite(confidence_array)
        if ((confidence_array[finite] < 0) | (confidence_array[finite] > 1)).any():
            raise ValueError("Confidence values must be between zero and one")
        confidence_array = confidence_array.copy()
    if options.confidence_threshold is not None:
        if confidence_array is None:
            raise ValueError("A confidence grid is required for a confidence threshold")
        mask &= np.isfinite(confidence_array) & (
            confidence_array >= options.confidence_threshold
        )
    dt = high.astype(float) - low.astype(float)
    physical = np.isfinite(high) & np.isfinite(low) & np.isfinite(dz) & (dz > 0)
    if options.height_mode == "dtm_nominal_z":
        physical &= np.isfinite(terrain)
    raw = np.full(high.shape, np.nan)
    np.divide(dt, dz, out=raw, where=physical)
    masked = np.where(mask, raw, np.nan)
    gradient = raw.copy() if options.output_mode == "unmasked" else masked.copy()
    histogram = separation_histogram(
        dz, support, minimum=options.min_separation_m, maximum=options.max_separation_m
    )
    metadata = {
        "separation_histogram": histogram,
        "method": "paired-flight-1",
        "formula": "(high_field-low_field)/(high_height-low_height)",
        "units": "nT/m",
        "options": asdict(options),
        "accepted_cells": int(mask.sum()),
        "common_field_cells": int((np.isfinite(high) & np.isfinite(low)).sum()),
        "point_support_cells": int(support.sum()),
        "geometry_accepted_cells": int(geometry_mask.sum()),
        "unmasked_cells": int(np.isfinite(raw).sum()),
        "mask_kind": "geometry gates plus optional supplied confidence threshold",
        "confidence_generated": False,
        "invalid_height_policy": "missing, zero or reversed separation remains nodata in every output",
        "high_valid_points": len(hp),
        "low_valid_points": len(lp),
    }
    return PairResult(
        gradient,
        np.where(mask, dt, np.nan),
        np.where(mask, dz, np.nan),
        mask,
        hd,
        ld,
        metadata,
        raw,
        masked,
        geometry_mask,
        confidence_array,
    )


def fuse_directions(ns, ew):
    """Equal NS/EW mean: strict requires both; union retains single-direction cells.

    Both arrays must already occupy the same physical lattice. Count is 0/1/2;
    source code is 0 none, 1 NS only, 2 EW only, 3 both.
    """
    ns, ew = np.asarray(ns), np.asarray(ew)
    if ns.ndim != 2 or ns.shape != ew.shape:
        raise ValueError("Direction grids must have identical shapes and geometry")
    n, e = np.isfinite(ns), np.isfinite(ew)
    both = n & e
    strict = np.full(ns.shape, np.nan, dtype=float)
    strict[both] = (ns[both].astype(float) + ew[both].astype(float)) / 2
    union = strict.copy()
    union[n & ~e] = ns[n & ~e]
    union[e & ~n] = ew[e & ~n]
    return {
        "strict": strict,
        "union": union,
        "count": n.astype("uint8") + e.astype("uint8"),
        "source_code": n.astype("uint8") + 2 * e.astype("uint8"),
    }


def _metric_crs(crs):
    from pyproj import CRS

    parsed = CRS.from_user_input(crs)
    if not parsed.is_projected or any(
        abs(a.unit_conversion_factor - 1) > 1e-12 for a in parsed.axis_info[:2]
    ):
        raise ValueError(
            "Pair calculations require a projected CRS with metre coordinates"
        )
    return parsed


def _centers(transform, shape):
    row, col = np.indices(shape)
    x, y = transform * (col.ravel() + 0.5, row.ravel() + 0.5)
    return np.column_stack((x, y))


def _aligned(path, transform, shape, crs):
    import rasterio
    from rasterio.warp import reproject, Resampling

    with rasterio.open(path) as source:
        if source.crs is None:
            raise ValueError("Every raster needs its CRS")
        array = source.read(1, masked=True).astype("float32").filled(np.nan)
        array[~np.isfinite(array)] = np.nan
        result = np.full(shape, np.nan, dtype="float32")
        reproject(
            array,
            result,
            src_transform=source.transform,
            src_crs=source.crs,
            src_nodata=np.nan,
            dst_transform=transform,
            dst_crs=crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
    return result


def separation_histogram(delta_height, support, *, minimum=None, maximum=None, bins=40):
    """Distribution before vertical/confidence gates, one observation per supported cell.

    The sampled heights are those used by calculate_pair. Repeated nearest samples
    are counted once for each comparison cell; this is not a histogram of unique
    instrument readings. Median is descriptive, not an inferred acquisition height.
    """
    dz = np.asarray(delta_height, dtype=float)
    valid = np.asarray(support, dtype=bool)
    if dz.shape != valid.shape:
        raise ValueError("Height separation and support must have the same shape")
    if (
        isinstance(bins, bool)
        or not isinstance(bins, (int, np.integer))
        or not 1 <= bins <= 200
    ):
        raise ValueError("Histogram bins must be an integer from 1 to 200")
    if (minimum is None) != (maximum is None):
        raise ValueError("Supply both separation limits or neither")
    if minimum is not None and (
        not np.isfinite([minimum, maximum]).all() or not 0 < minimum <= maximum
    ):
        raise ValueError("Separation limits must be finite, positive and ordered")
    vals = dz[valid & np.isfinite(dz)]
    accepted = (
        np.ones(len(vals), dtype=bool)
        if minimum is None
        else (vals >= minimum) & (vals <= maximum)
    )
    counts, edges = np.histogram(vals, bins=int(bins))
    inside, _ = np.histogram(vals[accepted], bins=edges)
    positive = vals[vals > 0]
    quantiles = (
        np.percentile(vals, [5, 25, 50, 75, 95]).tolist() if len(vals) else [None] * 5
    )
    return {
        "units": "m",
        "grain": "shared-grid cells with horizontal sample support before vertical and confidence gates",
        "bin_edges_m": edges.tolist(),
        "counts": counts.tolist(),
        "inside_limits_counts": inside.tolist(),
        "outside_limits_counts": (counts - inside).tolist(),
        "supported_cells": int(len(vals)),
        "inside_limits_cells": int(accepted.sum()),
        "nonpositive_cells": int((vals <= 0).sum()),
        "minimum_m": minimum,
        "maximum_m": maximum,
        "p05_m": quantiles[0],
        "p25_m": quantiles[1],
        "median_m": quantiles[2],
        "p75_m": quantiles[3],
        "p95_m": quantiles[4],
        "positive_median_m": float(np.median(positive)) if len(positive) else None,
        "nominal_inferred": False,
    }


def match_point_profiles(
    high_points, low_points, max_distance_m, *, minimum=None, maximum=None
):
    """Diagnostic nearest-XY pairing, upper samples as references, preserving row order.

    Caller selects a traverse/sensor from each survey in a common metric CRS.
    Many upper samples may use the same lower sample. This is not a one-to-one
    assignment and does not replace calculate_pair's grid-centre support gates.
    """
    high = np.asarray(high_points, dtype=float)
    low = np.asarray(low_points, dtype=float)
    if any(p.ndim != 2 or p.shape[1] != 3 or not len(p) for p in (high, low)):
        raise ValueError("Provide nonempty X/Y/Z arrays for both selected profiles")
    if not np.isfinite(max_distance_m) or max_distance_m < 0:
        raise ValueError("Horizontal pair distance must be finite and nonnegative")
    if (minimum is None) != (maximum is None) or (
        minimum is not None
        and (not np.isfinite([minimum, maximum]).all() or not 0 < minimum <= maximum)
    ):
        raise ValueError("Supply both finite ordered positive height limits or neither")
    hv = np.isfinite(high).all(axis=1)
    lv = np.isfinite(low).all(axis=1)
    lower_ids = np.flatnonzero(lv)
    upper_ids = np.flatnonzero(hv)
    distances = np.full(len(high), np.nan)
    candidate = np.full(len(high), -1, dtype=int)
    if len(lower_ids) and len(upper_ids):
        d, i = cKDTree(low[lv, :2]).query(high[hv, :2])
        distances[upper_ids] = d
        candidate[upper_ids] = lower_ids[i]
    paired = (candidate >= 0) & (distances <= max_distance_m)
    lower_z = np.full(len(high), np.nan)
    lower_z[paired] = low[candidate[paired], 2]
    dz = high[:, 2] - lower_z
    accepted = paired & (dz > 0)
    if minimum is not None:
        accepted &= (dz >= minimum) & (dz <= maximum)
    steps = np.linalg.norm(np.diff(high[:, :2], axis=0), axis=1)
    # Missing coordinates break the line and add no assumed travel distance.
    distance = np.r_[0.0, np.cumsum(np.where(np.isfinite(steps), steps, 0.0))]
    used = np.unique(candidate[paired])
    lower_paired = np.zeros(len(low), dtype=bool)
    lower_paired[used] = True
    return dict(
        high_points=high.copy(),
        low_points=low.copy(),
        distance_m=distance,
        candidate_low_index=candidate,
        paired_low_index=np.where(paired, candidate, -1),
        horizontal_distance_m=distances,
        paired=paired,
        accepted=accepted,
        lower_z=lower_z,
        delta_height_m=dz,
        lower_paired=lower_paired,
        minimum_m=minimum,
        maximum_m=maximum,
        max_distance_m=float(max_distance_m),
        metadata=dict(
            method="point-profile-nearest-xy-1",
            high_points=len(high),
            low_points=len(low),
            paired_points=int(paired.sum()),
            accepted_points=int(accepted.sum()),
            unpaired_high_points=int((~paired).sum()),
            unpaired_low_points=int((~lower_paired).sum()),
            reused_lower_samples=int(paired.sum() - len(used)),
            matching="upper-to-nearest-lower; many-to-one allowed",
            distance_axis="upper profile acquisition row order",
            gradient_modified=False,
        ),
    )


def profile_tolerance_summary(result, nominal_m, percentages=(10, 20, 30)):
    """Compare vertical gates on unchanged XY pairs; never update processing options."""
    if not np.isfinite(nominal_m) or nominal_m <= 0:
        raise ValueError("Nominal separation must be finite and positive")
    paired = np.asarray(result["paired"], dtype=bool)
    dz = np.asarray(result["delta_height_m"], dtype=float)
    if paired.shape != dz.shape:
        raise ValueError("Pairs and separations must share a shape")
    denominator = int(paired.sum())
    rows = []
    for percent in percentages:
        if not np.isfinite(percent) or not 0 <= percent < 100:
            raise ValueError(
                "Tolerance percentages must be finite from zero to less than 100"
            )
        lo, hi = nominal_m * (1 - percent / 100), nominal_m * (1 + percent / 100)
        count = int(
            (paired & np.isfinite(dz) & (dz >= lo) & (dz <= hi) & (dz > 0)).sum()
        )
        rows.append(
            dict(
                tolerance_percent=float(percent),
                nominal_m=float(nominal_m),
                minimum_m=float(lo),
                maximum_m=float(hi),
                accepted_points=count,
                xy_paired_points=denominator,
                accepted_percent_of_xy_pairs=100 * count / denominator
                if denominator
                else None,
            )
        )
    return rows


def horizontal_pair_summary(result, increases=(0, 20, 30)):
    """Review wider XY limits using all nearest candidates, including current unpaired.

    Vertical limits are kept fixed. Counts do not mutate selected pairing, arrays
    or masks, and are scoped to the selected upper/lower profiles.
    """
    base = result["max_distance_m"]
    if not np.isfinite(base) or base < 0:
        raise ValueError("Horizontal limit must be finite and nonnegative")
    ids = np.asarray(result["candidate_low_index"], dtype=int)
    d = np.asarray(result["horizontal_distance_m"], dtype=float)
    high = np.asarray(result["high_points"])
    low = np.asarray(result["low_points"])
    if ids.shape != d.shape or len(ids) != len(high):
        raise ValueError("Candidate arrays must match upper samples")
    valid = (ids >= 0) & (ids < len(low)) & np.isfinite(d)
    delta = np.full(len(high), np.nan)
    delta[valid] = high[valid, 2] - low[ids[valid], 2]
    rows = []
    for increase in increases:
        if not np.isfinite(increase) or increase < 0:
            raise ValueError("Horizontal increases must be finite and nonnegative")
        limit = base * (1 + increase / 100)
        paired = valid & (d <= limit)
        accepted = paired & np.isfinite(delta) & (delta > 0)
        if result["minimum_m"] is not None:
            accepted &= (delta >= result["minimum_m"]) & (delta <= result["maximum_m"])
        count = int(paired.sum())
        used = len(np.unique(ids[paired]))
        rows.append(
            dict(
                increase_percent=float(increase),
                horizontal_limit_m=float(limit),
                xy_paired_points=count,
                percent_of_upper_points=100 * count / len(high) if len(high) else None,
                unpaired_high_points=int(len(high) - count),
                unpaired_low_points=int(len(low) - used),
                accepted_with_vertical_limits=int(accepted.sum()),
            )
        )
    return rows


def point_pair_tolerance_matrix(
    result, nominal_m, *, increases=(0, 20, 30), percentages=(10, 20, 30)
):
    """Matrix for selected raw profiles, not shared raster cells; review only."""
    vertical = profile_tolerance_summary(result, nominal_m, percentages)
    rows = []
    for v in vertical:
        review = dict(result, minimum_m=v["minimum_m"], maximum_m=v["maximum_m"])
        for h in horizontal_pair_summary(review, increases):
            rows.append(
                dict(
                    h,
                    vertical_tolerance_percent=v["tolerance_percent"],
                    minimum_m=v["minimum_m"],
                    maximum_m=v["maximum_m"],
                )
            )
    return dict(
        nominal_m=float(nominal_m),
        upper_points=len(result["high_points"]),
        lower_points=len(result["low_points"]),
        horizontal_increases_percent=list(increases),
        vertical_percentages=list(percentages),
        rows=rows,
        grain="selected upper-profile XYZ samples",
        active_pairing_changed=False,
    )

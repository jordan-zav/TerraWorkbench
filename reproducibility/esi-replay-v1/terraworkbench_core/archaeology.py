"""Native, auditable multiscale survey exploration and feature retention.

Coordinates supplied to array APIs are projected metres. Maps retain source row
order and finite support. Connected regions are thresholded magnetic features;
they carry no age or archaeological classification.
"""

from __future__ import annotations

import csv
import json
import hashlib
from pathlib import Path
import numpy as np
from scipy import ndimage

MAX_CELLS = 4_000_000
MAX_FEATURES = 10_000


def _check(canceled):
    if canceled and canceled():
        raise InterruptedError("Archaeology analysis canceled.")


def _validate(grid, transform):
    input_mask = np.ma.getmaskarray(grid) if np.ma.isMaskedArray(grid) else None
    raw = np.asarray(grid)
    if raw.dtype.kind not in "iuf" or raw.ndim != 2 or raw.size == 0:
        raise ValueError("A nonempty, real, two-dimensional grid is required.")
    if raw.size > MAX_CELLS:
        raise ValueError("Analysis exceeds 4 million grid cells.")
    a, b, c, d, e, f = tuple(transform)[:6]
    if (
        not np.isfinite([a, b, c, d, e, f]).all()
        or a <= 0
        or e >= 0
        or b != 0
        or d != 0
    ):
        raise ValueError("Use a north-up, unrotated transform in projected metres.")
    grid = raw.astype(np.float64, copy=True)
    if input_mask is not None:
        grid[input_mask] = np.nan
    grid[~np.isfinite(grid)] = np.nan
    if not np.isfinite(grid).any():
        raise ValueError("The grid has no finite measurements.")
    return grid, float(a), float(-e)


def _threshold(value):
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError("Detection threshold must be a finite positive nT value.")
    return value


def _integer(value, name, limit):
    number = int(value)
    if isinstance(value, bool) or number != value or number < 1 or number > limit:
        raise ValueError(f"{name} must be an integer between 1 and {limit}.")
    return number


def _xy(row, col, transform):
    a, _, c, _, e, f = tuple(transform)[:6]
    return float(c + (col + 0.5) * a), float(f + (row + 0.5) * e)


def _catalog(
    grid,
    transform,
    threshold,
    min_cells,
    max_features,
    canceled=None,
    return_labels=False,
):
    """Catalogue separate positive and negative lobes using eight-neighbour cells."""
    valid = np.isfinite(grid)
    boundary = valid & ~ndimage.binary_erosion(valid, border_value=0)
    rows = []
    feature_labels = np.zeros(grid.shape, dtype=np.int32) if return_labels else None
    cell_area = abs(tuple(transform)[0] * tuple(transform)[4])
    omitted = 0
    for sign in (1, -1):
        _check(canceled)
        labels, count = ndimage.label(
            valid & (sign * grid >= threshold), structure=np.ones((3, 3))
        )
        boxes = ndimage.find_objects(labels)
        for label_id, box in enumerate(boxes, 1):
            if label_id % 128 == 0:
                _check(canceled)
            local = labels[box] == label_id
            n = int(local.sum())
            if n < min_cells:
                continue
            if len(rows) >= max_features:
                omitted += 1
                continue
            rr, cc = np.where(local)
            rr, cc = rr + box[0].start, cc + box[1].start
            if return_labels:
                feature_labels[rr, cc] = len(rows) + 1
            values = grid[rr, cc]
            weights = np.abs(values)
            # Normalise weights before summation to avoid overflow.
            weights = weights / weights.max()
            row = float(np.average(rr, weights=weights))
            col = float(np.average(cc, weights=weights))
            peak = int(np.argmax(sign * values))
            x, y = _xy(row, col, transform)
            px, py = _xy(int(rr[peak]), int(cc[peak]), transform)
            rows.append(
                dict(
                    id=len(rows) + 1,
                    polarity="positive" if sign == 1 else "negative",
                    x_m=x,
                    y_m=y,
                    peak_x_m=px,
                    peak_y_m=py,
                    peak_nt=float(values[peak]),
                    mean_nt=float(
                        np.mean(values / np.max(np.abs(values)))
                        * np.max(np.abs(values))
                    ),
                    cells=n,
                    area_m2=n * cell_area,
                    equivalent_diameter_m=float(2 * np.sqrt(n * cell_area / np.pi)),
                    touches_support_boundary=bool(boundary[rr, cc].any()),
                    row_min=int(rr.min()),
                    row_max=int(rr.max()),
                    col_min=int(cc.min()),
                    col_max=int(cc.max()),
                )
            )
    return (rows, omitted, feature_labels) if return_labels else (rows, omitted)


def catalogue_anomalies(
    grid,
    transform,
    *,
    threshold_nt,
    min_cells=3,
    max_features=MAX_FEATURES,
    canceled=None,
):
    """Return signed connected features above an explicit absolute nT threshold.

    Threshold applies to the provided grid values: use a residual map when the
    input contains the Earth's field. Positive/negative lobes remain separate.
    Diameter is the diameter of a circle with the same thresholded area; it is
    not a fitted source width. Boundary flags include holes in survey support.
    """
    _check(canceled)
    data, _, _ = _validate(grid, transform)
    threshold = _threshold(threshold_nt)
    minimum = _integer(min_cells, "min_cells", MAX_CELLS)
    maximum = _integer(max_features, "max_features", MAX_FEATURES)
    features, omitted = _catalog(data, transform, threshold, minimum, maximum, canceled)
    _check(canceled)
    return dict(
        features=features,
        omitted_features=omitted,
        threshold_nt=threshold,
        connectivity=8,
        units="nT",
        valid_cells=int(np.isfinite(data).sum()),
    )


def analyze_grid(
    grid,
    transform,
    *,
    scales_metres=(0.5, 1.0, 2.0, 4.0),
    threshold_nt,
    min_cells=3,
    max_features=MAX_FEATURES,
    canceled=None,
):
    """Return Gaussian backgrounds, residuals, signed catalogues and persistence.

    Each scale is Gaussian sigma in metres, not kernel width. Mask-normalised
    smoothing uses reflected outer edges and a four-sigma footprint. A residual
    is input minus its local background. Both maps keep the original mask.
    Persistence counts scales containing a same-polarity thresholded feature
    sharing thresholded cells with each catalogue feature. It is a reproducible
    detection measure, not a probability or archaeological interpretation.
    Catalogue anchors include coarse-only features. Each anchor uses the first
    scale where its region occurs. Broader matched lobes do not replace finer
    anchors; geometries remain available separately in each scale catalogue.
    Return: scale_maps list [{sigma_m, background, residual, features, ...}],
    catalogue (all-scale anchors with persistence), and metadata. Arrays are float64.
    """
    _check(canceled)
    data, dx, dy = _validate(grid, transform)
    threshold = _threshold(threshold_nt)
    minimum = _integer(min_cells, "min_cells", MAX_CELLS)
    maximum = _integer(max_features, "max_features", MAX_FEATURES)
    scales = sorted(set(float(s) for s in scales_metres))
    if not 1 <= len(scales) <= 8 or not all(np.isfinite(s) and s > 0 for s in scales):
        raise ValueError(
            "Provide one to eight finite positive Gaussian scales in metres."
        )
    if data.size * len(scales) > 16_000_000:
        raise ValueError("Combined analysis exceeds 16 million scale cells.")
    if max(scales) / min(dx, dy) > 256:
        raise ValueError("A Gaussian scale cannot exceed 256 grid cells.")
    valid = np.isfinite(data)
    filled = np.where(valid, data, 0.0)
    # Scale the convolution for large finite values; normalized sum <= 1.
    magnitude = float(np.max(np.abs(data[valid])))
    normalized = filled / magnitude if magnitude else filled
    output = []
    for sigma in scales:
        _check(canceled)
        kernel = (sigma / dy, sigma / dx)
        weight = ndimage.gaussian_filter(
            valid.astype(float), kernel, mode="reflect", truncate=4.0
        )
        smooth = ndimage.gaussian_filter(
            normalized, kernel, mode="reflect", truncate=4.0
        )
        background = np.full(data.shape, np.nan)
        background[valid] = smooth[valid] / weight[valid] * magnitude
        with np.errstate(over="ignore", invalid="ignore"):
            residual = data - background
        if not np.isfinite(residual[valid]).all():
            raise ValueError("Residual values exceed finite numerical range.")
        features, omitted, labels = _catalog(
            residual, transform, threshold, minimum, maximum, canceled, True
        )
        output.append(
            dict(
                sigma_m=sigma,
                background=background,
                residual=residual,
                features=features,
                omitted_features=omitted,
                feature_labels=labels,
            )
        )
    anchors = []
    for source_index, level in enumerate(output):
        _check(canceled)
        for feature in level["features"]:
            r0, r1, c0, c1 = (
                feature[key] for key in ("row_min", "row_max", "col_min", "col_max")
            )
            box = np.s_[r0 : r1 + 1, c0 : c1 + 1]
            footprint = level["feature_labels"][box] == feature["id"]
            has_earlier_match = False
            for prior in output[:source_index]:
                ids = np.unique(prior["feature_labels"][box][footprint])
                if any(
                    i and prior["features"][i - 1]["polarity"] == feature["polarity"]
                    for i in ids
                ):
                    has_earlier_match = True
                    break
            if not has_earlier_match:
                anchors.append((source_index, feature))
    catalogue = []
    for source_index, feature in anchors[:maximum]:
        _check(canceled)
        r0, r1, c0, c1 = (
            feature[key] for key in ("row_min", "row_max", "col_min", "col_max")
        )
        box = np.s_[r0 : r1 + 1, c0 : c1 + 1]
        footprint = output[source_index]["feature_labels"][box] == feature["id"]
        matching = []
        for level in output:
            ids = np.unique(level["feature_labels"][box][footprint])
            if any(
                i and level["features"][i - 1]["polarity"] == feature["polarity"]
                for i in ids
            ):
                matching.append(level["sigma_m"])
        catalogue.append(
            dict(
                feature,
                id=len(catalogue) + 1,
                anchor_sigma_m=output[source_index]["sigma_m"],
                persistent_scales=matching,
                persistence_count=len(matching),
                persistence_fraction=len(matching) / len(output),
            )
        )
    _check(canceled)
    return dict(
        scale_maps=output,
        catalogue=catalogue,
        metadata=dict(
            units="nT",
            sigma_metres=scales,
            threshold_nt=threshold,
            min_cells=minimum,
            valid_cells=int(valid.sum()),
            persistence_rule="same-polarity thresholded component overlap",
            omitted_catalogue_anchors=max(0, len(anchors) - maximum),
            mask_policy="original finite support",
            gaussian_mode="reflect",
            gaussian_truncate=4.0,
        ),
    )


def _read_magnetic(path):
    import rasterio
    from .process_effect import _units

    with rasterio.open(path) as src:
        if src.width * src.height > MAX_CELLS:
            raise ValueError("Analysis exceeds 4 million grid cells.")
        if (
            not src.crs
            or not src.crs.is_projected
            or not np.isclose(src.crs.linear_units_factor[1], 1.0)
        ):
            raise ValueError("A projected CRS with metre coordinates is required.")
        if _units(src) != "nT":
            raise ValueError("Magnetic analysis requires explicit nT unit metadata.")
        if np.dtype(src.dtypes[0]).kind not in "iuf":
            raise ValueError("A real numerical magnetic grid is required.")
        data = src.read(1, masked=True).astype(float).filled(np.nan)
        return data, src.transform, src.crs


def _file_hash(path, canceled=None):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            _check(canceled)
            digest.update(chunk)
    return digest.hexdigest()


def analyze_geotiff(path, *, canceled=None, **settings):
    """Read an nT GeoTIFF in a projected metre CRS, then run analyze_grid."""
    _check(canceled)
    initial_hash = _file_hash(path, canceled)
    data, transform, crs = _read_magnetic(path)
    if _file_hash(path, canceled) != initial_hash:
        raise ValueError("Source grid changed during reading.")
    result = analyze_grid(data, transform, canceled=canceled, **settings)
    result.update(
        transform=transform,
        crs=crs.to_string(),
        source_path=str(Path(path).resolve()),
        source_sha256=initial_hash,
    )
    result["metadata"]["source_sha256"] = initial_hash
    return result


def _measure(data, transform, sign, threshold, supported, dominant_scope=None):
    """Measure common-support feature amplitude, half-height area and continuity."""
    values = np.where(supported, sign * data, -np.inf)
    row, col = np.unravel_index(np.argmax(values), values.shape)
    peak = float(values[row, col])
    active = supported & (sign * data >= threshold)
    labels, count = ndimage.label(active, structure=np.ones((3, 3)))
    areas = np.bincount(labels.ravel())[1:]
    active_count = int(active.sum())
    half = (
        supported & (sign * data >= peak * 0.5)
        if peak > 0
        else np.zeros(data.shape, bool)
    )
    half_labels, _ = ndimage.label(half, structure=np.ones((3, 3)))
    peak_label = half_labels[row, col]
    half_cells = int((half_labels == peak_label).sum()) if peak_label else 0
    area = abs(tuple(transform)[0] * tuple(transform)[4])
    dominant_support = (
        supported if dominant_scope is None else supported & dominant_scope
    )
    if dominant_support.any():
        absolute = np.where(dominant_support, np.abs(data), -np.inf)
        dominant_row, dominant_col = np.unravel_index(np.argmax(absolute), data.shape)
        dominant_peak = float(data[dominant_row, dominant_col])
    else:
        dominant_peak = None
    return dict(
        dominant_peak_nt=dominant_peak,
        same_polarity_detected=bool(active_count),
        peak_nt=sign * peak,
        peak_row=int(row),
        peak_col=int(col),
        half_height_diameter_m=float(2 * np.sqrt(half_cells * area / np.pi)),
        threshold_cells=active_count,
        largest_component_fraction=float(areas.max() / active_count)
        if active_count
        else 0.0,
        component_count=int(count),
    )


def compare_feature_retention(
    before,
    after,
    transform,
    *,
    features=None,
    threshold_nt,
    min_cells=3,
    padding_metres=2.0,
    reference_labels=None,
    canceled=None,
):
    """Compare anchored reference lobes on common support, without resampling.

    features accepts catalogue dictionaries containing polarity and inclusive
    row_min/max,col_min/max. When absent, catalogue_anomalies identifies before
    lobes above threshold_nt. Expand each reference box by padding_metres and
    compare extrema, half-height equivalent diameter, and fragmentation at the
    same absolute threshold. Before/after grids must already share geometry and
    nT units. Lost support is reported independently, not filled for comparison.
    Half-height diameter uses the connected half-peak region containing the peak.
    Continuity is largest threshold component / all thresholded cells in the box.
    Dominant amplitude and polarity reversal refer to the unpadded reference box.
    Loss of the original polarity is tested on its original threshold footprint.
    reference_labels optionally supplies a grid of exact catalogue component IDs.
    A missing same-polarity detection has no reported peak displacement.
    """
    _check(canceled)
    a, dx, dy = _validate(before, transform)
    b, _, _ = _validate(after, transform)
    if a.shape != b.shape:
        raise ValueError("Feature comparison requires equal grid shapes.")
    threshold = _threshold(threshold_nt)
    padding = float(padding_metres)
    if not np.isfinite(padding) or padding < 0:
        raise ValueError("Padding must be a finite nonnegative metre distance.")
    if features is None:
        minimum = _integer(min_cells, "min_cells", MAX_CELLS)
        features, _, reference_labels = _catalog(
            a, transform, threshold, minimum, MAX_FEATURES, canceled, True
        )
    if reference_labels is not None:
        reference_labels = np.asarray(reference_labels)
        if reference_labels.shape != a.shape or reference_labels.dtype.kind not in "iu":
            raise ValueError(
                "Reference labels require an integer grid matching the source shape."
            )
    features = list(features)
    if len(features) > MAX_FEATURES:
        raise ValueError("Feature comparison exceeds 10000 features.")
    results = []
    for index, feature in enumerate(features):
        _check(canceled)
        if feature.get("polarity") not in ("positive", "negative"):
            raise ValueError("Feature polarity must be positive or negative.")
        bounds = []
        for key, limit in (
            ("row_min", a.shape[0]),
            ("row_max", a.shape[0]),
            ("col_min", a.shape[1]),
            ("col_max", a.shape[1]),
        ):
            value = feature[key]
            integer = int(value)
            if integer != value or integer < 0 or integer >= limit:
                raise ValueError("Feature bounds must be integer source-grid indices.")
            bounds.append(integer)
        r0, r1, c0, c1 = bounds
        if r0 > r1 or c0 > c1:
            raise ValueError("Feature bounds are reversed.")
        reference_bounds = (r0, r1, c0, c1)
        rp, cp = int(np.ceil(padding / dy)), int(np.ceil(padding / dx))
        r0, r1 = max(0, r0 - rp), min(a.shape[0] - 1, r1 + rp)
        c0, c1 = max(0, c0 - cp), min(a.shape[1] - 1, c1 + cp)
        aa, bb = a[r0 : r1 + 1, c0 : c1 + 1], b[r0 : r1 + 1, c0 : c1 + 1]
        valid_a, valid_b = np.isfinite(aa), np.isfinite(bb)
        common = valid_a & valid_b
        record = dict(
            id=feature.get("id", index + 1),
            polarity=feature["polarity"],
            reference_cells=int(valid_a.sum()),
            common_cells=int(common.sum()),
            lost_support_cells=int((valid_a & ~valid_b).sum()),
            support_retention_fraction=float(common.sum() / valid_a.sum())
            if valid_a.any()
            else 0.0,
        )
        if common.any():
            sign = 1 if feature["polarity"] == "positive" else -1
            dominant_scope = np.zeros(common.shape, dtype=bool)
            rr0, rr1, cc0, cc1 = reference_bounds
            dominant_scope[rr0 - r0 : rr1 - r0 + 1, cc0 - c0 : cc1 - c0 + 1] = True
            if reference_labels is not None:
                dominant_scope &= (
                    reference_labels[r0 : r1 + 1, c0 : c1 + 1] == feature["id"]
                )
            else:
                dominant_scope &= sign * aa >= threshold
            record["feature_reference_cells"] = int((dominant_scope & valid_a).sum())
            record["feature_common_cells"] = int((dominant_scope & common).sum())
            record["feature_support_retention_fraction"] = record[
                "feature_common_cells"
            ] / max(1, record["feature_reference_cells"])
            if not (dominant_scope & common).any():
                record.update(
                    before=None,
                    after=None,
                    peak_displacement_m=None,
                    match_status="unsupported",
                    matched_components=0,
                    same_polarity_lost=None,
                    polarity_reversed=None,
                    dominant_amplitude_retention_ratio=None,
                    amplitude_change_nt=None,
                    amplitude_retention_ratio=None,
                    width_change_m=None,
                    continuity_change=None,
                )
                results.append(record)
                continue
            reference_polarity_retained = bool(
                (dominant_scope & common & (sign * bb >= threshold)).any()
            )
            # Compare this component, never an unrelated stronger neighbour.
            first = _measure(
                aa, transform, sign, threshold, common & dominant_scope, dominant_scope
            )
            after_labels, after_count = ndimage.label(
                common & (sign * bb >= threshold), structure=np.ones((3, 3))
            )
            other_before = common & (sign * aa >= threshold) & ~dominant_scope
            overlap_ids = np.unique(after_labels[dominant_scope & common])
            overlap_ids = overlap_ids[overlap_ids > 0]
            selected = []
            status = "missing"
            if len(overlap_ids):
                selected = overlap_ids.tolist()
                status = "split" if len(selected) > 1 else "matched"
                if any(
                    (other_before & (after_labels == label)).any() for label in selected
                ):
                    status = "merged"
            elif padding > 0:
                distances = ndimage.distance_transform_edt(
                    ~dominant_scope, sampling=(dy, dx)
                )
                candidates = []
                for label in range(1, after_count + 1):
                    footprint = after_labels == label
                    if (footprint & other_before).any():
                        continue
                    distance = float(distances[footprint].min())
                    if distance <= padding + 1e-10:
                        candidates.append((distance, label))
                candidates.sort()
                if candidates:
                    if (
                        len(candidates) > 1
                        and abs(candidates[0][0] - candidates[1][0]) < 1e-10
                    ):
                        status = "ambiguous"
                    else:
                        selected = [candidates[0][1]]
                        status = "matched"
            second_support = (
                common & np.isin(after_labels, selected)
                if selected and status != "merged"
                else common & dominant_scope
            )
            second = _measure(
                bb, transform, sign, threshold, second_support, dominant_scope
            )
            # Preserve the signed fixed-footprint diagnostic even after a shift.
            fixed = _measure(
                bb, transform, sign, threshold, common & dominant_scope, dominant_scope
            )
            second["dominant_peak_nt"] = fixed["dominant_peak_nt"]
            record["match_status"] = status
            record["matched_components"] = len(selected)
            displacement = float(
                np.hypot(
                    (first["peak_col"] - second["peak_col"]) * dx,
                    (first["peak_row"] - second["peak_row"]) * dy,
                )
            )
            for measure in (first, second):
                measure["peak_x_m"], measure["peak_y_m"] = _xy(
                    measure.pop("peak_row") + r0,
                    measure.pop("peak_col") + c0,
                    transform,
                )
            dominant_before, dominant_after = (
                first["dominant_peak_nt"],
                second["dominant_peak_nt"],
            )
            reversed_polarity = (
                dominant_before is not None
                and dominant_after is not None
                and sign * dominant_before >= threshold
                and sign * dominant_after <= -threshold
            )
            record.update(
                before=first,
                after=second,
                same_polarity_lost=not reference_polarity_retained,
                polarity_reversed=bool(reversed_polarity),
                dominant_amplitude_retention_ratio=(
                    dominant_after / dominant_before
                    if dominant_before and dominant_after is not None
                    else None
                ),
                peak_displacement_m=displacement
                if status in ("matched", "split")
                and second["same_polarity_detected"]
                and not reversed_polarity
                else None,
                amplitude_change_nt=second["peak_nt"] - first["peak_nt"]
                if status not in ("merged", "ambiguous")
                else None,
                amplitude_retention_ratio=second["peak_nt"] / first["peak_nt"]
                if first["peak_nt"] and status not in ("merged", "ambiguous")
                else None,
                width_change_m=second["half_height_diameter_m"]
                - first["half_height_diameter_m"]
                if status in ("matched", "split")
                else None,
                continuity_change=second["largest_component_fraction"]
                - first["largest_component_fraction"]
                if status in ("matched", "split")
                else None,
            )
        else:
            record.update(
                before=None,
                after=None,
                peak_displacement_m=None,
                match_status="unsupported",
                matched_components=0,
                same_polarity_lost=None,
                polarity_reversed=None,
                dominant_amplitude_retention_ratio=None,
                amplitude_change_nt=None,
                amplitude_retention_ratio=None,
                width_change_m=None,
                continuity_change=None,
            )
        results.append(record)
    return dict(
        features=results,
        threshold_nt=threshold,
        padding_metres=padding,
        units="nT",
        comparison_support="common finite cells",
        polarity_loss_scope="original thresholded component footprint",
        dominant_amplitude_scope="original thresholded component footprint",
        extrema_search_scope="reference bounding box plus padding",
    )


def compare_retention_geotiffs(before_path, after_path, *, canceled=None, **settings):
    """GeoTIFF version of compare_feature_retention; reject geometry mismatches."""
    _check(canceled)
    a, ta, ca = _read_magnetic(before_path)
    _check(canceled)
    b, tb, cb = _read_magnetic(after_path)
    if ta != tb or ca != cb or a.shape != b.shape:
        raise ValueError("Feature comparison requires identical geometry and CRS.")
    return compare_feature_retention(a, b, ta, canceled=canceled, **settings)


def compare_multiscale_retention(
    result, after_path, *, canceled=None, padding_metres=2.0
):
    """Compare processing effects against every original residual-scale catalogue.

    The after map is after_grid minus the SAME pre-processing Gaussian background
    at each scale. Its background is never re-fitted, so attenuation and shifts
    remain measurable in a total-field survey. Return a JSON-ready object with
    scale_results and overall counts of scale/feature observations. One physical
    feature can occur in several scales; counts are not unique source counts.
    All geometry, metre CRS, nT units, and both source file hashes are verified.
    """
    import rasterio

    _check(canceled)
    before_path = result.get("source_path")
    before_hash = result.get("source_sha256")
    if (
        not before_path
        or not before_hash
        or _file_hash(before_path, canceled) != before_hash
    ):
        raise ValueError("Reference source changed since multiscale analysis.")
    after_hash = _file_hash(after_path, canceled)
    after, transform, crs = _read_magnetic(after_path)
    if _file_hash(after_path, canceled) != after_hash:
        raise ValueError("Processed grid changed during reading.")
    if transform != result["transform"] or crs != rasterio.crs.CRS.from_user_input(
        result["crs"]
    ):
        raise ValueError("Multiscale retention requires identical geometry and CRS.")
    scale_results = []
    threshold = result["metadata"]["threshold_nt"]
    for level in result["scale_maps"]:
        _check(canceled)
        if after.shape != level["residual"].shape:
            raise ValueError("Multiscale retention requires identical grid shapes.")
        with np.errstate(over="ignore", invalid="ignore"):
            residual_after = after - level["background"]
        valid = np.isfinite(after) & np.isfinite(level["background"])
        if not np.isfinite(residual_after[valid]).all():
            raise ValueError("Processed residual values exceed finite numerical range.")
        comparison = compare_feature_retention(
            level["residual"],
            residual_after,
            transform,
            features=level["features"],
            threshold_nt=threshold,
            padding_metres=padding_metres,
            reference_labels=level.get("feature_labels"),
            canceled=canceled,
        )
        comparison.update(
            sigma_m=level["sigma_m"],
            amplitude_reference="fixed original Gaussian background",
            omitted_reference_features=level["omitted_features"],
        )
        scale_results.append(comparison)
    if (
        _file_hash(before_path, canceled) != before_hash
        or _file_hash(after_path, canceled) != after_hash
    ):
        raise ValueError("A source grid changed during retention comparison.")
    observations = [row for scale in scale_results for row in scale["features"]]
    _check(canceled)
    return dict(
        scale_results=scale_results,
        units="nT",
        amplitude_reference="processed grid minus original background at each sigma",
        source_path=str(before_path),
        source_sha256=before_hash,
        after_path=str(Path(after_path).resolve()),
        after_sha256=after_hash,
        threshold_nt=threshold,
        padding_metres=float(padding_metres),
        overall=dict(
            scale_count=len(scale_results),
            feature_observation_count=len(observations),
            same_polarity_lost_count=sum(
                row["same_polarity_lost"] is True for row in observations
            ),
            polarity_reversed_count=sum(
                row["polarity_reversed"] is True for row in observations
            ),
            no_common_support_count=sum(
                row["common_cells"] == 0 for row in observations
            ),
        ),
    )


def _export_analysis_into(result, target, created, canceled=None):
    """Publish GeoTIFF maps, CSV/GeoJSON catalogue and JSON parameters.

    Expects an analyze_geotiff result with transform/crs. Output directory must
    not exist, so previous runs and input files cannot be overwritten. On failure
    publication is finalized by export_analysis after provenance verification.
    """
    import rasterio

    _check(canceled)
    products = {}
    for index, level in enumerate(result["scale_maps"], 1):
        for kind in ("background", "residual"):
            _check(canceled)
            path = target / f"scale_{index:02d}_{kind}.tif"
            created.append(path)
            data = level[kind]
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=data.shape[1],
                height=data.shape[0],
                count=1,
                dtype="float64",
                transform=result["transform"],
                crs=result["crs"],
                nodata=np.nan,
                compress="deflate",
            ) as dst:
                dst.write(data, 1)
                dst.update_tags(
                    units="nT", sigma_metres=str(level["sigma_m"]), analysis=kind
                )
            products[f"scale_{index}_{kind}"] = str(path)
    catalogue = result["catalogue"]
    csv_path = target / "anomaly_catalogue.csv"
    fieldnames = (
        list(catalogue[0])
        if catalogue
        else ["id", "polarity", "x_m", "y_m", "peak_nt", "persistence_count"]
    )
    created.append(csv_path)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(catalogue)
    # RFC 7946 GeoJSON positions are longitude/latitude, irrespective of source CRS.
    from pyproj import Transformer

    project = Transformer.from_crs(result["crs"], "EPSG:4326", always_xy=True)
    features = []
    for row in catalogue:
        _check(canceled)
        lon, lat = project.transform(row["x_m"], row["y_m"])
        features.append(
            dict(
                type="Feature",
                geometry=dict(type="Point", coordinates=[lon, lat]),
                properties=row,
            )
        )
    geojson = target / "anomaly_catalogue.geojson"
    created.append(geojson)
    geojson.write_text(
        json.dumps(
            dict(type="FeatureCollection", features=features), indent=2, allow_nan=False
        ),
        encoding="utf-8",
    )
    metadata = dict(
        result["metadata"],
        source_path=result.get("source_path"),
        crs=result["crs"],
        transform=list(result["transform"]),
        catalogue_cells="anchors from all residual scales",
        omitted_features_by_scale=[
            level["omitted_features"] for level in result["scale_maps"]
        ],
    )
    report = target / "analysis.json"
    created.append(report)
    report.write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8")
    catalogue_json = target / "anomaly_catalogue.json"
    created.append(catalogue_json)
    catalogue_json.write_text(
        json.dumps(
            dict(features=catalogue, metadata=metadata), indent=2, allow_nan=False
        ),
        encoding="utf-8",
    )
    products.update(
        catalogue_csv=str(csv_path),
        catalogue_geojson=str(geojson),
        analysis_json=str(report),
        anomaly_catalogue_json=str(catalogue_json),
    )
    _check(canceled)
    return products


def export_analysis(result, output_dir, *, canceled=None):
    """Publish analysis into a new directory and verify immutable source provenance.

    Return product paths including anomaly_catalogue_json, whose JSON object
    contains features and metadata. On failure/cancellation only files created by
    this call are removed; unrelated or concurrently added files are preserved.
    """
    _check(canceled)
    source = result.get("source_path")
    expected = result.get("source_sha256")
    if not source or not expected or _file_hash(source, canceled) != expected:
        raise ValueError(
            "Source grid changed since analysis; rerun before publication."
        )
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    created = []
    try:
        products = _export_analysis_into(result, target, created, canceled)
        if _file_hash(source, canceled) != expected:
            raise ValueError("Source grid changed during publication.")
        _check(canceled)
        return products
    except BaseException:
        for path in created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            target.rmdir()
        except OSError:
            pass
        raise

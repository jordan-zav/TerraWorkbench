"""Native row-preserving survey preparation and inspectable 1D spectra.

Lag convention matches Forge: GPS(t + lag) belongs to magnetic sample(t).
No interpolation across nulls, timestamp resets or explicitly configured gaps.
"""

import json
from pathlib import Path
import numpy as np
from scipy.signal import welch


def _check(canceled):
    if canceled and canceled():
        raise InterruptedError("Survey preprocessing canceled.")


def _time_scale(unit):
    if unit not in ("ms", "s", "us"):
        raise ValueError("time_unit must be ms, s or us.")
    return {"ms": 0.001, "s": 1.0, "us": 0.000001}[unit]


def _groups(frame, track, sensor):
    columns = [c for c in (track, sensor) if c]
    if len(set(columns)) != len(columns):
        raise ValueError("Track and sensor columns must be distinct.")
    for name in columns:
        if name not in frame:
            raise ValueError(f"Missing group column {name}.")
    if not columns:
        return [((), np.arange(len(frame)))]
    # Positional indices support duplicate source DataFrame labels safely.
    return list(frame.groupby(columns, sort=False, dropna=False).indices.items())


def _runs(ids, valid, times=None, max_gap_seconds=None):
    """Per-profile acquisition order; never sort or cross an invalid observation."""
    if times is not None and max_gap_seconds is None:
        deltas = np.diff(times[ids])
        positive = deltas[np.isfinite(deltas) & (deltas > 0)]
        max_gap_seconds = 2 * float(np.median(positive)) if len(positive) else None
    run = []
    previous = None
    for i in ids:
        good = valid[i] and (times is None or np.isfinite(times[i]))
        split = (
            previous is not None
            and times is not None
            and (
                times[i] <= times[previous]
                or (
                    max_gap_seconds is not None
                    and times[i] - times[previous] > max_gap_seconds
                )
            )
        )
        if not good or split:
            if run:
                yield np.asarray(run)
            run = []
        if good:
            run.append(i)
            previous = i
        else:
            previous = None
    if run:
        yield np.asarray(run)


def _profile_segments(ids, valid, x, y, times, time_gap, spatial_gap):
    """Finite acquisition runs split at physical outages, including default gaps."""
    for run in _runs(ids, valid, times, time_gap):
        delta = np.hypot(np.diff(x[run]), np.diff(y[run]))
        positive = delta[np.isfinite(delta) & (delta > 0)]
        limit = (
            spatial_gap
            if spatial_gap is not None
            else (2 * float(np.median(positive)) if len(positive) else None)
        )
        cuts = np.flatnonzero(delta > limit) + 1 if limit is not None else []
        yield from np.split(run, cuts)


def _bounded_record(step, record):
    step["records_total"] = step.get("records_total", 0) + 1
    if len(step["profiles"]) < 256:
        step["profiles"].append(record)
    else:
        step["records_omitted"] = step.get("records_omitted", 0) + 1


def _profile_warning(report, message):
    if len(report["warnings"]) < 256:
        report["warnings"].append(message)
    else:
        report["warnings_omitted"] = report.get("warnings_omitted", 0) + 1


def _shift(x, y, times, runs, lag_seconds):
    sx, sy = np.full(len(x), np.nan), np.full(len(x), np.nan)
    for ids in runs:
        if len(ids) < 2:
            continue
        target = times[ids] + lag_seconds
        sx[ids] = np.interp(target, times[ids], x[ids], left=np.nan, right=np.nan)
        sy[ids] = np.interp(target, times[ids], y[ids], left=np.nan, right=np.nan)
    return sx, sy


def estimate_lag(
    x,
    y,
    values,
    times_seconds,
    groups,
    *,
    minimum_ms=-1000.0,
    maximum_ms=1000.0,
    step_ms=50.0,
    max_gap_seconds=None,
    canceled=None,
):
    """Scan GPS lag minimizing centered spatial profile disagreement.

    Only same-sensor, opposite, near-parallel neighboring profiles participate.
    This assumes repeated/adjacent anomaly structure and constant lag. It cannot
    identify lag from a single line or featureless field; such cases fail explicitly.
    Unlike legacy correlation it uses physical position, not equal sample indices.
    """
    x, y, values, times_seconds = map(
        lambda a: np.asarray(a, dtype=float), (x, y, values, times_seconds)
    )
    if (
        not all(np.isfinite([minimum_ms, maximum_ms, step_ms]))
        or step_ms <= 0
        or maximum_ms <= minimum_ms
    ):
        raise ValueError("Invalid bounded lag scan.")
    candidates = np.arange(minimum_ms, maximum_ms + step_ms * 0.5, step_ms)
    if len(candidates) > 101:
        raise ValueError("Lag scan is limited to 101 candidates; increase step_ms.")
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
    profiles = []
    all_runs = []
    for key, ids in groups:
        for run in _runs(ids, valid, times_seconds, max_gap_seconds):
            all_runs.append(run)
            if len(run) < 32:
                continue
            vector = np.array([x[run[-1]] - x[run[0]], y[run[-1]] - y[run[0]]])
            length = np.linalg.norm(vector)
            if length > 0 and np.std(values[run]) > 1e-6:
                if len(profiles) < 128:
                    profiles.append((key, run, vector / length, length))
    pairs = []
    for a in range(len(profiles)):
        key, ids, direction, length = profiles[a]
        choices = []
        for b in range(a + 1, len(profiles)):
            other_key, other, odir, olen = profiles[b]
            # A tuple key includes sensor last when callers group track+sensor.
            if isinstance(key, tuple) and len(key) > 1 and key[-1] != other_key[-1]:
                continue
            if np.dot(direction, odir) > -0.9:
                continue
            delta = np.array(
                [
                    np.mean(x[other]) - np.mean(x[ids]),
                    np.mean(y[other]) - np.mean(y[ids]),
                ]
            )
            separation = abs(direction[0] * delta[1] - direction[1] * delta[0])
            if separation <= 0.2 * min(length, olen):
                choices.append((separation, b))
        if choices:
            pairs.append((a, min(choices)[1]))
        if len(pairs) >= 32:
            break
    if not pairs:
        raise ValueError(
            "Auto lag needs opposite parallel profiles with overlapping anomalies; use explicit manual lag."
        )
    # Fix the comparison support across all candidates, preventing lower scores
    # from shedding the difficult overlap endpoints at large candidate lags.
    pair_data = []
    for a, b in pairs:
        _, ia, axis, _ = profiles[a]
        _, ib, _, _ = profiles[b]
        per_candidate = []
        for lag in candidates:
            _check(canceled)
            data = []
            for ids in (ia, ib):
                target = times_seconds[ids] + lag / 1000.0
                sx = np.interp(
                    target, times_seconds[ids], x[ids], left=np.nan, right=np.nan
                )
                sy = np.interp(
                    target, times_seconds[ids], y[ids], left=np.nan, right=np.nan
                )
                good = np.isfinite(sx) & np.isfinite(sy)
                projection = sx[good] * axis[0] + sy[good] * axis[1]
                val = values[ids][good]
                if len(projection) < 16:
                    break
                delta = np.diff(projection)
                if not (np.all(delta > 0) or np.all(delta < 0)):
                    break
                if delta[0] < 0:
                    projection, val = projection[::-1], val[::-1]
                data.append((projection, val))
            per_candidate.append(data)
        if any(len(data) != 2 for data in per_candidate):
            continue
        lower = max(p[0][0] for data in per_candidate for p in data)
        upper = min(p[0][-1] for data in per_candidate for p in data)
        if upper <= lower:
            continue
        knots = np.linspace(lower, upper, min(512, len(ia), len(ib)))
        scores = []
        for data in per_candidate:
            va, vb = [np.interp(knots, p, v) for p, v in data]
            residual = va - vb
            residual -= np.median(residual)
            scale = max(np.std(va), np.std(vb), 1e-6)
            scores.append(float(np.sqrt(np.mean(residual**2)) / scale))
        pair_data.append(scores)
    if not pair_data:
        raise ValueError("No monotonic common spatial support for auto lag.")
    objective = np.median(pair_data, axis=0)
    best = int(np.argmin(objective))
    contrast = float(
        (np.max(objective) - np.min(objective)) / max(np.max(objective), 1e-12)
    )
    if contrast < 0.01:
        raise ValueError(
            "Auto lag objective is flat; lag is unidentifiable. Use explicit manual lag."
        )
    _check(canceled)
    return float(candidates[best]), {
        "objective": "median normalized RMS of median-centered opposite spatial profiles",
        "candidate_ms": candidates.tolist(),
        "score": objective.tolist(),
        "pairs": len(pair_data),
        "best_at_bound": best in (0, len(candidates) - 1),
        "contrast": contrast,
        "profiles_considered": len(profiles),
        "profile_limit": 128,
        "assumptions": "Adjacent profiles share anomaly structure; constant GPS lag; no automatic sensor-delay inference.",
    }


def _uniform_axis(axis):
    delta = np.diff(axis)
    if not len(delta) or np.any(delta <= 0):
        raise ValueError("Resampling requires a strictly increasing explicit axis.")
    spacing = float(np.median(delta))
    count = int(np.ceil((axis[-1] - axis[0]) / spacing)) + 1
    if count > 3_000_000:
        raise ValueError("Uniform resampling exceeds 3 million samples.")
    return np.linspace(axis[0], axis[-1], count)


def spectrum(
    axis, original, filtered, *, domain="time", spacing_tolerance=0.01, resample=False
):
    """Welch PSD on explicit regular seconds/metres; no guessed sample frequency."""
    if domain not in ("time", "distance"):
        raise ValueError("PSD domain must be time or distance.")
    axis, original, filtered = map(
        lambda a: np.asarray(a, float), (axis, original, filtered)
    )
    if len(axis) < 8 or original.shape != axis.shape or filtered.shape != axis.shape:
        raise ValueError("PSD requires at least eight aligned samples.")
    if not np.isfinite(np.concatenate([axis, original, filtered])).all():
        raise ValueError("PSD cannot bridge nulls.")
    delta = np.diff(axis)
    spacing = float(np.median(delta))
    resampled = False
    if spacing <= 0 or np.any(
        abs(delta - spacing) > spacing_tolerance * spacing + 1e-12
    ):
        if not resample:
            raise ValueError(
                "PSD requires regular sampling; enable explicit linear resampling."
            )
        regular = _uniform_axis(axis)
        original, filtered = (
            np.interp(regular, axis, original),
            np.interp(regular, axis, filtered),
        )
        axis = regular
        spacing = float(axis[1] - axis[0])
        resampled = True
    frequency, raw = welch(original, fs=1 / spacing, nperseg=min(1024, len(axis)))
    _, final = welch(filtered, fs=1 / spacing, nperseg=min(1024, len(axis)))
    return {
        "domain": domain,
        "frequency_unit": "Hz" if domain == "time" else "cycles/m",
        "density_unit": "nT²/Hz" if domain == "time" else "nT²/(cycles/m)",
        "spacing": spacing,
        "samples": len(axis),
        "resampled": resampled,
        "resampling": "linear within finite segment" if resampled else "none",
        "frequency": frequency.tolist(),
        "original": raw.tolist(),
        "filtered": final.tolist(),
    }


def preprocess_frame(
    frame,
    options,
    *,
    x_column,
    y_column,
    value_column,
    track_column=None,
    sensor_column=None,
    time_column=None,
    coordinate_mode="projected",
    crs=None,
    canceled=None,
    stage_callback=None,
):
    """Return copied row-preserving frame and JSON-compatible QC/PSD report.

    Inactive rows retain original metadata but selected signal becomes NaN so later
        crossovers cannot bridge exclusions or clipping. Original columns are copied.
    """
    import pandas as pd
    from pyproj import CRS, Transformer

    options = dict(options or {})
    out = frame.copy()
    for column in (x_column, y_column, value_column):
        if column not in out:
            raise ValueError(f"Missing mapped column {column}.")
    if "Source_row_index" not in out:
        out["Source_row_index"] = np.arange(len(out))
    for target, source in (
        ("Original_X", x_column),
        ("Original_Y", y_column),
        ("Original_value_nT", value_column),
    ):
        if target not in out:
            out[target] = out[source]
    x, y, value = [
        pd.to_numeric(out[c], errors="coerce").to_numpy(dtype=float).copy()
        for c in (x_column, y_column, value_column)
    ]
    raw = value.copy()
    groups = _groups(out, track_column, sensor_column)
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(value)
    for mapped_group in (track_column, sensor_column):
        if mapped_group:
            valid &= out[mapped_group].notna().to_numpy()
    times = None
    if time_column:
        if time_column not in out:
            raise ValueError(f"Missing timestamp column {time_column}.")
        times = pd.to_numeric(out[time_column], errors="coerce").to_numpy(
            float
        ) * _time_scale(options.get("time_unit", "ms"))
        valid &= np.isfinite(times)
    gap = options.get("max_gap_seconds")
    if gap is not None and (not np.isfinite(gap) or gap <= 0):
        raise ValueError("max_gap_seconds must be positive.")
    spatial_gap = options.get("max_gap_m")
    if spatial_gap is not None and (not np.isfinite(spatial_gap) or spatial_gap <= 0):
        raise ValueError("max_gap_m must be positive.")
    zero = options.get("zero_traverse", "none")
    if zero not in ("none", "mean", "median"):
        raise ValueError("zero_traverse must be none, mean or median.")
    bounds = []
    for name in ("background_min_nt", "background_max_nt"):
        token = options.get(name)
        try:
            parsed = None if token is None else float(token)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name} must be a finite nT value.") from error
        if parsed is not None and (isinstance(token, bool) or not np.isfinite(parsed)):
            raise ValueError(f"{name} must be a finite nT value.")
        bounds.append(parsed)
    background_min, background_max = bounds
    if (
        background_min is not None
        and background_max is not None
        and background_min > background_max
    ):
        raise ValueError("Background minimum cannot exceed maximum.")
    if zero == "none" and any(v is not None for v in bounds):
        raise ValueError("Background limits require zero traverse mean or median.")
    deslope = options.get("deslope", False)
    if not isinstance(deslope, (bool, np.bool_)):
        raise ValueError("deslope must be true or false.")
    try:
        stagger = float(options.get("destagger_m", 0.0))
    except (TypeError, ValueError) as error:
        raise ValueError("destagger_m must be a finite signed distance.") from error
    if isinstance(options.get("destagger_m"), bool) or not np.isfinite(stagger):
        raise ValueError("destagger_m must be a finite signed distance.")
    parity = options.get("destagger_parity", "even")
    if parity not in ("even", "odd"):
        raise ValueError("destagger_parity must be even or odd.")
    if (zero != "none" or deslope or stagger) and not track_column:
        raise ValueError(
            "Zero traverse, deslope and destagger require a mapped track column."
        )
    excluded = options.get("exclude_sensors") or []
    if excluded:
        if not sensor_column:
            raise ValueError("Sensor exclusion requires a mapped sensor column.")

        def sensor_token(v):
            try:
                n = float(v)
                return str(int(n)) if np.isfinite(n) and n.is_integer() else str(v)
            except (TypeError, ValueError):
                return str(v)

        exclusion = (
            out[sensor_column]
            .map(sensor_token)
            .isin([sensor_token(s) for s in excluded])
            .to_numpy()
        )
        valid &= ~exclusion
    else:
        exclusion = np.zeros(len(out), bool)

    def projected(a, b):
        if coordinate_mode == "geographic":
            target = CRS.from_user_input(crs)
            if not target.is_projected or any(
                abs(u.unit_conversion_factor - 1) > 1e-10 for u in target.axis_info[:2]
            ):
                raise ValueError("Spatial filtering requires a projected metre CRS.")
            return tuple(
                np.asarray(v)
                for v in Transformer.from_crs(
                    "EPSG:4326", target, always_xy=True
                ).transform(a, b)
            )
        if coordinate_mode != "projected":
            raise ValueError("Unknown coordinate mode.")
        target = CRS.from_user_input(crs)
        if not target.is_projected or any(
            abs(u.unit_conversion_factor - 1) > 1e-10 for u in target.axis_info[:2]
        ):
            raise ValueError("Projected coordinates must use metre CRS.")
        return a, b

    lag = float(options.get("lag_ms", 0.0) or 0.0)
    if not np.isfinite(lag):
        raise ValueError("Lag must be finite.")
    report = {
        "input_rows": len(out),
        "excluded_rows": int(exclusion.sum()),
        "steps": [],
        "spectra": [],
        "warnings": [],
        "input_signal_column": value_column,
        "spectrum_original_scope": "selected input values before this preprocessing invocation",
        "invalid_timestamp_rows": int((~np.isfinite(times)).sum())
        if times is not None
        else 0,
        "gap_policy": "invalid rows split profiles; timestamp reset splits; default gap >2x positive median interval",
    }

    def snapshot(step, signal=None):
        if stage_callback is not None:
            _check(canceled)
            values = value if signal is None else signal
            stage_callback(
                dict(step), np.column_stack((x, y, np.where(valid, values, np.nan)))
            )

    if excluded:
        report["steps"].append(
            {
                "operation": "exclude sensors",
                "sensor_ids": [str(s) for s in excluded],
                "excluded_rows": int(exclusion.sum()),
                "row_policy": "retain metadata; signal null",
            }
        )
        snapshot(report["steps"][-1])
    if options.get("auto_lag") or lag:
        if times is None:
            raise ValueError(
                "GPS lag requires an explicit numeric timestamp column and time unit."
            )
        if options.get("auto_lag"):
            px, py = projected(x, y)
            lag, diagnostics = estimate_lag(
                px,
                py,
                np.where(valid, value, np.nan),
                times,
                groups,
                minimum_ms=float(options.get("lag_min_ms", -1000)),
                maximum_ms=float(options.get("lag_max_ms", 1000)),
                step_ms=float(options.get("lag_step_ms", 50)),
                max_gap_seconds=gap,
                canceled=canceled,
            )
            report["auto_lag"] = diagnostics
        runs = [r for _, ids in groups for r in _runs(ids, valid, times, gap)]
        x, y = _shift(x, y, times, runs, lag / 1000.0)
        valid &= np.isfinite(x) & np.isfinite(y)
        report["steps"].append(
            {
                "operation": "GPS lag",
                "lag_ms": lag,
                "convention": "GPS(t+lag) at magnetic t; unsupported endpoints null",
            }
        )
        snapshot(report["steps"][-1])
    if stagger:
        px, py = projected(x, y)
        sx, sy = px.copy(), py.copy()
        step = {
            "operation": "destagger",
            "shift_m": stagger,
            "parity": parity,
            "order": "first track appearance per sensor; first odd, second even",
            "convention": "position at along-track distance plus signed shift",
            "edge_policy": "unsupported endpoints null; no extrapolation",
            "gap_policy": "invalid rows, time resets/outages and spatial gaps split paths; default spatial gap >2x positive median step",
            "profiles": [],
            "record_limit": 256,
            "unsupported_rows": 0,
        }
        profile_order = {}
        for key, ids in sorted(groups, key=lambda item: int(item[1][0])):
            _check(canceled)
            if pd.isna(out[track_column].iloc[ids[0]]) or (
                sensor_column and pd.isna(out[sensor_column].iloc[ids[0]])
            ):
                continue
            sensor_id = str(out[sensor_column].iloc[ids[0]]) if sensor_column else "all"
            order = profile_order.get(sensor_id, 0) + 1
            profile_order[sensor_id] = order
            selected = order % 2 == (0 if parity == "even" else 1)
            record = {
                "group": str(key),
                "acquisition_order": order,
                "shifted": selected,
                "samples": int(valid[ids].sum()),
                "unsupported_rows": 0,
            }
            if selected:
                for segment in _profile_segments(
                    ids, valid, px, py, times, gap, spatial_gap
                ):
                    _check(canceled)
                    sx[segment], sy[segment] = np.nan, np.nan
                    distance = np.r_[
                        0.0,
                        np.cumsum(np.hypot(np.diff(px[segment]), np.diff(py[segment]))),
                    ]
                    if len(segment) >= 2 and distance[-1] > 0:
                        # Repeated positions share a distance knot; retain first measured position.
                        knots, first = np.unique(distance, return_index=True)
                        target = distance + stagger
                        sx[segment] = np.interp(
                            target, knots, px[segment[first]], left=np.nan, right=np.nan
                        )
                        sy[segment] = np.interp(
                            target, knots, py[segment[first]], left=np.nan, right=np.nan
                        )
                    record["unsupported_rows"] += int(
                        (~np.isfinite(sx[segment]) | ~np.isfinite(sy[segment])).sum()
                    )
            step["unsupported_rows"] += record["unsupported_rows"]
            _bounded_record(step, record)
        step["new_null_rows"] = step["unsupported_rows"]
        changed = np.isfinite(sx) & np.isfinite(sy) & ((sx != px) | (sy != py))
        if coordinate_mode == "geographic":
            gx, gy = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(
                sx, sy
            )
            # Avoid a projection round trip for untouched rows.
            x[changed], y[changed] = np.asarray(gx)[changed], np.asarray(gy)[changed]
            unsupported = valid & (~np.isfinite(sx) | ~np.isfinite(sy))
            x[unsupported], y[unsupported] = np.nan, np.nan
        else:
            x, y = sx, sy
        valid &= np.isfinite(x) & np.isfinite(y)
        step["finite_output_rows"] = int(valid.sum())
        report["steps"].append(step)
        snapshot(report["steps"][-1])
    clip = options.get("clip_geo")
    if clip:
        from shapely.geometry import shape
        from shapely.ops import unary_union, transform

        suffix = Path(clip).suffix.lower()
        if suffix in (".json", ".geojson"):
            data = json.loads(Path(clip).read_text(encoding="utf-8-sig"))
            clip_crs = (
                options.get("clip_crs")
                or data.get("crs", {}).get("properties", {}).get("name")
                or "EPSG:4326"
            )
            features = (
                data.get("features", [data])
                if data.get("type") == "FeatureCollection"
                else [data]
            )
            geometry = unary_union(
                [shape(f.get("geometry", f)) for f in features if f.get("geometry", f)]
            )
        elif suffix == ".kml":
            import xml.etree.ElementTree as ET
            from shapely.geometry import Polygon

            doc = ET.parse(str(clip))
            ns = {"k": "http://www.opengis.net/kml/2.2"}

            def coordinates(element):
                return [
                    tuple(map(float, token.split(",")[:2]))
                    for token in (element.text or "").split()
                ]

            polygons = []
            for polygon in doc.findall(".//k:Polygon", ns):
                outer = polygon.find("k:outerBoundaryIs/k:LinearRing/k:coordinates", ns)
                if outer is not None:
                    holes = [
                        coordinates(e)
                        for e in polygon.findall(
                            "k:innerBoundaryIs/k:LinearRing/k:coordinates", ns
                        )
                    ]
                    polygons.append(Polygon(coordinates(outer), holes))
            geometry = unary_union(polygons)
            clip_crs = options.get("clip_crs") or "EPSG:4326"
        else:
            try:
                import fiona
            except ImportError as error:
                raise ValueError(
                    "This runtime supports GeoJSON/KML clipping; convert the polygon to either format."
                ) from error
            with fiona.open(str(clip)) as source:
                clip_crs = options.get("clip_crs") or source.crs_wkt or source.crs
                if not clip_crs:
                    raise ValueError(
                        "Clipping geometry requires a declared source CRS."
                    )
                geometry = unary_union(
                    [
                        shape(feature["geometry"])
                        for feature in source
                        if feature["geometry"]
                    ]
                )
        if (
            geometry.is_empty
            or not geometry.is_valid
            or geometry.geom_type not in ("Polygon", "MultiPolygon")
        ):
            raise ValueError("Clip must be a valid polygon geometry.")
        input_crs = "EPSG:4326" if coordinate_mode == "geographic" else crs
        geometry = transform(
            Transformer.from_crs(clip_crs, input_crs, always_xy=True).transform,
            geometry,
        )
        from shapely import intersects_xy

        inside = intersects_xy(geometry, x, y)
        report["clipped_rows"] = int((valid & ~inside).sum())
        valid &= inside
        report["steps"].append(
            {
                "operation": "geometry clip",
                "path": str(Path(clip).resolve()),
                "boundary_included": True,
            }
        )
        snapshot(report["steps"][-1])
    value[~valid] = np.nan
    level_mode = options.get("level_mode", "none")
    if level_mode not in ("none", "sensor", "sensor_track"):
        raise ValueError("level_mode must be none, sensor or sensor_track.")
    if level_mode != "none":
        if not sensor_column or (level_mode == "sensor_track" and not track_column):
            raise ValueError("Selected leveling requires sensor/track mappings.")
        temporary = out.copy()
        temporary["_archie_value"] = value
        sensor_medians = (
            temporary.groupby(sensor_column, dropna=False)["_archie_value"]
            .transform("median")
            .to_numpy()
        )
        out["Sensor_levelled_nT"] = value - sensor_medians
        if track_column:
            line_medians = (
                temporary.groupby([sensor_column, track_column], dropna=False)[
                    "_archie_value"
                ]
                .transform("median")
                .to_numpy()
            )
            out["Sensor_track_levelled_nT"] = value - line_medians
        value = (
            out[
                "Sensor_levelled_nT"
                if level_mode == "sensor"
                else "Sensor_track_levelled_nT"
            ]
            .to_numpy(float)
            .copy()
        )
        report["steps"].append(
            {
                "operation": "median leveling",
                "mode": level_mode,
                "reference": "pre-filter values; relative zero median",
            }
        )
        snapshot(report["steps"][-1])
    if zero != "none":
        step = {
            "operation": "zero traverse",
            "method": zero,
            "background_min_nt": background_min,
            "background_max_nt": background_max,
            "threshold_scope": "estimate offset only; subtract from all finite profile values",
            "profiles": [],
            "record_limit": 256,
            "skipped_profiles": 0,
            "new_null_rows": 0,
        }
        for key, ids in groups:
            _check(canceled)
            finite = np.isfinite(value[ids])
            selected = finite.copy()
            if background_min is not None:
                selected &= value[ids] >= background_min
            if background_max is not None:
                selected &= value[ids] <= background_max
            count = int(selected.sum())
            record = {
                "group": str(key),
                "finite_samples": int(finite.sum()),
                "used_samples": count,
                "excluded_from_estimation": int(finite.sum()) - count,
                "offset_nt": None,
            }
            if count:
                offset = float(
                    np.mean(value[ids[selected]])
                    if zero == "mean"
                    else np.median(value[ids[selected]])
                )
                value[ids[finite]] -= offset
                record["offset_nt"] = offset
            else:
                step["skipped_profiles"] += 1
                _profile_warning(
                    report,
                    f"Zero traverse group {key}: no samples within background limits; profile unchanged.",
                )
            _bounded_record(step, record)
        report["steps"].append(step)
        snapshot(report["steps"][-1])
    if deslope:
        px, py = projected(x, y)
        step = {
            "operation": "deslope",
            "fit": "least-squares straight line versus along-track metres",
            "gap_policy": "invalid rows, time resets/outages and spatial gaps split fits; default spatial gap >2x positive median step",
            "profiles": [],
            "record_limit": 256,
            "skipped_segments": 0,
            "new_null_rows": 0,
        }
        for key, ids in groups:
            _check(canceled)
            for segment in _profile_segments(
                ids, valid & np.isfinite(value), px, py, times, gap, spatial_gap
            ):
                _check(canceled)
                distance = np.r_[
                    0.0, np.cumsum(np.hypot(np.diff(px[segment]), np.diff(py[segment])))
                ]
                record = {
                    "group": str(key),
                    "source_start_row": int(segment[0]),
                    "source_end_row": int(segment[-1]),
                    "samples": len(segment),
                    "start_xy_m": [float(px[segment[0]]), float(py[segment[0]])],
                    "end_xy_m": [float(px[segment[-1]]), float(py[segment[-1]])],
                    "length_m": float(distance[-1]),
                    "slope_nt_per_m": None,
                    "intercept_nt": None,
                }
                if len(segment) < 3 or distance[-1] <= 0:
                    step["skipped_segments"] += 1
                    _profile_warning(
                        report,
                        f"Deslope group {key}, row {int(segment[0])}: needs at least three samples with physical span; segment unchanged.",
                    )
                else:
                    centered = distance - np.mean(distance)
                    slope = float(
                        np.dot(centered, value[segment] - np.mean(value[segment]))
                        / np.dot(centered, centered)
                    )
                    intercept = float(
                        np.mean(value[segment]) - slope * np.mean(distance)
                    )
                    value[segment] -= intercept + slope * distance
                    record.update(slope_nt_per_m=slope, intercept_nt=intercept)
                _bounded_record(step, record)
        report["steps"].append(step)
        snapshot(report["steps"][-1])
    spike = options.get("spike_tol")
    if spike is not None and any(
        name in out
        for name in (
            "Despike_modified",
            "Before_despike_nT",
            "After_despike_nT",
            "Despike_delta_nT",
        )
    ):
        raise ValueError("Existing despike audit columns would be overwritten.")
    despike_flags = np.zeros(len(out), dtype=bool)
    despike_before = np.full(len(out), np.nan)
    despike_after = np.full(len(out), np.nan)
    median_window = options.get("median_window_samples")
    if median_window is not None and (
        isinstance(median_window, bool) or int(median_window) != median_window
    ):
        raise ValueError("Sample median window must be an integer.")
    notch_hz = float(options.get("notch_hz", 0) or 0)
    notch_q = float(options.get("notch_q", 30))
    if (
        not np.isfinite([notch_hz, notch_q]).all()
        or notch_hz < 0
        or not 1 <= notch_q <= 1000
    ):
        raise ValueError("Notch frequency must be nonnegative and Q 1–1000.")
    if notch_hz and times is None:
        raise ValueError("Temporal notch requires mapped timestamps and time unit.")
    high_m = float(options.get("highpass_m", 0) or 0)
    bw_high_m, bw_low_m = [
        float(options.get(k, 0) or 0) for k in ("bw_high_m", "bw_low_m")
    ]
    bw_high_hz, bw_low_hz = [
        float(options.get(k, 0) or 0) for k in ("bw_high_hz", "bw_low_hz")
    ]
    if any(
        not np.isfinite(v) or v < 0
        for v in (high_m, bw_high_m, bw_low_m, bw_high_hz, bw_low_hz)
    ):
        raise ValueError(
            "Filter wavelengths/frequencies must be finite and nonnegative."
        )
    if (bw_high_m or bw_low_m) and (bw_high_hz or bw_low_hz):
        raise ValueError(
            "Choose spatial wavelengths or temporal frequencies, not both."
        )
    need_spatial = (
        high_m
        or bw_high_m
        or bw_low_m
        or (options.get("psd") and options.get("psd_domain", "time") == "distance")
    )
    px, py = projected(x, y) if need_spatial else (x, y)
    tolerance = float(options.get("spacing_tolerance", 0.01))
    if not np.isfinite(tolerance) or not 0 <= tolerance <= 0.05:
        raise ValueError("spacing_tolerance must be between zero and 5%.")
    from terraworkbench_core.channel_filters import ChannelFilterOptions, filter_segment

    stage_values = {}
    if stage_callback is not None:
        for name, active in [
            ("despike", spike is not None),
            ("moving median residual", median_window or high_m),
            (
                "zero-phase Butterworth SOS",
                bw_high_m or bw_low_m or bw_high_hz or bw_low_hz,
            ),
            ("zero-phase temporal notch", notch_hz),
        ]:
            if active:
                stage_values[name] = value.copy()

    def capture(name, segment, values):
        if name in stage_values:
            stage_values[name][segment] = values

    for key, ids in groups:
        _check(canceled)
        for run in _runs(ids, valid, times, gap):
            _check(canceled)
            if len(run) > 3_000_000:
                raise ValueError("Profile segment exceeds 3 million rows.")
            distance = np.r_[
                0.0, np.cumsum(np.hypot(np.diff(px[run]), np.diff(py[run])))
            ]
            pieces = (
                np.split(run, np.flatnonzero(np.diff(distance) > spatial_gap) + 1)
                if spatial_gap
                else [run]
            )
            for segment in pieces:
                vals = value[segment].copy()
                axis_sample = np.arange(len(segment), dtype=float)
                if spike is not None:
                    threshold = float(spike)
                    window = int(options.get("spike_window", 5))
                    if (
                        threshold <= 0
                        or not np.isfinite(threshold)
                        or window < 3
                        or window > 1001
                        or window % 2 != 1
                    ):
                        raise ValueError(
                            "Despike requires positive nT threshold and odd window 3..1001."
                        )
                    med, counts = filter_segment(
                        axis_sample,
                        vals,
                        ChannelFilterOptions(method="median", window=window),
                        canceled,
                    )
                    replacements = np.isfinite(med) & (abs(vals - med) > threshold)
                    despike_before[segment] = vals
                    despike_flags[segment] = replacements
                    vals[replacements] = med[replacements]
                    despike_after[segment] = vals
                    report.setdefault("spikes_replaced", 0)
                    report["spikes_replaced"] += int(replacements.sum())
                capture("despike", segment, vals)
                if median_window or high_m:
                    if median_window and high_m:
                        raise ValueError(
                            "Choose sample median window or physical highpass window, not both."
                        )
                    width = int(median_window) if median_window else None
                    if high_m:
                        ds = np.hypot(np.diff(px[segment]), np.diff(py[segment]))
                        along = np.r_[0.0, np.cumsum(ds)]
                        lower = np.searchsorted(along, along - high_m / 2, side="left")
                        upper = np.searchsorted(along, along + high_m / 2, side="right")
                        if np.max(upper - lower) > 1001:
                            raise ValueError(
                                "Physical moving median contains over 1001 samples per window; reduce window/resample explicitly."
                            )
                        background = np.full(len(vals), np.nan)
                        for j, (start, end) in enumerate(zip(lower, upper)):
                            if j % 1024 == 0:
                                _check(canceled)
                            if (
                                along[j] - high_m / 2 >= 0
                                and along[j] + high_m / 2 <= along[-1]
                                and end - start >= 3
                            ):
                                background[j] = np.median(vals[start:end])
                        counts = {
                            "short_segments": int(not np.isfinite(background).any())
                        }
                    else:
                        background, counts = filter_segment(
                            axis_sample,
                            vals,
                            ChannelFilterOptions(method="median", window=width),
                            canceled,
                        )
                    vals = vals - background
                    report.setdefault("short_filter_segments", 0)
                    report["short_filter_segments"] += counts["short_segments"]
                capture("moving median residual", segment, vals)
                if bw_high_m or bw_low_m or bw_high_hz or bw_low_hz:
                    spatial = bool(bw_high_m or bw_low_m)
                    if not spatial and times is None:
                        raise ValueError("Temporal Butterworth requires timestamps.")
                    axis = (
                        np.r_[
                            0.0,
                            np.cumsum(
                                np.hypot(np.diff(px[segment]), np.diff(py[segment]))
                            ),
                        ]
                        if spatial
                        else times[segment]
                    )
                    low = 1 / bw_high_m if spatial and bw_high_m else bw_high_hz
                    high = 1 / bw_low_m if spatial and bw_low_m else bw_low_hz
                    method = (
                        "bandpass" if low and high else "highpass" if low else "lowpass"
                    )
                    config = ChannelFilterOptions(
                        method=method,
                        domain="distance" if spatial else "time",
                        axis="explicit",
                        cutoff=low or high,
                        upper_cutoff=high or 0.2,
                        order=int(options.get("bw_order", 4)),
                        spacing_tolerance=tolerance,
                    )
                    # Median edge nulls are separate runs, never interpolated away.
                    finite = np.isfinite(vals)
                    for sub in _runs(np.arange(len(segment)), finite):
                        subaxis = axis[sub]
                        subvalues = vals[sub]
                        if options.get("bw_resample") and len(subaxis) > 1:
                            delta = np.diff(subaxis)
                            spacing = np.median(delta)
                            if np.any(
                                abs(delta - spacing) > tolerance * spacing + 1e-12
                            ):
                                regular = _uniform_axis(subaxis)
                                result, counts = filter_segment(
                                    regular,
                                    np.interp(regular, subaxis, subvalues),
                                    config,
                                    canceled,
                                )
                                result = np.interp(subaxis, regular, result)
                                report.setdefault("butterworth_resampled_segments", 0)
                                report["butterworth_resampled_segments"] += 1
                            else:
                                result, counts = filter_segment(
                                    subaxis, subvalues, config, canceled
                                )
                        else:
                            result, counts = filter_segment(
                                subaxis, subvalues, config, canceled
                            )
                        vals[sub] = result
                        report.setdefault("short_filter_segments", 0)
                        report["short_filter_segments"] += counts["short_segments"]
                capture("zero-phase Butterworth SOS", segment, vals)
                if notch_hz:
                    from .channel_filters import notch_segment

                    for sub in _runs(np.arange(len(vals)), np.isfinite(vals)):
                        axis = times[segment[sub]]
                        signal = vals[sub]
                        resampled = False
                        if options.get("notch_resample") and len(axis) > 1:
                            delta = np.diff(axis)
                            spacing = float(np.median(delta))
                            if np.any(
                                abs(delta - spacing)
                                > tolerance * spacing + 1e-12 * spacing
                            ):
                                regular = _uniform_axis(axis)
                                resampled = True
                                result, counts = notch_segment(
                                    regular,
                                    np.interp(regular, axis, signal),
                                    frequency_hz=notch_hz,
                                    quality_factor=notch_q,
                                    spacing_tolerance=tolerance,
                                    canceled=canceled,
                                )
                                result = np.interp(axis, regular, result)
                        if not resampled:
                            result, counts = notch_segment(
                                axis,
                                signal,
                                frequency_hz=notch_hz,
                                quality_factor=notch_q,
                                spacing_tolerance=tolerance,
                                canceled=canceled,
                            )
                        vals[sub] = result
                        report.setdefault("notch_short_segments", 0)
                        report["notch_short_segments"] += counts["short_segments"]
                        report.setdefault("notch_resampled_segments", 0)
                        report["notch_resampled_segments"] += int(resampled)
                capture("zero-phase temporal notch", segment, vals)
                value[segment] = vals
                if options.get("psd"):
                    domain = options.get("psd_domain", "time")
                    if domain == "time" and times is None:
                        raise ValueError(
                            "Temporal PSD requires explicit numeric timestamps."
                        )
                    axis = (
                        times[segment]
                        if domain == "time"
                        else np.r_[
                            0.0,
                            np.cumsum(
                                np.hypot(np.diff(px[segment]), np.diff(py[segment]))
                            ),
                        ]
                    )
                    for sub in _runs(
                        np.arange(len(segment)),
                        np.isfinite(vals) & np.isfinite(raw[segment]),
                    ):
                        if len(sub) < 8:
                            continue
                        if len(report["spectra"]) >= 256:
                            report.setdefault("skipped_spectra", 0)
                            report["skipped_spectra"] += 1
                            if report["skipped_spectra"] == 1:
                                report["warnings"].append(
                                    "PSD display/export limited to first 256 finite segments; filtering continues for all rows."
                                )
                            continue
                        try:
                            entry = spectrum(
                                axis[sub],
                                raw[segment[sub]],
                                vals[sub],
                                domain=domain,
                                spacing_tolerance=tolerance,
                                resample=bool(options.get("psd_resample")),
                            )
                        except ValueError as error:
                            report["warnings"].append(
                                f"PSD group {key}, row {int(segment[sub[0]])}: {error}"
                            )
                            continue
                        entry["group"] = str(key)
                        entry["source_start_row"] = int(segment[sub[0]])
                        report["spectra"].append(entry)
    if spike is not None:
        out["Despike_modified"] = despike_flags
        out["Before_despike_nT"] = despike_before
        out["After_despike_nT"] = despike_after
        out["Despike_delta_nT"] = despike_after - despike_before
        report["despike_review_columns"] = [
            "Despike_modified",
            "Before_despike_nT",
            "After_despike_nT",
            "Despike_delta_nT",
        ]
        report["warnings"].append(
            "Despiking can replace genuine narrow anomalies. Review Original_value_nT and despike audit columns when assessing small ferrous targets."
        )
        report["despike_evidence"] = {
            "report": "SCIENTIFIC_VALIDATION.html",
            "test": "benchmarks/test_archaeological_preservation.py",
            "scope": "Controlled synthetic experiment; loss depends on target width, sampling, threshold and window.",
        }
        report["steps"].append(
            {
                "operation": "despike",
                "threshold_nT": float(spike),
                "edge_policy": "retain untested edges",
            }
        )
    if median_window or high_m:
        report["steps"].append(
            {
                "operation": "moving median residual",
                "window_samples": median_window,
                "window_m": high_m,
                "edge_policy": "null incomplete windows",
            }
        )
    if bw_high_m or bw_low_m or bw_high_hz or bw_low_hz:
        report["steps"].append(
            {
                "operation": "zero-phase Butterworth SOS",
                "highpass_wavelength_m": bw_high_m,
                "lowpass_wavelength_m": bw_low_m,
                "highpass_hz": bw_high_hz,
                "lowpass_hz": bw_low_hz,
                "order": int(options.get("bw_order", 4)),
                "irregular_sampling": "explicit linear resampling"
                if options.get("bw_resample")
                else "reject",
            }
        )
    if notch_hz:
        report["steps"].append(
            dict(
                operation="zero-phase temporal notch",
                frequency_hz=notch_hz,
                quality_factor=notch_q,
                bandwidth_hz=notch_hz / notch_q,
                irregular_sampling="explicit linear resampling"
                if options.get("notch_resample")
                else "reject",
                reference="https://doi.org/10.1007/s00024-023-03323-w",
                reference_scope="MT paper discusses notch limitations; this is not its adaptive sinusoidal subtraction",
            )
        )
    for step in report["steps"]:
        name = step["operation"]
        if name in stage_values:
            snapshot(step, stage_values.pop(name))
    out[x_column], out[y_column], out[value_column] = x, y, value
    out["Preprocessed_nT"] = value
    report["finite_output_rows"] = int(
        (np.isfinite(x) & np.isfinite(y) & np.isfinite(value)).sum()
    )
    report["lag_ms"] = lag
    _check(canceled)
    return out, report

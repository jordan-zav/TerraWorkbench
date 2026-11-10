"""Independent relative order-zero levelling at real cross-survey intersections.

The fixed-median recipe is an opt-in transformation for crosshatch data. It
removes each profile's baseline and does not preserve an absolute total field.
Synthetic validation does not certify a historical field-processing pipeline.
"""

from __future__ import annotations

import numpy as np


def clean_crosshatch_levels(
    first_df,
    second_df,
    *,
    x_column,
    y_column,
    value_column,
    track_column,
    sensor_column,
    time_column,
    canceled=None,
    progress=None,
    workflow="crosshatch",
    baseline_mode="sensor_profile",
    on_no_crossovers="raise",
    max_segments=1000000,
    max_crossings=500000,
):
    """Return two copied frames and a JSON-safe relative-levelling QC report.

    Time must be numeric and use the same unit within each input. Rows retain
    their original order and index. Invalid rows are retained with NaN derived
    values. Each track/sensor pair is one order-zero correction profile. Its
    geometry follows source order and breaks at invalid samples, non-increasing
    time, or a time gap exceeding twice its median positive sampling interval.
    No-crossing input raises by default; an explicit noop keeps only medians.
    Cancellation raises InterruptedError and never edits caller-owned frames.
    """
    import pandas as pd
    import shapely
    from shapely import STRtree
    from scipy import sparse
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse.linalg import LinearOperator, cg

    if int(shapely.__version__.split(".")[0]) < 2:
        raise RuntimeError("Crossovers require Shapely 2 or newer.")
    if workflow not in ("crosshatch", "tie_lines"):
        raise ValueError("Unknown crossover workflow.")
    if baseline_mode not in ("none", "sensor", "sensor_profile"):
        raise ValueError("Unknown crossover baseline mode.")
    if on_no_crossovers not in ("raise", "noop"):
        raise ValueError("on_no_crossovers must be raise or noop.")
    for name, limit in [
        ("max_segments", max_segments),
        ("max_crossings", max_crossings),
    ]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, np.integer))
            or limit < 1
        ):
            raise ValueError(name + " must be a positive integer.")
    columns = [
        x_column,
        y_column,
        value_column,
        track_column,
        sensor_column,
        time_column,
    ]
    if len(set(columns)) != 6:
        raise ValueError(
            "Coordinates, value, track, sensor and time columns must be distinct."
        )

    def check_cancel():
        if canceled is not None and canceled():
            raise InterruptedError("Crossover levelling canceled.")

    def update(value):
        check_cancel()
        if progress is not None:
            progress(float(value))

    def prepare(frame, side):
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("Crossover inputs must be pandas DataFrames.")
        if not frame.columns.is_unique:
            raise ValueError("Input column names must be unique.")
        missing = [name for name in columns if name not in frame]
        if missing:
            raise ValueError(side + " is missing columns: " + ", ".join(missing))
        out = frame.copy(deep=True)
        numeric = np.column_stack(
            [
                pd.to_numeric(frame[c], errors="coerce").to_numpy(
                    dtype=float, na_value=np.nan
                )
                for c in [x_column, y_column, value_column, time_column]
            ]
        )
        ids_valid = (
            frame[track_column].notna().to_numpy()
            & frame[sensor_column].notna().to_numpy()
        )
        unknown_id_prefix = np.cumsum(~ids_valid)
        valid = np.isfinite(numeric).all(axis=1) & ids_valid
        profile = np.full(len(frame), -1, dtype=np.int64)
        # Factorize every identified row, even invalid geometry/value rows. The
        # latter remain inside the profile sequence so they break adjacency.
        identified = np.flatnonzero(ids_valid)
        keys = pd.MultiIndex.from_frame(
            frame.iloc[identified][[track_column, sensor_column]]
        )
        codes, unique = pd.factorize(keys, sort=False)
        profile[identified] = codes
        ordering = np.argsort(codes, kind="stable")
        profile_positions = (
            np.split(identified[ordering], np.cumsum(np.bincount(codes))[:-1])
            if len(codes)
            else []
        )
        working = pd.DataFrame(
            {
                "profile": profile[valid],
                "sensor": frame[sensor_column].to_numpy()[valid],
                "value": numeric[valid, 2],
            }
        )
        after_sensor = working.value - working.groupby(
            "sensor", sort=False
        ).value.transform("median")
        after_profile = after_sensor - after_sensor.groupby(
            working.profile, sort=False
        ).transform("median")
        baseline = np.full(len(frame), np.nan)
        baseline[valid] = (
            numeric[valid, 2]
            if workflow == "tie_lines" or baseline_mode == "none"
            else (
                after_sensor.to_numpy()
                if baseline_mode == "sensor"
                else after_profile.to_numpy()
            )
        )
        for name, values in [
            ("After_sensor_median_nT", after_sensor.to_numpy()),
            ("After_sensor_transect_medians_nT", after_profile.to_numpy()),
        ]:
            if (
                workflow == "crosshatch"
                and baseline_mode != "none"
                and (
                    name == "After_sensor_median_nT"
                    or baseline_mode == "sensor_profile"
                )
            ):
                derived = np.full(len(frame), np.nan)
                derived[valid] = values
                out[name] = derived
        segments, starts, ends, segment_profiles = [], [], [], []
        segment_count = 0
        skipped_gap = skipped_invalid = skipped_zero = 0
        limits = []
        profiles = []
        for pid, key in enumerate(unique):
            check_cancel()
            positions = profile_positions[pid]
            profiles.append(
                {
                    "side": side,
                    "local_id": pid,
                    "track": str(key[0]),
                    "sensor": str(key[1]),
                    "valid_rows": int(valid[positions].sum()),
                }
            )
            dt = np.diff(numeric[positions, 3])
            unknown_between = (
                unknown_id_prefix[positions[1:]] - unknown_id_prefix[positions[:-1]]
            ) > 0
            both = valid[positions[:-1]] & valid[positions[1:]] & ~unknown_between
            positive = dt[both & (dt > 0)]
            limit = 2 * float(np.median(positive)) if len(positive) else None
            limits.append(
                {
                    "profile_id": pid,
                    "max_time_gap": limit,
                    "positive_intervals": int(len(positive)),
                }
            )
            if limit is None:
                skipped_invalid += int((~both).sum())
                skipped_gap += int(both.sum())
                continue
            distance = np.linalg.norm(
                numeric[positions[1:], :2] - numeric[positions[:-1], :2], axis=1
            )
            timing = (dt > 0) & (dt <= limit)
            good = both & timing & (distance > 1e-8)
            skipped_invalid += int((~both).sum())
            skipped_gap += int((both & ~timing).sum())
            skipped_zero += int((both & timing & (distance <= 1e-8)).sum())
            begin = positions[:-1][good]
            finish = positions[1:][good]
            if segment_count + len(begin) > max_segments:
                raise ValueError(
                    side + " exceeds max_segments; partition or reduce input."
                )
            segment_count += len(begin)
            starts.append(begin)
            ends.append(finish)
            segment_profiles.append(np.full(len(begin), pid, dtype=np.int64))
            segments.append(np.stack([numeric[begin, :2], numeric[finish, :2]], axis=1))
        return {
            "frame": out,
            "numeric": numeric,
            "valid": valid,
            "profile": profile,
            "baseline": baseline,
            "profiles": profiles,
            "coords": np.concatenate(segments) if segments else np.empty((0, 2, 2)),
            "starts": np.concatenate(starts)
            if starts
            else np.array([], dtype=np.int64),
            "ends": np.concatenate(ends) if ends else np.array([], dtype=np.int64),
            "segment_profiles": np.concatenate(segment_profiles)
            if segment_profiles
            else np.array([], dtype=np.int64),
            "qc": {
                "input_rows": len(frame),
                "valid_rows": int(valid.sum()),
                "invalid_rows": int((~valid).sum()),
                "used_segments": segment_count,
                "invalid_adjacencies_skipped": skipped_invalid,
                "time_gap_segments_skipped": skipped_gap,
                "zero_length_segments_skipped": skipped_zero,
                "profile_sampling": limits,
            },
        }

    update(0.0)
    first = prepare(first_df, "first")
    update(0.10)
    second = prepare(second_df, "second")
    update(0.20)
    nfirst = len(first["profiles"])
    nsecond = len(second["profiles"])
    n = nfirst + nsecond
    if n == 0:
        raise ValueError("No identified track/sensor profiles in inputs.")
    profiles = first["profiles"] + second["profiles"]
    for pid, item in enumerate(profiles):
        item["global_id"] = pid
    crossings = []
    seen = set()
    overlaps = duplicates = candidates = 0
    if len(first["coords"]) and len(second["coords"]):
        second_geometry = shapely.linestrings(second["coords"])
        tree = STRtree(second_geometry)
        for i, coords in enumerate(first["coords"]):
            check_cancel()
            query = shapely.LineString(coords)
            hits = tree.query(query, predicate="intersects")
            candidates += len(hits)
            # Count candidates before intersection geometry allocation; this
            # also bounds overlapping segments and endpoint multiplicities.
            if candidates > max_crossings:
                raise ValueError(
                    "Intersection candidates exceed max_crossings; partition input."
                )
            if len(hits):
                locations = shapely.intersection(query, second_geometry[hits])
                point = shapely.get_type_id(locations) == 0
                overlaps += int((~point).sum())
                xy = shapely.get_coordinates(locations[point])
                for j, location in zip(hits[point], xy):
                    left = int(first["segment_profiles"][i])
                    right = int(second["segment_profiles"][j]) + nfirst
                    key = (
                        left,
                        right,
                        round(float(location[0]), 6),
                        round(float(location[1]), 6),
                    )
                    if key in seen:
                        duplicates += 1
                        continue
                    seen.add(key)
                    fields = []
                    for prepared, segment in [(first, i), (second, int(j))]:
                        endpoints = prepared["coords"][segment]
                        vector = endpoints[1] - endpoints[0]
                        fraction = float(
                            np.clip(
                                np.dot(location - endpoints[0], vector)
                                / np.dot(vector, vector),
                                0.0,
                                1.0,
                            )
                        )
                        begin, finish = (
                            prepared["starts"][segment],
                            prepared["ends"][segment],
                        )
                        fields.append(
                            float(
                                prepared["baseline"][begin] * (1 - fraction)
                                + prepared["baseline"][finish] * fraction
                            )
                        )
                    crossings.append((left, right, fields[0] - fields[1]))
            if i % 64 == 0:
                update(0.20 + 0.45 * (i + 1) / len(first["coords"]))
    update(0.65)
    offsets = np.zeros(n)
    component_labels = np.arange(n)
    degrees = np.zeros(n)
    before = after = np.array([], dtype=float)
    iterations = 0
    normal_max = 0.0
    solver_status = "not_run"
    if crossings and workflow == "tie_lines":
        data = np.asarray(crossings, dtype=float)
        left, right, before = data[:, 0].astype(int), data[:, 1].astype(int), data[:, 2]
        counts = np.bincount(left, minlength=nfirst)
        active = counts > 0
        offsets[:nfirst][active] = (
            -np.bincount(left, weights=before, minlength=nfirst)[active]
            / counts[active]
        )
        degrees = np.bincount(np.r_[left, right], minlength=n)
        adjacency = sparse.coo_matrix(
            (np.ones(2 * len(data)), (np.r_[left, right], np.r_[right, left])),
            shape=(n, n),
        ).tocsr()
        _, component_labels = connected_components(adjacency, directed=False)
        after = before + offsets[left]
        normal_max = float(
            np.max(abs(np.bincount(left, weights=after, minlength=nfirst)))
        )
        if (
            not np.isfinite(offsets).all()
            or np.linalg.norm(after) > np.linalg.norm(before) + 1e-8
        ):
            raise ValueError("Tie-line correction validation failed.")
        solver_status = "anchored_primary_profile_means"
    elif crossings:
        data = np.asarray(crossings, dtype=float)
        left, right, before = data[:, 0].astype(int), data[:, 1].astype(int), data[:, 2]
        adjacency = sparse.coo_matrix(
            (np.ones(2 * len(data)), (np.r_[left, right], np.r_[right, left])),
            shape=(n, n),
        ).tocsr()
        components, component_labels = connected_components(adjacency, directed=False)
        degrees = np.asarray(adjacency.sum(axis=1)).ravel()
        counts = np.bincount(component_labels)
        A = sparse.coo_matrix(
            (
                np.tile([1.0, -1.0], len(data)),
                (
                    np.repeat(np.arange(len(data)), 2),
                    np.column_stack([left, right]).ravel(),
                ),
            ),
            shape=(len(data), n),
        ).tocsr()
        laplacian = A.T @ A
        rhs = -np.asarray(A.T @ before).ravel()

        # Add the component-constant projection to make the normal operator
        # positive definite without choosing an arbitrary reference profile.
        def matvec(value):
            means = (
                np.bincount(component_labels, weights=value, minlength=components)
                / counts
            )
            return laplacian @ value + means[component_labels]

        operator = LinearOperator((n, n), matvec=matvec, dtype=float)
        diagonal = degrees + 1 / counts[component_labels]
        preconditioner = LinearOperator(
            (n, n), matvec=lambda value: value / diagonal, dtype=float
        )

        def callback(_):
            nonlocal iterations
            iterations += 1
            check_cancel()
            if iterations % 32 == 0:
                update(0.65 + 0.25 * min(iterations / 10000, 1.0))

        offsets, info = cg(
            operator,
            rhs,
            M=preconditioner,
            rtol=1e-11,
            atol=1e-10,
            maxiter=10000,
            callback=callback,
        )
        check_cancel()
        if info != 0 or not np.isfinite(offsets).all():
            raise ValueError(
                "Crossover OLS solver did not converge; no output applied."
            )
        means = (
            np.bincount(component_labels, weights=offsets, minlength=components)
            / counts
        )
        offsets -= means[component_labels]
        after = before + A @ offsets
        normal_max = float(np.max(abs(A.T @ after)))
        tolerance = max(1e-7, 1e-8 * float(np.max(abs(rhs))))
        if (
            normal_max > tolerance
            or np.linalg.norm(after) > np.linalg.norm(before) + 1e-8
        ):
            raise ValueError("Crossover OLS validation failed; no output applied.")
        solver_status = "converged_normal_equations"
    elif on_no_crossovers == "raise":
        raise ValueError(
            "No real point crossovers found; median removal alone is not crossover levelling."
        )
    if workflow == "tie_lines":
        missing = [
            item["track"] + "/" + item["sensor"]
            for pid, item in enumerate(first["profiles"])
            if item["valid_rows"] and degrees[pid] == 0
        ]
        if missing:
            raise ValueError(
                "Primary profiles without real tie-line crossings: "
                + ", ".join(missing)
            )
        if not crossings:
            raise ValueError("Tie-line leveling needs real point crossings.")
    update(0.95)
    unsupported = np.flatnonzero(degrees == 0).tolist()
    for pid, item in enumerate(profiles):
        item.update(
            component=int(component_labels[pid]),
            correction_nT=float(offsets[pid]),
            status="no_crossovers_unadjusted"
            if degrees[pid] == 0
            else "fitted_from_crossovers",
        )
    for prepared, start in [(first, 0), (second, nfirst)]:
        correction = np.full(len(prepared["frame"]), np.nan)
        valid = prepared["valid"]
        correction[valid] = offsets[start + prepared["profile"][valid]]
        prepared["frame"]["Crosslevel_correction_nT"] = correction
        prepared["frame"]["Crosslevelled_nT"] = prepared["baseline"] + correction

    def rms(values):
        return float(np.sqrt(np.mean(values * values))) if len(values) else None

    active_components = len(np.unique(component_labels[degrees > 0]))
    report = {
        "algorithm": "fixed_medians_real_crossovers_order0",
        "status": "levelled" if crossings else "no_crossovers_unadjusted",
        "absolute_field_preserved": False,
        "historical_pipeline_equivalence_validated": False,
        "intersections": len(crossings),
        "intersection_candidates": candidates,
        "nonpoint_overlaps_excluded": overlaps,
        "duplicate_endpoint_intersections_removed": duplicates,
        "before_crosslevel_rms_nT": rms(before),
        "after_crosslevel_rms_nT": rms(after),
        "first_geometry": first["qc"],
        "second_geometry": second["qc"],
        "profiles": profiles,
        "unsupported_profiles": unsupported,
        "solver": {
            "status": solver_status,
            "iterations": iterations,
            "normal_equation_max_abs": normal_max,
            "graph_components": active_components,
            "gauge": "Zero mean correction per connected component; relative levelling only.",
        },
        "limits": {
            "max_segments_per_input": int(max_segments),
            "max_intersection_candidates": int(max_crossings),
        },
        "segment_arrays_bytes": int(
            sum(
                p[k].nbytes
                for p in [first, second]
                for k in ["coords", "starts", "ends", "segment_profiles"]
            )
        ),
        "notes": [
            "Median removal is fitted independently to each input sensor and track/sensor profile.",
            "Crossovers constrain relative order-zero offsets, not field truth or regional baseline.",
            "Disconnected components have independent gauges; unsupported profiles receive zero crossover correction.",
            "Gaps use twice each profile's median positive numeric time interval; very short profiles cannot establish reliable sampling.",
        ],
    }
    report["baseline_mode"] = "none" if workflow == "tie_lines" else baseline_mode
    if workflow == "crosshatch" and baseline_mode != "sensor_profile":
        report["algorithm"] = "real_crossovers_order0_" + baseline_mode
        report["notes"][0] = "Baseline removal: " + baseline_mode + "."
    if workflow == "tie_lines":
        report.update(
            algorithm="primary_lines_anchored_to_tie_lines_order0",
            absolute_field_preserved=True,
            reference="Second input tie-line readings held fixed; first input primary profiles corrected.",
            gridding_inputs=[1],
            tie_lines_unchanged=True,
            notes=[
                "No sensor or profile median subtraction is performed by this leveling step.",
                "Each primary track/sensor profile receives the negative mean of its primary-minus-tie crossover differences.",
                "Only exact point intersections are used; no nearest-line extrapolation.",
            ],
        )
        report["solver"]["gauge"] = "Tie-line corrections fixed at zero."
        for pid, item in enumerate(report["profiles"]):
            item["role"] = "primary" if pid < nfirst else "tie"
            item["intersections"] = int(degrees[pid])
            if pid >= nfirst:
                item["status"] = "fixed_reference"
    update(1.0)
    return first["frame"], second["frame"], report

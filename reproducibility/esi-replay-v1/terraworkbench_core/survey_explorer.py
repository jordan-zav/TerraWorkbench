"""Read-only paged tables and bounded profile previews, without a GUI host.

Profiles retain selection order, null gaps and contiguous line/sensor runs.
Envelope reduction is DISPLAY ONLY; neither channels nor recipes are modified.
"""

import numpy as np

from ._calibration import integer_budget


def _check(cancel):
    if cancel is not None and cancel():
        raise InterruptedError("Survey preview cancelled")


def survey_group_values(
    store, database_id, columns, *, max_values=2000, cancel=None, progress=None
):
    """Discover bounded selector values without caching or modifying the survey."""
    import pyarrow.compute as pc

    integer_budget(max_values, "max_values", 1)
    columns = list(dict.fromkeys(columns))
    if not columns:
        raise ValueError("Choose grouping channels first")
    found = {name: set() for name in columns}
    truncated = {name: False for name in columns}
    count = 0
    batches = store.batches(database_id, columns, canceled=cancel)
    try:
        for batch in batches:
            _check(cancel)
            count += len(batch)
            for name in columns:
                for item in pc.unique(batch.column(name)).to_pylist():
                    if (
                        item is None
                        or isinstance(item, float)
                        and not np.isfinite(item)
                    ):
                        continue
                    if not isinstance(item, (str, int, float, bool)):
                        raise ValueError(
                            "Selector channels must contain scalar text or numbers"
                        )
                    label = str(item)
                    if label not in found[name]:
                        if len(found[name]) >= max_values:
                            truncated[name] = True
                        else:
                            found[name].add(label)
            if progress:
                progress(count)
    finally:
        batches.close()
    _check(cancel)
    return {
        "rows": count,
        "values": {name: sorted(values) for name, values in found.items()},
        "truncated": truncated,
    }


def read_survey_page(
    store,
    database_id,
    columns,
    *,
    offset=0,
    limit=200,
    filters=None,
    cancel=None,
    progress=None,
):
    """Read limit rows plus one look-ahead, offset relative to filtered selection.

    Only selected/filter columns are read. Offsets currently scan preceding
    selected rows: no spatial/line index or constant-time random access claimed.
    Does not compute a full filtered row count just to display a page.
    """
    integer_budget(offset, "offset", 0)
    integer_budget(limit, "limit")
    if limit > 2000 or not columns or len(set(columns)) != len(columns):
        raise ValueError("Choose unique columns and a page size <=2000")
    _check(cancel)
    data = {name: [] for name in columns}
    seen = taken = 0
    batches = store.batches(database_id, columns, filters=filters, canceled=cancel)
    try:
        for batch in batches:
            _check(cancel)
            skip = min(max(0, offset - seen), len(batch))
            seen += len(batch)
            if skip < len(batch):
                chunk = batch.slice(skip, min(len(batch) - skip, limit + 1 - taken))
                for name in columns:
                    data[name].extend(chunk.column(name).to_pylist())
                taken += len(chunk)
            if progress:
                progress(seen)
            if taken > limit:
                break
    finally:
        batches.close()
    _check(cancel)
    return {
        "columns": list(columns),
        "data": {name: values[:limit] for name, values in data.items()},
        "offset": offset,
        "rows": min(taken, limit),
        "has_next": taken > limit,
    }


def _envelope(y, budget):
    if len(y) <= budget:
        return np.arange(len(y))
    chosen = [0, len(y) - 1]
    bins = (budget - 2) // 2
    if bins:
        edges = np.linspace(1, len(y) - 1, bins + 1, dtype=int)
        for first, stop in zip(edges[:-1], edges[1:]):
            if stop > first:
                values = y[first:stop]
                chosen.extend(
                    [first + int(np.argmin(values)), first + int(np.argmax(values))]
                )
    return np.unique(chosen)


def compare_survey_profiles(store, database_id, primary, secondary, **options):
    """Row-aligned A/B and B-A previews, never interpolation or unit conversion."""
    import pyarrow as pa
    import pyarrow.compute as pc

    if primary == secondary:
        raise ValueError("Choose two different channels")
    before = {row["name"]: row for row in store.channels(database_id)}
    difference_name = "@difference"
    while difference_name in before:
        difference_name += "_"
    if (
        not before[primary]["unit"]
        or before[primary]["unit"] != before[secondary]["unit"]
    ):
        raise ValueError(
            "Comparison requires identical explicitly declared units; no automatic conversion"
        )
    options = dict(options)
    options["max_points"] = min(options.get("max_points", 6000), 3000)
    first = read_survey_profile(store, database_id, primary, **options)
    second = read_survey_profile(store, database_id, secondary, **options)
    dependencies = set()

    class DifferenceReader:
        def batches(self, database, columns, **kwargs):
            source_columns = list(
                dict.fromkeys(
                    [name for name in columns if name != difference_name]
                    + [primary, secondary]
                )
            )
            dependencies.update(source_columns)
            batches = store.batches(database, source_columns, **kwargs)
            try:
                for batch in batches:
                    difference = pc.subtract(
                        batch.column(secondary).cast(pa.float64()),
                        batch.column(primary).cast(pa.float64()),
                    )
                    yield pa.record_batch(
                        [
                            difference
                            if name == difference_name
                            else batch.column(name)
                            for name in columns
                        ],
                        names=columns,
                    )
            finally:
                batches.close()

    difference = read_survey_profile(
        DifferenceReader(), database_id, difference_name, **options
    )
    dependencies.update((options.get("filters") or {}).keys())
    after = {row["name"]: row for row in store.channels(database_id)}
    if any(
        name not in after
        or before[name]["version_id"] != after[name]["version_id"]
        or before[name]["unit"] != after[name]["unit"]
        for name in dependencies
    ):
        raise ValueError(
            "Compared channel versions or units changed during preview; reload"
        )
    return {
        "primary": first,
        "secondary": second,
        "difference": difference,
        "unit": before[primary]["unit"],
        "inputs": {name: before[name]["version_id"] for name in dependencies},
    }


def read_survey_profile(
    store,
    database_id,
    channel,
    *,
    axis=None,
    group=None,
    sensor=None,
    distance_columns=None,
    source_crs=None,
    filters=None,
    max_samples=3_000_000,
    max_points=6000,
    max_segments=256,
    cancel=None,
    progress=None,
):
    """Bounded min/max envelope with statistics from ALL valid selected samples.

    Numeric values/axis required; numeric text is accepted, malformed text is not
    silently discarded. Default x is one-based selected-sample ordinal, NOT original row ID
    or distance. No sorting/interpolation or physical coordinate conversion.
    Nulls, group changes and nonincreasing explicit axes split display paths.
    Reappearing groups do not join. Reject selections exceeding explicit budgets.
    """
    for value, name, minimum in (
        (max_samples, "max_samples", 1),
        (max_points, "max_points", 16),
        (max_segments, "max_segments", 1),
    ):
        integer_budget(value, name, minimum)
    _check(cancel)
    if distance_columns and (
        len(distance_columns) != 2
        or len(set(distance_columns)) != 2
        or not source_crs
        or axis
    ):
        raise ValueError(
            "Distance requires distinct X/Y columns, an explicit CRS and no alternate axis"
        )
    groups = list(dict.fromkeys(name for name in (group, sensor) if name))
    names = list(
        dict.fromkeys(
            [channel, *([axis] if axis else []), *groups, *(distance_columns or [])]
        )
    )
    batches = store.batches(database_id, names, filters=filters, canceled=cancel)
    xs, ys, spans = [], [], []
    count = 0
    previous = None
    previous_x = None
    previous_valid = False
    distance_y = []
    try:
        for batch in batches:
            _check(cancel)
            if count + len(batch) > max_samples:
                raise ValueError(
                    "Profile selection exceeds sample budget; select a transect or sensor first"
                )
            if not len(batch):
                continue
            import pyarrow as pa

            try:
                y = (
                    batch.column(channel)
                    .cast(pa.float64())
                    .to_numpy(zero_copy_only=False)
                )
                x = (
                    batch.column(axis).cast(pa.float64()).to_numpy(zero_copy_only=False)
                    if axis
                    else np.arange(count + 1, count + len(batch) + 1, dtype=float)
                )
            except (pa.ArrowInvalid, pa.ArrowNotImplementedError) as error:
                raise ValueError("Profile channel and axis must be numeric") from error
            valid = np.isfinite(x) & np.isfinite(y)
            if distance_columns:
                x = (
                    batch.column(distance_columns[0])
                    .cast(pa.float64())
                    .to_numpy(zero_copy_only=False)
                )
                coordinate_y = (
                    batch.column(distance_columns[1])
                    .cast(pa.float64())
                    .to_numpy(zero_copy_only=False)
                )
                distance_y.append(coordinate_y)
                valid &= np.isfinite(x) & np.isfinite(coordinate_y)
            labels = [
                batch.column(name).to_numpy(zero_copy_only=False) for name in groups
            ]
            changed = np.zeros(len(batch), bool)
            for name, values in zip(groups, labels):
                valid &= ~batch.column(name).is_null().to_numpy(zero_copy_only=False)
                if values.dtype.kind in "f":
                    valid &= np.isfinite(values)
                changed[1:] |= values[1:] != values[:-1]
            if axis:
                changed[1:] |= np.diff(x) <= 0
            breaks = np.ones(len(batch), bool)
            breaks[1:] = changed[1:] | ~valid[:-1] | ~valid[1:]
            starts = np.flatnonzero(valid & breaks)
            stops = np.flatnonzero(valid & np.r_[breaks[1:], True]) + 1
            first_group = tuple(values[0] for values in labels)
            continuous = (
                previous_valid
                and valid[0]
                and first_group == previous
                and (not axis or x[0] > previous_x)
            )
            for first, stop in zip(starts, stops):
                if first == 0 and continuous:
                    spans[-1][1] = count + int(stop)
                else:
                    label = " · ".join(
                        f"{name}: {values[first]}"
                        for name, values in zip(groups, labels)
                    )
                    spans.append([count + int(first), count + int(stop), label])
                    if len(spans) > max_segments:
                        raise ValueError(
                            "Too many profile discontinuities; narrow the transect/sensor selection"
                        )
            xs.append(x)
            ys.append(y)
            count += len(batch)
            previous = tuple(values[-1] for values in labels)
            previous_x = x[-1]
            previous_valid = bool(valid[-1])
            if progress:
                progress(count)
    finally:
        batches.close()
    _check(cancel)
    x = np.concatenate(xs) if xs else np.empty(0)
    y = np.concatenate(ys) if ys else np.empty(0)
    if distance_columns:
        from .profile_distance import along_profile_distance

        coordinate_y = np.concatenate(distance_y) if distance_y else np.empty(0)
        distance_x = np.full(x.shape, np.nan)
        for first, stop, _ in spans:
            _check(cancel)
            distance_x[first:stop] = along_profile_distance(
                x[first:stop], coordinate_y[first:stop], source_crs
            )
        x = distance_x
    lengths = np.array([stop - first for first, stop, _ in spans], dtype=int)
    valid_count = int(lengths.sum())
    minimum = np.minimum(lengths, 2)
    if minimum.sum() > max_points:
        raise ValueError(
            "Too many profile segments for the display budget; narrow the selection"
        )
    remaining = max_points - int(minimum.sum())
    budgets = minimum + (np.floor(remaining * lengths / max(1, valid_count))).astype(
        int
    )
    segments = []
    valid_values = []
    for (first, stop, label), budget in zip(spans, budgets):
        _check(cancel)
        values = y[first:stop]
        valid_values.append(values)
        selected = _envelope(values, int(budget))
        segments.append(
            {"x": x[first:stop][selected], "y": values[selected], "label": label}
        )
    valid_y = np.concatenate(valid_values) if valid_values else np.empty(0)
    shown = sum(len(segment["x"]) for segment in segments)
    return {
        "channel": channel,
        "axis": axis,
        "rows": count,
        "valid_rows": valid_count,
        "excluded_rows": count - valid_count,
        "segments": segments,
        "display_points": shown,
        "reduced": shown < valid_count,
        "minimum": float(valid_y.min()) if valid_count else None,
        "maximum": float(valid_y.max()) if valid_count else None,
        "mean": float(valid_y.mean()) if valid_count else None,
        "std": float(valid_y.std()) if valid_count else None,
        "sampling": "min/max envelope for display only; statistics from full valid selection",
    }

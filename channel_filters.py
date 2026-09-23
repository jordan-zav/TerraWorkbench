"""Independent 1D survey filters; never sort, interpolate gaps or join runs."""

from dataclasses import asdict, dataclass

import numpy as np


METHODS = ("mean", "median", "despike", "detrend", "lowpass", "highpass", "bandpass")


@dataclass
class ChannelFilterOptions:
    method: str = "mean"
    domain: str = "samples"
    axis: str = ""
    group: str = ""
    sensor: str = ""
    max_gap: float = 1.5
    window: int = 5
    threshold: float = 3.0
    order: int = 4
    cutoff: float = 0.1
    upper_cutoff: float = 0.2
    spacing_tolerance: float = 0.01
    max_segment_rows: int = 3_000_000

    def validate(self):
        if self.method not in METHODS or self.domain not in ("samples", "time", "distance"):
            raise ValueError("Unknown channel filter or domain.")
        if self.domain != "samples" and not self.axis:
            raise ValueError("Time/distance requires an explicit numeric axis channel.")
        if self.domain == "samples" and self.axis:
            raise ValueError("Sample domain uses row order, not an axis channel.")
        if self.group and self.sensor and self.group == self.sensor:
            raise ValueError("Line and sensor channels must be distinct.")
        if not np.isfinite(self.max_gap) or self.max_gap <= 0:
            raise ValueError("Maximum gap must be positive and finite.")
        if type(self.window) is not int or not 3 <= self.window <= 1001 or self.window % 2 != 1:
            raise ValueError("Window must be odd, between 3 and 1001 samples.")
        if not np.isfinite(self.threshold) or self.threshold <= 0:
            raise ValueError("Spike threshold must be positive and finite.")
        if type(self.order) is not int or not 1 <= self.order <= 10:
            raise ValueError("Butterworth order must be between 1 and 10.")
        if not np.isfinite(self.cutoff) or self.cutoff <= 0:
            raise ValueError("Cutoff must be positive and finite.")
        if self.method == "bandpass" and (not np.isfinite(self.upper_cutoff) or self.upper_cutoff <= self.cutoff):
            raise ValueError("Band upper cutoff must exceed the lower cutoff.")
        if not np.isfinite(self.spacing_tolerance) or not 0 <= self.spacing_tolerance <= 0.05:
            raise ValueError("Spacing tolerance must be between 0 and 5%.")
        if type(self.max_segment_rows) is not int or not 2 <= self.max_segment_rows <= 3_000_000:
            raise ValueError("Segment limit must be between 2 and 3,000,000 rows.")

    def to_dict(self):
        return asdict(self)


def filter_segment(axis, values, options, canceled=None):
    """One finite, strictly increasing run. Return values and diagnostic counts.

    Moving filters use centered complete sample windows, with null edges.
    Despiking is a Hampel detector: median +/- threshold * 1.4826 * MAD.
    Butterworth is zero-phase SOS forward/backward, with odd endpoint padding.
    Short segments become null, never silently copied as if filtered.
    """
    from scipy.signal import butter, sosfiltfilt

    options.validate()
    x, y = np.asarray(axis, dtype=float), np.asarray(values, dtype=float)
    if x.ndim != 1 or y.shape != x.shape or not len(x) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Segment must contain aligned finite coordinates and values.")
    if len(x) > options.max_segment_rows:
        raise ValueError("Segment exceeds the configured memory safety limit.")
    spacing = np.diff(x)
    if np.any(spacing <= 0):
        raise ValueError("Axis must increase strictly within each contiguous line/sensor run; no automatic sorting.")
    result = np.full(len(y), np.nan)
    diagnostics = {"segments": 1, "short_segments": 0, "spikes_replaced": 0}

    def cancel():
        if canceled and canceled():
            raise InterruptedError("Channel filtering canceled.")

    cancel()
    if options.method in ("mean", "median", "despike"):
        width = options.window
        if len(y) < width:
            diagnostics["short_segments"] = 1
        else:
            half = width // 2
            # Bounded work arrays, even for large user windows.
            block = max(1, 262144 // width)
            windows = np.lib.stride_tricks.sliding_window_view(y, width)
            for start in range(0, len(windows), block):
                cancel()
                chunk = windows[start:start + block]
                center = slice(start + half, start + half + len(chunk))
                if options.method == "mean":
                    result[center] = np.mean(chunk, axis=1)
                else:
                    median = np.median(chunk, axis=1)
                    if options.method == "median":
                        result[center] = median
                    else:
                        mad = np.median(np.abs(chunk - median[:, None]), axis=1)
                        spike = np.abs(y[center] - median) > options.threshold * 1.4826 * mad
                        result[center] = np.where(spike, median, y[center])
                        diagnostics["spikes_replaced"] += int(spike.sum())
    elif options.method == "detrend":
        if len(y) < 2:
            diagnostics["short_segments"] = 1
        else:
            normalized = (x - x[0]) / (x[-1] - x[0])
            normalized -= normalized.mean()
            centered = y - y.mean()
            result = centered - normalized * (np.dot(normalized, centered) / np.dot(normalized, normalized))
    elif len(y) < 2:
        diagnostics["short_segments"] = 1
    else:
        delta = float(np.median(spacing))
        if np.any(np.abs(spacing - delta) > options.spacing_tolerance * delta + 1e-12 * delta):
            raise ValueError("Butterworth requires regular sampling within the chosen tolerance; no implicit resampling.")
        cutoffs = [options.cutoff, options.upper_cutoff] if options.method == "bandpass" else options.cutoff
        if np.max(cutoffs) >= 0.5 / delta:
            raise ValueError(f"Cutoff must be below Nyquist ({0.5 / delta:g} cycles/axis unit).")
        sos = butter(options.order, cutoffs, btype=options.method, fs=1.0 / delta, output="sos")
        pad = 3 * (2 * len(sos) + 1 - min((sos[:, 2] == 0).sum(), (sos[:, 5] == 0).sum()))
        if len(y) <= pad + 1:
            diagnostics["short_segments"] = 1
        else:
            result = sosfiltfilt(sos, y, padtype="odd", padlen=int(pad))
            if not np.isfinite(result).all():
                raise ValueError("Nonfinite Butterworth result; output not published.")
    cancel()
    expected = result
    if options.method in ("mean", "median", "despike"):
        expected = result[options.window // 2:len(result) - options.window // 2]
    if np.isinf(result).any() or (not diagnostics["short_segments"] and not np.isfinite(expected).all()):
        raise ValueError("Filter overflow; output not published.")
    return result, diagnostics


def filtered_runs(batches, channel, options, stats, canceled=None):
    """Stream contiguous runs across Arrow batches, preserving original row order.

    Null/NaN values, null groups and axis gaps split runs. Group transitions
    always split, even when a group reappears later. Each run is bounded in size.
    """
    options.validate()
    xs, ys = [], []
    previous_group = None
    previous_axis = None
    rows = 0
    missing = 0

    def check():
        if canceled and canceled():
            raise InterruptedError("Channel filtering canceled.")

    def flush():
        if ys:
            result, counts = filter_segment(xs, ys, options, canceled)
            for key, value in counts.items():
                stats[key] = stats.get(key, 0) + value
            xs.clear()
            ys.clear()
            return result
        return np.empty(0)

    for batch in batches:
        check()
        data = batch.to_pydict()
        for index in range(len(batch)):
            rows += 1
            if rows % 1024 == 0:
                check()
            group = tuple(data[name][index] for name in (options.group, options.sensor) if name)
            if group != previous_group:
                output = flush()
                if len(output):
                    yield output
                previous_axis = None
                previous_group = group
            try:
                raw = data[channel][index]
                value = float(raw) if raw is not None else np.nan
                raw_axis = data[options.axis][index] if options.axis else None
                axis = float(raw_axis) if raw_axis is not None else (float(rows) if not options.axis else np.nan)
            except (TypeError, ValueError, OverflowError) as error:
                raise ValueError(f"Row {rows}: nonnumeric signal or axis in {channel!r}.") from error
            if np.isinf(value) or np.isinf(axis):
                raise ValueError(f"Row {rows}: infinite signal or axis.")
            valid_group = all(v is not None and not (isinstance(v, float) and np.isnan(v)) for v in group)
            if not np.isfinite(value) or not np.isfinite(axis) or not valid_group:
                output = flush()
                if len(output):
                    yield output
                missing += 1
                previous_axis = None
                stats["input_null_rows"] = stats.get("input_null_rows", 0) + 1
                if missing >= 65536:
                    yield np.full(missing, np.nan)
                    missing = 0
                continue
            if missing:
                yield np.full(missing, np.nan)
                missing = 0
            if previous_axis is not None:
                delta = axis - previous_axis
                if delta <= 0:
                    raise ValueError(f"Row {rows}: axis is duplicated or decreasing within a run. Sort/prepare it explicitly.")
                if options.axis and delta > options.max_gap:
                    output = flush()
                    if len(output):
                        yield output
                    stats["gap_splits"] = stats.get("gap_splits", 0) + 1
            if len(ys) >= options.max_segment_rows:
                raise ValueError(f"Row {rows}: segment exceeds {options.max_segment_rows:,} rows; reduce run size explicitly.")
            xs.append(axis)
            ys.append(value)
            previous_axis = axis
    output = flush()
    if len(output):
        yield output
    if missing:
        yield np.full(missing, np.nan)

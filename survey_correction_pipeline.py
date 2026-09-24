"""Explicit magnetic corrections on contiguous track/sensor runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import numpy as np

if __package__:
    from .channel_filters import ChannelFilterOptions, filter_segment
    from .survey_corrections import interpolate_base_variation, heading_correction
else:
    from channel_filters import ChannelFilterOptions, filter_segment
    from survey_corrections import interpolate_base_variation, heading_correction


@dataclass
class MagneticCorrectionOptions:
    max_gap_seconds: float = .02
    lag_seconds: float | None = None
    despike_window: int = 0
    despike_threshold: float = 6.
    heading_cosine: float | None = None
    heading_sine: float | None = None

    def validate(self):
        if not np.isfinite(self.max_gap_seconds) or self.max_gap_seconds <= 0:
            raise ValueError("A positive maximum time gap in seconds is required.")
        if self.lag_seconds is not None and not np.isfinite(self.lag_seconds):
            raise ValueError("Lag must be finite seconds or disabled.")
        heading = (self.heading_cosine, self.heading_sine)
        if any(v is not None for v in heading) and not all(v is not None and np.isfinite(v) for v in heading):
            raise ValueError("Supply both finite heading coefficients or disable heading correction.")
        if type(self.despike_window) is not int or self.despike_window < 0:
            raise ValueError("Despike window must be zero or an odd number of samples.")
        if self.despike_window:
            ChannelFilterOptions(method="despike", window=self.despike_window,
                                 threshold=self.despike_threshold).validate()


def correct_magnetic_arrays(values, time_seconds, tracks, sensors, options,
                            base_time=None, base_value=None, base_reference=None,
                            azimuth_degrees=None, canceled=None):
    """Return additive terms and corrected field; never cross gaps or sort rows.

    Heading azimuth is clockwise from true north, in degrees. Lag samples at
    t + lag; no extrapolation. Moving despike requires complete windows, so its
    edges are missing. Base and survey timestamps must share a time reference.
    """
    options.validate()
    raw = np.asarray(values, dtype=float)
    time = np.asarray(time_seconds, dtype=float)
    tracks, sensors = np.asarray(tracks), np.asarray(sensors)
    if raw.ndim != 1 or not raw.size or any(a.shape != raw.shape for a in (time, tracks, sensors)):
        raise ValueError("Aligned, nonempty one-dimensional channels are required.")
    if np.isinf(raw).any() or np.isinf(time).any():
        raise ValueError("Infinite signal or timestamps are not supported.")
    if any(v is None or (isinstance(v, float) and np.isnan(v)) for a in (tracks, sensors) for v in a):
        raise ValueError("Track and sensor identifiers cannot be missing.")
    if (base_time is None) != (base_value is None):
        raise ValueError("Base times and values must be supplied together.")
    base_enabled = base_time is not None
    if base_enabled:
        bt, bv = np.asarray(base_time, dtype=float), np.asarray(base_value, dtype=float)
        if bt.ndim != 1 or bt.shape != bv.shape or bt.size < 2 or not np.isfinite(bt).all() or not np.isfinite(bv).all() or np.any(np.diff(bt) <= 0):
            raise ValueError("Base observations must be finite and strictly increasing.")
        if base_reference is None or not np.isfinite(base_reference):
            raise ValueError("An explicit finite base reference is required.")
        base_term = -interpolate_base_variation(time, bt, bv, base_reference)
    else:
        base_term = np.zeros(raw.shape)
    heading_enabled = options.heading_cosine is not None
    if heading_enabled:
        azimuth = np.asarray(azimuth_degrees, dtype=float)
        if azimuth.shape != raw.shape:
            raise ValueError("Heading requires an aligned true-north azimuth channel in degrees.")
        heading_term = heading_correction(azimuth, options.heading_cosine, options.heading_sine)
        heading_term[~np.isfinite(azimuth)] = np.nan
    else:
        heading_term = np.zeros(raw.shape)
    valid = np.isfinite(raw) & np.isfinite(time)
    same_group = (tracks[1:] == tracks[:-1]) & (sensors[1:] == sensors[:-1])
    adjacent = same_group & valid[1:] & valid[:-1]
    delta = np.diff(time)
    if np.any(adjacent & (delta <= 0)):
        raise ValueError("Timestamps must increase within each contiguous track/sensor run.")
    breaks = ~adjacent | (delta > options.max_gap_seconds)
    boundaries = np.r_[0, np.flatnonzero(breaks) + 1, len(raw)]
    shifted, despiked = np.full(raw.shape, np.nan), np.full(raw.shape, np.nan)
    counts = {"segments": 0, "spikes_replaced": 0, "short_segments": 0}
    for start, stop in zip(boundaries[:-1], boundaries[1:]):
        if canceled and canceled():
            raise InterruptedError("Magnetic corrections canceled.")
        if not valid[start]:
            continue
        counts["segments"] += 1
        t, v = time[start:stop], raw[start:stop]
        lag = options.lag_seconds
        shifted[start:stop] = v if lag is None or lag == 0 else np.interp(t + lag, t, v, left=np.nan, right=np.nan)
        usable = np.flatnonzero(np.isfinite(shifted[start:stop]))
        if not len(usable):
            continue
        first, last = start + usable[0], start + usable[-1] + 1
        if options.despike_window:
            filtered, stats = filter_segment(time[first:last], shifted[first:last],
                ChannelFilterOptions(method="despike", window=options.despike_window,
                                     threshold=options.despike_threshold), canceled)
            despiked[first:last] = filtered
            counts["spikes_replaced"] += stats["spikes_replaced"]
            counts["short_segments"] += stats["short_segments"]
        else:
            despiked[first:last] = shifted[first:last]
    corrected = despiked + base_term + heading_term
    result = {"lag_delta": shifted - raw, "despike_delta": despiked - shifted,
              "base_delta": base_term, "heading_delta": heading_term,
              "total_delta": corrected - raw, "corrected": corrected}
    for key, array in result.items():
        array[~valid] = np.nan
        if np.isinf(array).any():
            raise ValueError(f"Correction overflow: {key}")
    recipe = {"parameters": asdict(options), "statistics": counts,
              "rows": len(raw), "valid_output_rows": int(np.isfinite(corrected).sum()),
              "enabled": {"lag": options.lag_seconds is not None, "despike": bool(options.despike_window),
                          "base": base_enabled, "heading": heading_enabled},
              "base_reference": base_reference, "heading_frame": "true north, degrees",
              "ordering": "original contiguous track/sensor runs; split at missing data and time gaps",
              "formula": "raw + lag_delta + despike_delta + base_delta + heading_delta",
              "missing_policy": "no lag/base extrapolation; complete despike windows only"}
    return result, recipe

"""Seismic/GPR array kernels: rows traces, last axis uniformly sampled time.

Time seconds, distance metres, velocity m/s. These kernels do not establish
SEG-Y/GPR format support, sensor response removal or an interpreted model.
Missing samples must be handled explicitly; finite input is required except
where an interpolation operation deliberately creates an unsupported mask.
"""

import numpy as np
from scipy import ndimage, signal
from scipy.optimize import least_squares

from ._array_contract import as_array


def _traces(values, dt_s, *, max_elements=5_000_000):
    a = as_array(values, float)
    if a.ndim != 2 or not len(a) or a.shape[1] < 4 or not np.isfinite(a).all():
        raise ValueError(
            "Finite (trace,time) array with at least four samples required"
        )
    if not np.isfinite(dt_s) or dt_s <= 0 or a.size > max_elements:
        raise ValueError("Positive sample interval and bounded trace matrix required")
    return a


def trace_bandpass(traces, dt_s, low_hz, high_hz, *, order=4):
    """Zero-phase two-pass Butterworth SOS; edge padding from SciPy is explicit.

    Two passes square the single-pass amplitude response. No detrending,
    calibration or amplitude normalization occurs. Short records are rejected.
    """
    a = _traces(traces, dt_s)
    if (
        not np.isfinite([low_hz, high_hz]).all()
        or not 0 < low_hz < high_hz < 0.5 / dt_s
        or isinstance(order, bool)
        or not isinstance(order, (int, np.integer))
        or not 1 <= order <= 12
    ):
        raise ValueError("Require 0<low<high<Nyquist and integer order in 1..12")
    sos = signal.butter(
        order, [low_hz, high_hz], fs=1 / dt_s, btype="bandpass", output="sos"
    )
    filtered = signal.sosfiltfilt(sos, a, axis=-1)
    return {
        "traces": filtered,
        "dt_s": dt_s,
        "sos": sos,
        "zero_phase": True,
        "amplitude_note": "two-pass Butterworth, no gain compensation",
    }


def dewow(traces, dt_s, window_samples):
    """Subtract centered moving time mean with reflected boundaries.

    Integer odd window; not a proprietary dewow reproduction. Long physical
    wavelets/low frequencies may be removed; the actual removed trend is returned.
    """
    a = _traces(traces, dt_s)
    if (
        isinstance(window_samples, bool)
        or not isinstance(window_samples, (int, np.integer))
        or not 3 <= window_samples <= a.shape[1]
        or window_samples % 2 != 1
    ):
        raise ValueError("Odd window of 3..record-length samples required")
    trend = ndimage.uniform_filter1d(a, size=window_samples, axis=-1, mode="reflect")
    return {
        "traces": a - trend,
        "removed_trend": trend,
        "dt_s": dt_s,
        "window_samples": int(window_samples),
        "boundary": "reflect",
    }


def remove_trace_background(traces, dt_s, *, method="mean", reference_traces=None):
    """Subtract across-trace reference mean/median at each time sample.

    Not temporal filtering. Can remove real horizontal reflectors; return the
    removed background and energy ratio, not a guarantee of signal retention.
    reference_traces is an explicit boolean selection; default uses all traces.
    """
    a = _traces(traces, dt_s)
    use = (
        np.ones(len(a), bool)
        if reference_traces is None
        else as_array(reference_traces)
    )
    if (
        use.shape != (len(a),)
        or use.dtype.kind != "b"
        or not use.any()
        or method not in ("mean", "median")
    ):
        raise ValueError("Require nonempty boolean reference selection and mean/median")
    background = (np.mean if method == "mean" else np.median)(a[use], axis=0)
    output = a - background
    original_energy = np.sum(a * a, axis=-1)
    ratio = np.divide(
        np.sum(output * output, axis=-1),
        original_energy,
        out=np.full(len(a), np.nan),
        where=original_energy > 0,
    )
    return {
        "traces": output,
        "removed_background": background,
        "energy_ratio": ratio,
        "reference_traces": use.copy(),
        "method": method,
        "warning": "Coherent geological signal can be removed with background",
    }


def correct_time_zero(traces, dt_s, zero_times_s):
    """Linear resampling: output(t)=input(t+zero), output time starts at zero.

    Explicit per-trace zero relative to original first sample. Out-of-support
    values become NaN, not zero. Filter complete records before this operation,
    or select a common supported window before subsequent finite-only filters.
    """
    a = _traces(traces, dt_s)
    zero = as_array(zero_times_s, float)
    if zero.shape != (len(a),) or not np.isfinite(zero).all():
        raise ValueError("Finite explicit time zero per trace required")
    times = np.arange(a.shape[1]) * dt_s
    output = np.array(
        [
            np.interp(times + shift, times, row, left=np.nan, right=np.nan)
            for row, shift in zip(a, zero)
        ]
    )
    return {
        "traces": output,
        "times_s": times,
        "valid": np.isfinite(output),
        "zero_times_s": zero.copy(),
        "interpolation": "linear, no extrapolation",
    }


def explicit_time_gain(
    traces, dt_s, *, reference_time_s, power=0.0, exponential_rate_s=0.0, max_gain
):
    """Apply g(t)=(1+t/tref)^power*exp(rate*t), capped at explicit max_gain.

    Return gain for reproducibility/undo. Not absorption compensation without
    independent calibration; no AGC or undocumented amplitude equalization.
    """
    a = _traces(traces, dt_s)
    if (
        not np.isfinite([reference_time_s, power, exponential_rate_s, max_gain]).all()
        or reference_time_s <= 0
        or power < 0
        or exponential_rate_s < 0
        or max_gain < 1
    ):
        raise ValueError("Require tref>0, nonnegative power/rate and max_gain>=1")
    times = np.arange(a.shape[1]) * dt_s
    log_gain = power * np.log1p(times / reference_time_s) + exponential_rate_s * times
    gain = np.exp(np.minimum(log_gain, np.log(max_gain)))
    return {
        "traces": a * gain,
        "gain": gain,
        "capped": log_gain > np.log(max_gain),
        "warning": "Gain changes quantitative amplitudes unless independently calibrated",
    }


def fit_diffraction_hyperbola(
    positions_m,
    travel_times_s,
    *,
    time_std_s,
    initial,
    velocity_bounds_m_s,
    max_evaluations=100,
):
    """Fit zero-offset point-diffractor t^2=t0^2+4*(x-x0)^2/v^2.

    Explicit (x0,t0,v) initial guess and velocity bounds. Homogeneous velocity,
    zero antenna separation, flat datum; not a general CMP/tomographic model.
    Covariance is local conditional least-squares, excluding pick/model bias.
    """
    x, times, std, start, bounds = [
        as_array(a, float)
        for a in (positions_m, travel_times_s, time_std_s, initial, velocity_bounds_m_s)
    ]
    if (
        x.ndim != 1
        or x.size < 5
        or x.size > 100000
        or times.shape != x.shape
        or std.shape != x.shape
        or start.shape != (3,)
        or bounds.shape != (2,)
        or not all(np.isfinite(a).all() for a in (x, times, std, start, bounds))
        or np.any(times <= 0)
        or np.any(std <= 0)
        or np.ptp(x) <= 0
        or not 0 < bounds[0] < start[2] < bounds[1]
        or start[1] <= 0
        or not x.min() < start[0] < x.max()
    ):
        raise ValueError(
            "Finite picks/errors, interior (x0,t0,v) guess and positive velocity bounds required"
        )
    if (
        isinstance(max_evaluations, bool)
        or not isinstance(max_evaluations, (int, np.integer))
        or not 1 <= max_evaluations <= 1000
    ):
        raise ValueError("max_evaluations must be integer 1..1000")
    center, span = x.mean(), np.ptp(x)

    def prediction(model):
        apex = center + span * model[0]
        t0, velocity = np.exp(model[1:])
        return np.sqrt(t0 * t0 + 4 * ((x - apex) / velocity) ** 2)

    initial_model = np.r_[(start[0] - center) / span, np.log(start[1:])]
    limits = (
        [((x.min() - center) / span), np.log(np.finfo(float).tiny), np.log(bounds[0])],
        [((x.max() - center) / span), np.log(times.max() * 10), np.log(bounds[1])],
    )
    fit = least_squares(
        lambda m: (prediction(m) - times) / std,
        initial_model,
        bounds=limits,
        max_nfev=max_evaluations,
    )
    apex, t0, velocity = center + span * fit.x[0], np.exp(fit.x[1]), np.exp(fit.x[2])
    covariance = np.full((3, 3), np.nan)
    if np.linalg.matrix_rank(fit.jac) == 3:
        transform = np.diag([span, t0, velocity])
        covariance = transform @ np.linalg.inv(fit.jac.T @ fit.jac) @ transform.T
    return {
        "apex_position_m": float(apex),
        "apex_time_s": float(t0),
        "velocity_m_s": float(velocity),
        "conditional_depth_m": float(t0 * velocity / 2),
        "conditional_covariance": covariance,
        "predicted_times_s": prediction(fit.x),
        "chi_squared": float(fit.fun @ fit.fun),
        "success": bool(fit.success),
        "message": fit.message,
    }


def normal_moveout(
    traces, dt_s, offsets_m, velocity_m_s, *, maximum_stretch, minimum_fold=2
):
    """Constant-RMS-velocity reflection NMO and mean stack on a zero-based axis.

    Offset is full source-receiver separation: t=sqrt(t0^2+(offset/v)^2).
    Mute unsupported/stretched samples; no amplitude/stretch compensation.
    This is an array processor, not automatic velocity analysis or migration.
    """
    a = _traces(traces, dt_s)
    offsets = as_array(offsets_m, float)
    if (
        offsets.shape != (len(a),)
        or not np.isfinite(offsets).all()
        or not np.isfinite([velocity_m_s, maximum_stretch]).all()
        or velocity_m_s <= 0
        or maximum_stretch < 0
        or isinstance(minimum_fold, bool)
        or not isinstance(minimum_fold, (int, np.integer))
        or minimum_fold < 1
    ):
        raise ValueError(
            "Explicit offsets, positive velocity, stretch limit and integer fold required"
        )
    times = np.arange(a.shape[1]) * dt_s
    corrected = np.full(a.shape, np.nan)
    for i, offset in enumerate(offsets):
        travel = np.hypot(times, offset / velocity_m_s)
        stretch = (
            np.divide(travel, times, out=np.full(times.shape, np.inf), where=times > 0)
            - 1
        )
        if offset == 0:
            stretch[0] = 0
        good = (stretch <= maximum_stretch) & (travel <= times[-1])
        corrected[i, good] = np.interp(travel[good], times, a[i])
    fold = np.isfinite(corrected).sum(axis=0)
    stack = np.divide(
        np.nansum(corrected, axis=0),
        fold,
        out=np.full(times.shape, np.nan),
        where=fold >= minimum_fold,
    )
    return {
        "traces": corrected,
        "stack": stack,
        "fold": fold,
        "times_s": times,
        "valid": np.isfinite(corrected),
        "velocity_m_s": velocity_m_s,
        "warning": "Constant RMS velocity; amplitudes affected by interpolation/stretch",
    }


def hvsr_windows(windows, dt_s, *, vertical_psd_floor, accepted=None):
    """Unsmoothed per-window H/V using RMS of north/east amplitude spectra.

    Shape (window,3,time), component order north,east,up. Hann periodogram,
    mean removed, H=sqrt((P_N+P_E)/2), V=sqrt(P_U). Caller-supplied vertical
    noise floor in input-unit^2/Hz; invalid ratios remain NaN. Geometric mean
    and log spread describe accepted windows, NOT uncertainty in Vs/depth.
    No SESAME certification, smoothing, response removal or automatic rejection.
    """
    a = as_array(windows, float)
    if a.ndim != 3 or a.shape[1] != 3 or not len(a):
        raise ValueError("Require (window,3,time) north,east,up components")
    _traces(a.reshape(-1, a.shape[-1]), dt_s)
    if not np.isfinite(vertical_psd_floor) or vertical_psd_floor <= 0:
        raise ValueError("Positive explicit vertical PSD noise floor required")
    use = np.ones(len(a), bool) if accepted is None else as_array(accepted)
    if use.shape != (len(a),) or use.dtype.kind != "b" or not use.any():
        raise ValueError("Nonempty boolean accepted-window mask required")
    frequency, psd = signal.periodogram(
        a[use], fs=1 / dt_s, window="hann", detrend="constant", axis=-1
    )
    valid = (psd[:, 2] > vertical_psd_floor) & (frequency[None, :] > 0)
    ratio = np.sqrt(
        np.divide(
            (psd[:, 0] + psd[:, 1]) / 2,
            psd[:, 2],
            out=np.full(psd[:, 2].shape, np.nan),
            where=valid,
        )
    )
    valid &= ratio > 0
    logs = np.log(np.where(valid, ratio, np.nan))
    count = valid.sum(axis=0)
    average = np.divide(
        np.nansum(logs, axis=0),
        count,
        out=np.full(len(frequency), np.nan),
        where=count > 0,
    )
    variance = np.divide(
        np.nansum((logs - average) ** 2, axis=0),
        count - 1,
        out=np.full(len(frequency), np.nan),
        where=count > 1,
    )
    return {
        "frequency_hz": frequency,
        "window_hvsr": ratio,
        "geometric_mean": np.exp(average),
        "log_std": np.sqrt(variance),
        "count": count,
        "accepted": use.copy(),
        "horizontal_definition": "RMS of N/E amplitude spectra",
        "smoothing": "none",
    }


def sta_lta_picks(
    traces,
    dt_s,
    *,
    sta_samples,
    lta_samples,
    threshold,
    lta_energy_floor,
    search_window_s,
):
    """First causal trailing energy-ratio crossing in an explicit search window.

    Integer STA<LTA; startup before a complete LTA is invalid. Output is a
    candidate threshold pick, NOT a calibrated phase classifier or uncertainty.
    Filter/detrend, verify polarity/timing and manually review before tomography.
    """
    a = _traces(traces, dt_s)
    for samples in (sta_samples, lta_samples):
        if isinstance(samples, bool) or not isinstance(samples, (int, np.integer)):
            raise ValueError("STA/LTA lengths must be explicit integers")
    window = as_array(search_window_s, float)
    if (
        not 1 <= sta_samples < lta_samples <= a.shape[1]
        or not np.isfinite([threshold, lta_energy_floor]).all()
        or threshold <= 1
        or lta_energy_floor <= 0
        or window.shape != (2,)
        or not np.isfinite(window).all()
        or not 0 <= window[0] < window[1] <= (a.shape[1] - 1) * dt_s
    ):
        raise ValueError(
            "Valid STA/LTA, threshold>1, positive energy floor and contained time window required"
        )
    energy = a * a
    cumulative = np.pad(np.cumsum(energy, axis=-1), ((0, 0), (1, 0)))
    short, long = np.zeros_like(a), np.zeros_like(a)
    short[:, sta_samples - 1 :] = (
        cumulative[:, sta_samples:] - cumulative[:, :-sta_samples]
    ) / sta_samples
    long[:, lta_samples - 1 :] = (
        cumulative[:, lta_samples:] - cumulative[:, :-lta_samples]
    ) / lta_samples
    ratio = np.divide(short, long, out=np.zeros_like(a), where=long > lta_energy_floor)
    ratio[:, : lta_samples - 1] = 0
    time = np.arange(a.shape[1]) * dt_s
    search = (time >= window[0]) & (time <= window[1])
    crossing = (ratio >= threshold) & search[None, :]
    found = crossing.any(axis=1)
    index = np.where(found, np.argmax(crossing, axis=1), -1)
    return {
        "sample_index": index,
        "time_s": np.where(found, np.maximum(index, 0) * dt_s, np.nan),
        "valid": found,
        "sta_lta": ratio,
        "sample_resolution_s": dt_s,
        "sta_window_s": sta_samples * dt_s,
        "warning": "Candidate threshold onset; review phase and latency",
    }


def phase_velocity_image(
    traces,
    dt_s,
    positions_m,
    velocities_m_s,
    *,
    frequency_range_hz,
    minimum_amplitude,
    minimum_traces=3,
    max_work=5_000_000,
):
    """Phase-shift coherence image for positive apparent velocity on a line.

    Uniform increasing receiver spacing; output |mean(exp(i*phase))|^2.
    Demeaned Hann-tapered FFT amplitudes divided by sample count. Reject weak
    spectral traces using the caller's explicit amplitude floor. Nyquist-alias
    cells are masked. This is dispersion imaging, NOT mode picking or Vs
    inversion; negative propagation/array geometry need a different contract.
    """
    a = _traces(traces, dt_s)
    x, velocity, bounds = [
        as_array(v, float) for v in (positions_m, velocities_m_s, frequency_range_hz)
    ]
    if (
        x.shape != (len(a),)
        or len(x) < 3
        or velocity.ndim != 1
        or not len(velocity)
        or bounds.shape != (2,)
        or not all(np.isfinite(v).all() for v in (x, velocity, bounds))
        or np.any(np.diff(x) <= 0)
        or not np.allclose(np.diff(x), np.diff(x)[0], rtol=1e-6, atol=1e-8)
        or np.any(velocity <= 0)
        or not 0 < bounds[0] < bounds[1] < 0.5 / dt_s
        or not np.isfinite(minimum_amplitude)
        or minimum_amplitude <= 0
        or isinstance(minimum_traces, bool)
        or not isinstance(minimum_traces, (int, np.integer))
        or not 3 <= minimum_traces <= len(x)
    ):
        raise ValueError(
            "Uniform line positions, positive velocities/frequencies/amplitude floor and minimum trace count required"
        )
    frequency = np.fft.rfftfreq(a.shape[1], dt_s)
    selected = (frequency >= bounds[0]) & (frequency <= bounds[1])
    frequency = frequency[selected]
    if not len(frequency) or len(frequency) * len(velocity) * len(x) > max_work:
        raise ValueError("No selected FFT bins or dispersion work budget exceeded")
    transformed = (
        np.fft.rfft(
            (a - a.mean(axis=1)[:, None]) * signal.windows.hann(a.shape[1], sym=False),
            axis=-1,
        )[:, selected]
        / a.shape[1]
    )
    image = np.full((len(frequency), len(velocity)), np.nan)
    alias = frequency[:, None] / velocity[None, :] > 0.5 / np.diff(x)[0]
    counts = np.zeros(len(frequency), int)
    for i, f in enumerate(frequency):
        amplitude = abs(transformed[:, i])
        use = amplitude > minimum_amplitude
        counts[i] = use.sum()
        if counts[i] >= minimum_traces:
            phase = transformed[use, i] / amplitude[use]
            correction = np.exp(
                2j * np.pi * f * (x[use] - x[0])[None, :] / velocity[:, None]
            )
            image[i] = abs(correction @ phase / counts[i]) ** 2
    image[alias] = np.nan
    return {
        "frequency_hz": frequency,
        "velocity_m_s": velocity.copy(),
        "coherence": image,
        "alias_mask": alias,
        "contributing_traces": counts,
        "normalization": "phase-only coherence, not quantitative wave amplitude",
        "warning": "Apparent positive phase velocity; modes and Vs inversion unresolved",
    }

"""Euler, Werner and profile SPI source-depth estimators, independent of QGIS.

Projected coordinates and all heights/depths must use one length unit. Elevations
and vertical derivatives are positive upwards. See docs/source_depth.md for the
geometry assumptions, quality statistics and primary references.
"""
from collections import Counter
from functools import lru_cache
import hashlib
from pathlib import Path
import numpy as np


def _integer(value, name, minimum=1):
    if isinstance(value, (bool, np.bool_)) or not np.isfinite(value) or int(value) != value or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}.")
    return int(value)


def _positive(value, name, zero=False):
    value = float(value)
    if not np.isfinite(value) or value < 0 or (value == 0 and not zero):
        raise ValueError(f"{name} must be finite and {'nonnegative' if zero else 'positive'}.")
    return value


def _depth_bounds(bounds):
    low, high = map(float, bounds)
    if not np.isfinite(low) or low < 0 or np.isnan(high) or high <= low:
        raise ValueError("Depth bounds require 0 <= minimum < maximum.")
    return low, high


def _fit(design, rhs, max_condition):
    """Column-scaled SVD least squares; do not square the condition number."""
    scale = np.linalg.norm(design, axis=0)
    if np.any(scale == 0) or len(rhs) <= design.shape[1]:
        return None, "rank"
    matrix = design / scale
    u, s, vt = np.linalg.svd(matrix, full_matrices=False)
    if s[-1] <= s[0] * np.finfo(float).eps * max(matrix.shape):
        return None, "rank"
    condition = float(s[0] / s[-1])
    if condition > max_condition:
        return None, "condition"
    parameters = (vt.T @ ((u.T @ rhs) / s)) / scale
    residual = design @ parameters - rhs
    variance = float(residual @ residual / (len(rhs) - design.shape[1]))
    covariance = ((vt.T / s**2) @ vt) / np.outer(scale, scale) * variance
    return (parameters, covariance, condition, residual), None


@lru_cache(maxsize=1)
def _source_digest():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _result(method, solutions, rejected, **recipe):
    if method.startswith("spi"):
        from scipy import __version__ as scipy_version
        recipe["scipy"] = scipy_version
    return {"solutions": solutions, "rejected": dict(rejected),
            "recipe": {"method": method, "numpy": np.__version__,
                       "core_source_sha256": _source_digest(),
                       "vertical_convention": "positive_up", **recipe}}


def _euler_window(xyz, field, gradients, *, structural_index,
                 depth_bounds=(0., np.inf), max_condition=1e6,
                 max_relative_depth_error=.2, max_relative_residual=.2,
                 min_gradient=0.):
    """Solve one 3-D Euler window; return solution and a rejection reason.

    SI=0 solves for the contact offset A, not an unidentifiable background B.
    Depth is measured below mean receiver elevation in this window. Uncertainty
    is an equation-fit diagnostic and omits derivative errors/correlations.
    """
    xyz, field, gradients = (np.asarray(a, dtype=float) for a in (xyz, field, gradients))
    if field.ndim != 1 or xyz.ndim != 2 or xyz.shape[0] != len(field) or xyz.shape[1] not in (2, 3) or gradients.shape != xyz.shape:
        raise ValueError("Euler requires aligned coordinate, field and gradient arrays.")
    dimension = xyz.shape[1]
    index = _positive(structural_index, "Structural index", zero=True)
    condition_limit = _positive(max_condition, "Maximum condition")
    error_limit = _positive(max_relative_depth_error, "Maximum relative depth error", zero=True)
    residual_limit = _positive(max_relative_residual, "Maximum relative residual", zero=True)
    min_gradient = _positive(min_gradient, "Minimum gradient", zero=True)
    low, high = _depth_bounds(depth_bounds)
    if len(field) <= dimension+1:
        return None, "support"
    if not all(np.isfinite(a).all() for a in (xyz, field, gradients)):
        return None, "nodata"
    if np.max(np.linalg.norm(gradients, axis=1)) <= min_gradient:
        return None, "gradient"
    origin, baseline = xyz.mean(axis=0), float(field.mean())
    rhs = np.sum((xyz-origin) * gradients, axis=1) + index*(field-baseline)
    constant = index if index else 1.
    design = np.column_stack([gradients, np.full(len(field), constant)])
    fitted, reason = _fit(design, rhs, condition_limit)
    if fitted is None:
        return None, reason
    parameters, covariance, condition, residual = fitted
    source = origin + parameters[:dimension]
    depth = float(origin[-1] - source[-1])
    if not low < depth <= high:
        return None, "depth"
    depth_std = float(np.sqrt(max(0., covariance[dimension-1, dimension-1])))
    relative_error = depth_std / depth
    relative_residual = float(np.linalg.norm(residual) / max(np.linalg.norm(rhs-rhs.mean()), np.finfo(float).tiny))
    if relative_error > error_limit:
        return None, "depth_error"
    if relative_residual > residual_limit:
        return None, "residual"
    position = {"x": float(source[0]), "y": float(source[1])} if dimension == 3 else {"distance": float(source[0])}
    return {**position, "z": float(source[-1]),
            "depth": depth, "depth_std": depth_std, "relative_depth_error": relative_error,
            "condition": condition, "relative_residual": relative_residual,
            "samples": len(field), "structural_index": index,
            "background": float(parameters[-1]+baseline) if index else None,
            "contact_offset": float(parameters[-1]) if index == 0 else None}, None


def euler_window(xyz, field, gradients, **quality):
    """Solve one 3-D window; SI=0 estimates contact offset, not background."""
    xyz = np.asarray(xyz, float)
    if xyz.ndim != 2 or xyz.shape[1] != 3:
        raise ValueError("3-D Euler requires XYZ coordinates.")
    return _euler_window(xyz, field, gradients, **quality)


def euler_grid(x, y, elevation, field, gradient_x, gradient_y, gradient_z, *,
               structural_index, window_size=9, stride=1, min_valid_fraction=1.,
               max_horizontal_distance=None, max_windows=1000000, max_solutions=100000,
               canceled=None, **quality):
    """Moving-window Euler on supplied grids; missing samples are never filled."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    structural_index = _positive(structural_index, "Structural index", zero=True)
    arrays = [np.asarray(a, float) for a in (field, gradient_x, gradient_y, gradient_z)]
    if x.ndim != 1 or y.ndim != 1:
        raise ValueError("Grid coordinates must be one-dimensional.")
    shape = (len(y), len(x))
    if x.ndim != 1 or y.ndim != 1 or any(a.shape != shape for a in arrays):
        raise ValueError("Grid coordinates must be 1-D with matching (y,x) arrays.")
    if not np.isfinite(x).all() or not np.isfinite(y).all() or np.any(np.diff(x) <= 0) or np.any(np.diff(y) <= 0):
        raise ValueError("Grid coordinates must be finite and strictly increasing.")
    elevation = np.broadcast_to(np.asarray(elevation, float), shape)
    window = _integer(window_size, "Window size", 3)
    step = _integer(stride, "Stride")
    if window > min(shape) or not 0 < min_valid_fraction <= 1:
        raise ValueError("Window must fit grid and valid fraction must be in (0,1].")
    budget = _integer(max_windows, "Maximum windows")
    solution_limit = _integer(max_solutions, "Maximum solutions")
    if len(range(0, shape[0]-window+1, step))*len(range(0, shape[1]-window+1, step)) > budget:
        raise ValueError("Window budget exceeded; increase stride or process smaller regions.")
    if max_horizontal_distance is not None:
        max_horizontal_distance = _positive(max_horizontal_distance, "Maximum horizontal distance")
    solutions, rejected = [], Counter()
    for row in range(0, shape[0]-window+1, step):
        if canceled is not None and canceled():
            raise RuntimeError("Source-depth estimation canceled.")
        for col in range(0, shape[1]-window+1, step):
            sl = np.s_[row:row+window, col:col+window]
            xx, yy = np.meshgrid(x[col:col+window], y[row:row+window])
            xyz = np.column_stack([xx.ravel(), yy.ravel(), elevation[sl].ravel()])
            values = [a[sl].ravel() for a in arrays]
            valid = np.isfinite(xyz).all(axis=1) & np.isfinite(values).all(axis=0)
            if valid.sum() < max(5, int(np.ceil(window**2*min_valid_fraction))):
                rejected["support"] += 1
                continue
            solution, reason = euler_window(xyz[valid], values[0][valid],
                np.column_stack(values[1:])[valid], structural_index=structural_index, **quality)
            if solution is not None and max_horizontal_distance is not None:
                center = np.array([xx.mean(), yy.mean()])
                if np.linalg.norm(np.array([solution["x"], solution["y"]])-center) > max_horizontal_distance:
                    solution, reason = None, "horizontal_distance"
            if solution is None:
                rejected[reason] += 1
            else:
                solution.update(window_row=row, window_column=col)
                if len(solutions) >= solution_limit:
                    raise ValueError("Solution budget exceeded; increase stride or tighten quality controls.")
                solutions.append(solution)
    return _result("euler_3d", solutions, rejected, structural_index=float(structural_index),
                   window_size=window, stride=step, min_valid_fraction=float(min_valid_fraction),
                   max_horizontal_distance=max_horizontal_distance,
                   max_windows=budget, max_solutions=solution_limit,
                   quality=_serializable_quality(quality))


def _profile(distance, values, profile_id, max_gap):
    distance, values = np.asarray(distance, float), np.asarray(values, float)
    if distance.ndim != 1 or values.shape != distance.shape or len(distance) < 5:
        raise ValueError("Profile requires at least five aligned positions and values.")
    if not np.isfinite(distance).all():
        raise ValueError("Profile positions must be finite.")
    groups = np.zeros(len(distance), int) if profile_id is None else np.asarray(profile_id)
    if groups.shape != distance.shape or any(v is None or v != v for v in groups):
        raise ValueError("Profile IDs must be aligned and nonmissing.")
    same = groups[1:] == groups[:-1]
    gaps = np.diff(distance)
    if not np.isfinite(gaps).all() or np.any(gaps[same] <= 0) or not same.any():
        raise ValueError("Distance must strictly increase within each profile.")
    limit = 3*float(np.median(gaps[same])) if max_gap is None else _positive(max_gap, "Maximum gap")
    breaks = ~same | (gaps > limit)
    return distance, values, breaks, limit


def euler_profile(distance, elevation, field, gradient_x, gradient_z, *, structural_index,
                   window_size=15, stride=1, profile_id=None, max_gap=None,
                   max_windows=1000000, max_solutions=100000, canceled=None, **quality):
    """Constrained 2-D Euler for profile sources; no along-strike position is solved."""
    distance, field, breaks, gap = _profile(distance, field, profile_id, max_gap)
    gx, gz = np.asarray(gradient_x, float), np.asarray(gradient_z, float)
    elevation = np.broadcast_to(np.asarray(elevation, float), field.shape)
    if gx.shape != field.shape or gz.shape != field.shape:
        raise ValueError("Profile gradients must match observations.")
    index = _positive(structural_index, "Structural index", zero=True)
    window, step = _integer(window_size, "Window size", 4), _integer(stride, "Stride")
    budget, limit = _integer(max_windows, "Maximum windows"), _integer(max_solutions, "Maximum solutions")
    if window > len(field) or len(range(0, len(field)-window+1, step)) > budget:
        raise ValueError("Window must fit profile and remain within the window budget.")
    solutions, rejected = [], Counter()
    for start in range(0, len(field)-window+1, step):
        if canceled is not None and canceled():
            raise RuntimeError("Source-depth estimation canceled.")
        if breaks[start:start+window-1].any():
            rejected["profile_gap"] += 1
            continue
        sl = slice(start, start+window)
        solution, reason = _euler_window(np.column_stack([distance[sl], elevation[sl]]),
            field[sl], np.column_stack([gx[sl], gz[sl]]), structural_index=index, **quality)
        if solution is None:
            rejected[reason] += 1
        else:
            if len(solutions) >= limit:
                raise ValueError("Solution budget exceeded; increase stride or tighten controls.")
            solution["window_start"] = start
            solutions.append(solution)
    return _result("euler_2d_profile", solutions, rejected, structural_index=index,
                   window_size=window, stride=step, max_gap=gap,
                   max_windows=budget, max_solutions=limit, quality=_serializable_quality(quality))


def werner_profile(distance, field, *, window_size=15, stride=1,
                    background_degree=0, observation_elevation=0., profile_id=None,
                    max_gap=None, depth_bounds=(0., np.inf), max_condition=1e6,
                    max_relative_residual=.1, max_horizontal_distance=None,
                    max_windows=1000000, max_solutions=100000, canceled=None):
    """Thin-sheet Werner solutions on level profiles with polynomial interference.

    background_degree=-1 fits no interference; 0..2 fits constant..quadratic.
    Windows never cross profile boundaries, large gaps or missing observations.
    """
    distance, field, breaks, gap = _profile(distance, field, profile_id, max_gap)
    degree = int(background_degree)
    if degree != background_degree or degree not in (-1, 0, 1, 2):
        raise ValueError("Background degree must be -1, 0, 1 or 2.")
    window = _integer(window_size, "Window size", max(5, degree+6))
    step = _integer(stride, "Stride")
    if window > len(distance):
        raise ValueError("Window exceeds profile length.")
    budget = _integer(max_windows, "Maximum windows")
    solution_limit = _integer(max_solutions, "Maximum solutions")
    if len(range(0, len(distance)-window+1, step)) > budget:
        raise ValueError("Window budget exceeded; increase stride or split the profile.")
    elevation = float(observation_elevation)
    if not np.isfinite(elevation):
        raise ValueError("Observation elevation must be a finite level height.")
    low, high = _depth_bounds(depth_bounds)
    condition_limit = _positive(max_condition, "Maximum condition")
    residual_limit = _positive(max_relative_residual, "Maximum relative residual", zero=True)
    if max_horizontal_distance is not None:
        max_horizontal_distance = _positive(max_horizontal_distance, "Maximum horizontal distance")
    solutions, rejected = [], Counter()
    for start in range(0, len(distance)-window+1, step):
        if canceled is not None and canceled():
            raise RuntimeError("Source-depth estimation canceled.")
        if breaks[start:start+window-1].any():
            rejected["profile_gap"] += 1
            continue
        xx, data = distance[start:start+window], field[start:start+window]
        if not np.isfinite(data).all():
            rejected["nodata"] += 1
            continue
        center, scale = float(xx.mean()), float(np.ptp(xx)/2)
        t = (xx-center)/scale
        baseline = float(data.mean()) if degree >= 0 else 0.
        amplitude = float(np.std(data))
        if amplitude <= np.finfo(float).eps*max(1., float(np.max(np.abs(data)))):
            rejected["signal"] += 1
            continue
        f = (data-baseline)/amplitude
        powers = range(2 if degree == -1 else degree+3)
        design = np.column_stack([f, t*f, *[t**p for p in powers]])
        fitted, reason = _fit(design, f*t**2, condition_limit)
        if fitted is None:
            rejected[reason] += 1
            continue
        pars, _, condition, _ = fitted
        b0, b1 = pars[:2]
        source_t = b1/2
        squared_depth = -b0-source_t**2
        if squared_depth <= 0:
            rejected["nonphysical"] += 1
            continue
        depth = float(scale*np.sqrt(squared_depth))
        position = float(center+scale*source_t)
        if not low < depth <= high:
            rejected["depth"] += 1
            continue
        if max_horizontal_distance is not None and abs(position-center) > max_horizontal_distance:
            rejected["horizontal_distance"] += 1
            continue
        numerator = np.polynomial.polynomial.polyval(t, pars[2:])
        predicted = baseline + amplitude*numerator/(t*t-b1*t-b0)
        rmse = float(np.sqrt(np.mean((predicted-data)**2)))
        relative = rmse/amplitude
        if relative > residual_limit:
            rejected["residual"] += 1
            continue
        if len(solutions) >= solution_limit:
            raise ValueError("Solution budget exceeded; increase stride or tighten quality controls.")
        solutions.append({"distance": position, "z": elevation-depth, "depth": depth,
                          "window_start": start, "samples": window, "condition": condition,
                          "rmse": rmse, "relative_residual": relative})
    return _result("werner_thin_sheet", solutions, rejected, window_size=window, stride=step,
                   background_degree=degree, observation_elevation=elevation, max_gap=gap,
                   depth_bounds=[low, None if np.isinf(high) else high],
                   max_condition=condition_limit, max_relative_residual=residual_limit,
                   max_windows=budget, max_solutions=solution_limit,
                   max_horizontal_distance=max_horizontal_distance)


def profile_fft_derivatives(field, spacing, *, padding_cells=None):
    """Uniform, complete, level 2-D-source profile derivatives; no gap filling.

    Reflect padding is tapered outside the original footprint. Boundary effects
    remain: depth estimation must exclude the edges and check padding sensitivity.
    """
    field = np.asarray(field, float)
    spacing = _positive(spacing, "Spacing")
    if field.ndim != 1 or len(field) < 8 or not np.isfinite(field).all():
        raise ValueError("FFT derivatives require >=8 finite profile samples; split at gaps first.")
    pad = max(2, len(field)//2) if padding_cells is None else _integer(padding_cells, "Padding", 0)
    values = field-field.mean()
    if pad:
        values = np.pad(values, pad, mode="reflect")
        taper = np.sin(np.linspace(0., np.pi/2, pad+1))[:-1]**2
        values[:pad] *= taper
        values[-pad:] *= taper[::-1]
    wave = 2*np.pi*np.fft.rfftfreq(len(values), spacing)
    spectrum = np.fft.rfft(values)
    factors = {"dx": 1j*wave, "dz": -np.abs(wave), "dxx": -wave**2,
               "dxz": -1j*wave*np.abs(wave)}
    return {name: np.fft.irfft(spectrum*factor, n=len(values))[pad:pad+len(field)]
            for name, factor in factors.items()}


def spi_profile(distance, gradient_x, gradient_z, *, second_x=None, cross_xz=None,
                 source_model="contact", observation_elevation=0., profile_id=None,
                 max_gap=None, min_amplitude=0., min_wavenumber=0.,
                 depth_bounds=(0., np.inf), peak_distance=1, prominence=0.,
                 edge_exclusion=2, max_solutions=100000, canceled=None):
    """Model-dependent SPI using local-wavenumber peaks on 2-D-source profiles.

    K = abs((Tx*Txz - Tz*Txx)/(Tx**2+Tz**2)); depth=(index+1)/K at peaks.
    Only peak locations are source-depth estimates. Indices here are 0 for a
    contact, 1 for a thin sheet and 2 for a horizontal cylinder.
    """
    from scipy.signal import find_peaks
    distance, gx, breaks, gap = _profile(distance, gradient_x, profile_id, max_gap)
    gz = np.asarray(gradient_z, float)
    if gz.shape != gx.shape:
        raise ValueError("First derivatives must match profile length.")
    factors = {"contact": 1., "thin_sheet": 2., "horizontal_cylinder": 3.}
    if source_model not in factors:
        raise ValueError("Source model must be contact, thin_sheet or horizontal_cylinder.")
    if (second_x is None) != (cross_xz is None):
        raise ValueError("Supply both second derivatives or neither.")
    if second_x is not None:
        gxx, gxz = np.asarray(second_x, float), np.asarray(cross_xz, float)
        if gxx.shape != gx.shape or gxz.shape != gx.shape:
            raise ValueError("Second derivatives must match profile length.")
    else:
        gxx, gxz = np.full_like(gx, np.nan), np.full_like(gx, np.nan)
    minimum = _positive(min_amplitude, "Minimum amplitude", zero=True)
    minimum_k = _positive(min_wavenumber, "Minimum wavenumber", zero=True)
    prominence = _positive(prominence, "Peak prominence", zero=True)
    separation = _integer(peak_distance, "Peak distance")
    edge = _integer(edge_exclusion, "Edge exclusion", 1)
    solution_limit = _integer(max_solutions, "Maximum solutions")
    low, high = _depth_bounds(depth_bounds)
    elevation = float(observation_elevation)
    if not np.isfinite(elevation):
        raise ValueError("Observation elevation must be finite and level.")
    finite = np.isfinite(gx) & np.isfinite(gz)
    # Split additionally at missing first derivatives. Never differentiate across gaps.
    boundaries = np.r_[0, np.flatnonzero(breaks | ~finite[:-1] | ~finite[1:])+1, len(gx)]
    wavenumber = np.full_like(gx, np.nan)
    solutions, rejected = [], Counter()
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        if canceled is not None and canceled():
            raise RuntimeError("Source-depth estimation canceled.")
        if right-left < max(5, 2*edge+3) or not finite[left:right].all():
            rejected["support_segment"] += 1
            continue
        sl = slice(left, right)
        if second_x is None:
            gxx[sl] = np.gradient(gx[sl], distance[sl], edge_order=2)
            gxz[sl] = np.gradient(gz[sl], distance[sl], edge_order=2)
        amplitude_squared = gx[sl]**2+gz[sl]**2
        good = (amplitude_squared > max(minimum**2, np.finfo(float).tiny)) & np.isfinite(gxx[sl]) & np.isfinite(gxz[sl])
        rejected["low_amplitude_samples"] += int(np.count_nonzero(amplitude_squared <= max(minimum**2, np.finfo(float).tiny)))
        rejected["invalid_second_derivative_samples"] += int(np.count_nonzero(~np.isfinite(gxx[sl]) | ~np.isfinite(gxz[sl])))
        k = np.full(right-left, np.nan)
        k[good] = np.abs((gx[sl][good]*gxz[sl][good]-gz[sl][good]*gxx[sl][good])/amplitude_squared[good])
        k[:edge], k[-edge:] = np.nan, np.nan
        wavenumber[sl] = k
        peaks, _ = find_peaks(np.where(np.isfinite(k), k, -np.inf),
                             height=minimum_k, distance=separation, prominence=prominence)
        for peak in peaks:
            # Do not create a peak immediately next to a missing derivative.
            if not np.isfinite(k[peak-1:peak+2]).all() or k[peak] <= 0:
                rejected["peak_support"] += 1
                continue
            depth = float(factors[source_model]/k[peak])
            if not low < depth <= high:
                rejected["depth"] += 1
                continue
            index = int(left+peak)
            if len(solutions) >= solution_limit:
                raise ValueError("Solution budget exceeded; increase peak distance or tighten quality controls.")
            solutions.append({"distance": float(distance[index]), "z": elevation-depth,
                              "depth": depth, "sample": index, "wavenumber": float(k[peak]),
                              "source_model": source_model})
    result = _result("spi_2d_profile", solutions, rejected, source_model=source_model,
        observation_elevation=elevation, max_gap=gap, min_amplitude=minimum,
        min_wavenumber=minimum_k, peak_distance=separation, prominence=prominence,
        edge_exclusion=edge, depth_bounds=[low, None if np.isinf(high) else high],
        max_solutions=solution_limit,
        second_derivatives="provided" if second_x is not None else "finite_difference")
    result["wavenumber"] = wavenumber
    return result


def _serializable_quality(quality):
    quality = {"depth_bounds": (0., np.inf), "max_condition": 1e6,
               "max_relative_depth_error": .2, "max_relative_residual": .2,
               "min_gradient": 0., **quality}
    return {key: [None if np.isinf(v) else float(v) for v in value]
            if key == "depth_bounds" else float(value) for key, value in quality.items()}


def grid_fft_derivatives(field, spacing, *, padding_cells=(16, 16)):
    """First/second derivatives on a complete, uniformly spaced level grid.

    spacing is (northing, easting). Positive-up vertical derivative is -|k|.
    NoData is rejected rather than interpolated into artificial source support.
    """
    from .spectral import prepare_fft_grid, finish_fft_grid, frequency_grid, apply_spectrum
    dy, dx = (_positive(v, "Grid spacing") for v in spacing)
    prepared, state = prepare_fft_grid(field, detrend_order=0,
        padding_cells=tuple(padding_cells), nodata_policy="reject")
    kx, ky, radial = frequency_grid(prepared.shape, dy, dx)
    spectrum = np.fft.fft2(prepared)
    factors = {"dx": 1j*kx, "dy": 1j*ky, "dz": -radial,
               "dxx": -kx**2, "dyy": -ky**2,
               "dxz": -1j*kx*radial, "dyz": -1j*ky*radial}
    return {name: finish_fft_grid(apply_spectrum(spectrum, factor), state, restore_trend=False)
            for name, factor in factors.items()}


def interpret_grid(method, x, y, elevation, field, *, derivative_grids=None,
                    direction="x", padding_cells=(16, 16), canceled=None, **options):
    """Grid facade: Euler 3-D or explicit x/y profile Werner and 2-D SPI.

    SPI here processes parallel profiles assuming locally 2-D sources normal to
    the chosen profile direction. It is not automatic strike tracking or a full
    3-D source-depth solution. Only use FFT derivatives on level observations.
    """
    x, y, field = np.asarray(x, float), np.asarray(y, float), np.asarray(field, float)
    if x.ndim != 1 or y.ndim != 1 or min(len(x), len(y)) < 2 or field.shape != (len(y), len(x)):
        raise ValueError("Grid requires 1-D x/y coordinates and a matching (y,x) field.")
    if not all(np.isfinite(a).all() and np.all(np.diff(a) > 0) for a in (x, y)):
        raise ValueError("Grid axes must be finite and strictly increasing.")
    if method not in ("euler", "werner", "spi") or direction not in ("x", "y"):
        raise ValueError("Method must be euler, werner or spi; direction must be x or y.")
    heights = np.broadcast_to(np.asarray(elevation, float), field.shape)
    level = np.isfinite(heights).all() and np.allclose(heights, heights.flat[0], rtol=0., atol=1e-8)
    derivatives = None
    if method != "werner":
        if derivative_grids is None:
            if not level:
                raise ValueError("FFT derivatives require a level observation grid; supply measured/model derivatives for nonlevel Euler.")
            dx, dy = np.diff(x), np.diff(y)
            if not np.allclose(dx, dx[0], rtol=1e-8) or not np.allclose(dy, dy[0], rtol=1e-8):
                raise ValueError("FFT derivatives require uniformly spaced grid axes.")
            derivatives = grid_fft_derivatives(field, (dy[0], dx[0]), padding_cells=padding_cells)
        else:
            derivatives = {name: np.asarray(value, float) for name, value in derivative_grids.items()}
            if any(value.shape != field.shape for value in derivatives.values()):
                raise ValueError("Derivative grids must match the field shape.")
        required = ("dx", "dy", "dz") if method == "euler" else (("dx", "dz", "dxx", "dxz") if direction == "x" else ("dy", "dz", "dyy", "dyz"))
        if not set(required) <= derivatives.keys():
            raise ValueError("Missing required derivative grids: " + ", ".join(required))
    if method == "euler":
        result = euler_grid(x, y, heights, field, derivatives["dx"], derivatives["dy"], derivatives["dz"],
                            canceled=canceled, **options)
    else:
        if not level:
            raise ValueError("Werner and profile SPI require level observations.")
        solutions, rejected = [], Counter()
        kgrid = np.full_like(field, np.nan)
        nprofiles = len(y) if direction == "x" else len(x)
        coordinate = x if direction == "x" else y
        limit = _integer(options.get("max_solutions", 100000), "Maximum solutions")
        if method == "werner":
            window = _integer(options.get("window_size", 15), "Window size", 5)
            stride = _integer(options.get("stride", 1), "Stride")
            if nprofiles*len(range(0, len(coordinate)-window+1, stride)) > options.get("max_windows", 1000000):
                raise ValueError("Grid window budget exceeded; increase stride or process smaller regions.")
        for index in range(nprofiles):
            if canceled is not None and canceled():
                raise RuntimeError("Source-depth estimation canceled.")
            sl = np.s_[index, :] if direction == "x" else np.s_[:, index]
            if method == "werner":
                profile = werner_profile(coordinate, field[sl], observation_elevation=float(heights.flat[0]), canceled=canceled, **options)
            else:
                first, second, cross = ("dx", "dxx", "dxz") if direction == "x" else ("dy", "dyy", "dyz")
                profile = spi_profile(coordinate,
                    np.where(np.isfinite(field[sl]), derivatives[first][sl], np.nan),
                    np.where(np.isfinite(field[sl]), derivatives["dz"][sl], np.nan),
                    second_x=derivatives[second][sl], cross_xz=derivatives[cross][sl],
                    observation_elevation=float(heights.flat[0]), canceled=canceled, **options)
                kgrid[sl] = profile["wavenumber"]
            rejected.update(profile["rejected"])
            for record in profile["solutions"]:
                record.update(x=record["distance"] if direction == "x" else float(x[index]),
                              y=float(y[index]) if direction == "x" else record["distance"], profile=index)
                if len(solutions) >= limit:
                    raise ValueError("Grid solution budget exceeded; process smaller regions or tighten controls.")
                solutions.append(record)
        result = _result(method+"_parallel_profiles", solutions, rejected,
                         direction=direction, profile_recipe=profile["recipe"])
        if method == "spi":
            result["wavenumber"] = kgrid
    result["recipe"].update(derivatives="not_required" if method == "werner" else "provided" if derivative_grids is not None else "fft_level_grid",
                           padding_cells=list(padding_cells) if derivative_grids is None and method != "werner" else None,
                           shape=list(field.shape))
    return result


def write_depth_catalog(output_directory, result, *, crs=None):
    """Write a new CSV/JSON catalog; no original data or existing output replaced."""
    import csv
    import json
    records = result["solutions"]
    metadata = {key: value for key, value in result.items() if key != "wavenumber"}
    metadata["crs"] = crs
    encoded = json.dumps(metadata, indent=2, allow_nan=False)
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=False)
    columns = sorted({key for row in records for key in row}) or ["depth"]
    with (output/"solutions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
    (output/"catalog.json").write_text(encoded, encoding="utf-8")
    if "wavenumber" in result:
        np.save(output/"wavenumber.npy", result["wavenumber"])
    return str(output)

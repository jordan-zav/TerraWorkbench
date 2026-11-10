"""Independent grid texture and basic monogenic phase attributes.

These are mathematical feature maps, not geological faults or a CET clone.
Grid axes are increasing north by row and east by column, in projected metres.
"""

import numpy as np
from scipy import ndimage

from ._array_contract import as_array
from ._calibration import integer_budget
from .spectral import frequency_grid


def _cancel(canceled):
    if canceled is not None and canceled():
        raise RuntimeError("Structural attributes canceled")


def monogenic_phase_attributes(
    values,
    spacing,
    wavelengths_m,
    *,
    sigma_on_f,
    noise_threshold,
    polarity="both",
    padding_cells=(0, 0),
    edge_exclusion_cells=0,
    max_cells=1_000_000,
    canceled=None,
):
    """Log-Gabor/Riesz phase symmetry and unweighted phase alignment.

    All inputs must be finite; NoData are not filled. Wavelengths and bandwidth
    are explicit. noise_threshold has the input field units, is subtracted
    from accumulated energies, and is NOT an automatic Rayleigh noise model.
    Basic phase alignment is local energy / summed scale amplitudes, without
    frequency-spread weighting or Kovesi's phase-deviation penalty. This is not
    numerical parity with phasecongmono or CET. Even-grid Nyquist axes and
    frequencies above the minimum directional Nyquist are excluded.
    Padding is reflected only when explicitly requested. Edge exclusion is
    recorded, not an inferred scientifically valid boundary. Normal azimuth
    is axial, clockwise from grid north, and NaN where odd energy is unresolved.
    """
    integer_budget(max_cells, "Maximum cells")
    integer_budget(edge_exclusion_cells, "Edge exclusion", minimum=0)
    data, spacing, wavelengths = (
        as_array(v, float) for v in (values, spacing, wavelengths_m)
    )
    if (
        data.ndim != 2
        or min(data.shape) < 3
        or data.size > max_cells
        or not np.isfinite(data).all()
    ):
        raise ValueError(
            "A complete finite 2-D grid within the cell budget is required"
        )
    if spacing.shape != (2,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("Positive (northing,easting) spacing in metres is required")
    if (
        wavelengths.ndim != 1
        or not 1 <= wavelengths.size <= 12
        or not np.isfinite(wavelengths).all()
        or np.any(wavelengths <= 2 * max(spacing))
    ):
        raise ValueError(
            "Provide one to twelve wavelengths strictly above twice the largest grid spacing"
        )
    bandwidth, threshold = float(sigma_on_f), float(noise_threshold)
    if (
        not np.isfinite([bandwidth, threshold]).all()
        or not 0 < bandwidth < 1
        or threshold < 0
        or polarity not in ("both", "positive", "negative")
    ):
        raise ValueError(
            "Require 0 < sigma_on_f < 1, nonnegative noise threshold and supported polarity"
        )
    padding = np.asarray(padding_cells)
    if (
        padding.shape != (2,)
        or padding.dtype.kind not in "iu"
        or np.any(padding < 0)
        or np.any(padding > 256)
    ):
        raise ValueError("Padding must be two integers from 0 to 256")
    if 2 * edge_exclusion_cells >= min(data.shape):
        raise ValueError("Edge exclusion leaves no interior")
    padded_shape = np.array(data.shape) + 2 * padding
    if int(np.prod(padded_shape)) > max_cells:
        raise ValueError("Padded phase workspace exceeds the cell budget")
    _cancel(canceled)
    scale = float(np.max(abs(data))) or 1.0
    work = np.pad(
        data / scale, tuple((int(p), int(p)) for p in padding), mode="reflect"
    )
    work = work - work.mean()  # numerically exact zero response for constants
    ke, kn, radial = frequency_grid(work.shape, *spacing)
    usable = (radial > 0) & (radial < np.pi / max(spacing))
    if work.shape[0] % 2 == 0:
        usable[work.shape[0] // 2, :] = False
    if work.shape[1] % 2 == 0:
        usable[:, work.shape[1] // 2] = False
    riesz_e = np.divide(
        -1j * ke, radial, out=np.zeros(work.shape, complex), where=radial > 0
    )
    riesz_n = np.divide(
        -1j * kn, radial, out=np.zeros(work.shape, complex), where=radial > 0
    )
    spectrum = np.fft.fft2(work)
    amplitude = np.zeros(work.shape)
    symmetry = np.zeros(work.shape)
    sum_even, sum_e, sum_n = (np.zeros(work.shape) for _ in range(3))
    for wavelength in wavelengths:
        _cancel(canceled)
        response = np.zeros(work.shape)
        response[usable] = np.exp(
            -(np.log(radial[usable] / (2 * np.pi / wavelength)) ** 2)
            / (2 * np.log(bandwidth) ** 2)
        )
        filtered = spectrum * response
        even = np.fft.ifft2(filtered).real
        odd_e = np.fft.ifft2(filtered * riesz_e).real
        odd_n = np.fft.ifft2(filtered * riesz_n).real
        odd = np.hypot(odd_e, odd_n)
        amplitude += np.sqrt(even * even + odd * odd)
        symmetry += (
            abs(even)
            if polarity == "both"
            else even
            if polarity == "positive"
            else -even
        ) - odd
        sum_even += even
        sum_e += odd_e
        sum_n += odd_n
    denominator = np.maximum(amplitude, np.finfo(float).eps)
    symmetry_energy = np.maximum(symmetry - threshold / scale, 0.0)
    alignment_energy = np.maximum(
        np.sqrt(sum_even**2 + sum_e**2 + sum_n**2) - threshold / scale, 0.0
    )
    scores = dict(
        phase_symmetry=np.clip(symmetry_energy / denominator, 0, 1),
        phase_alignment=np.clip(alignment_energy / denominator, 0, 1),
        amplitude=amplitude * scale,
        symmetry_energy=symmetry_energy * scale,
    )
    odd_energy = np.hypot(sum_e, sum_n)
    normal = np.mod(np.rad2deg(np.arctan2(sum_e, sum_n)), 180.0)
    normal[
        odd_energy
        <= max(
            threshold / scale,
            64 * np.finfo(float).eps * max(1.0, float(amplitude.max())),
        )
    ] = np.nan
    scores["normal_azimuth_degrees_axial"] = normal
    crop = tuple(slice(int(p), int(p) + size) for p, size in zip(padding, data.shape))
    valid = np.ones(data.shape, dtype=bool)
    edge = edge_exclusion_cells
    if edge:
        valid[:edge, :] = valid[-edge:, :] = valid[:, :edge] = valid[:, -edge:] = False
    for name in scores:
        scores[name] = scores[name][crop].copy()
        if (
            name != "normal_azimuth_degrees_axial"
            and not np.isfinite(scores[name]).all()
        ):
            raise ValueError("Phase attribute arithmetic exceeds finite range")
        scores[name][~valid] = np.nan
    _cancel(canceled)
    scores["valid_mask"] = valid
    scores["recipe"] = dict(
        wavelengths_m=wavelengths.tolist(),
        sigma_on_f=bandwidth,
        noise_threshold=threshold,
        polarity=polarity,
        spacing_m=spacing.tolist(),
        padding_cells=padding.tolist(),
        edge_exclusion_cells=edge,
        orientation="Axial normal, clockwise from grid north; undefined values are NaN",
        formulation="Independent basic log-Gabor/Riesz symmetry and unweighted phase alignment",
        noise_model="Explicit threshold in input units; no automatic noise estimation",
        scope="Feature attributes only; not faults, lithologies or CET equivalence",
    )
    return scores


def local_grid_texture(
    values,
    window_size,
    value_range,
    *,
    bins=32,
    minimum_valid_fraction=1.0,
    max_cells=1_000_000,
    max_bin_cells=64_000_000,
    require_valid_center=True,
    canceled=None,
):
    """Local standard deviation (input units) and quantized entropy (bits).

    The quantization range and odd square window are explicit. Values outside
    the range are rejected, not silently clipped. NaN neighbours are omitted
    and counted; centres with NaN or insufficient window coverage remain NaN.
    Outside-grid support is absent, not reflected or fabricated. Entropy
    depends on bins/range/window and is not a lithological classification.
    """
    for value, name, minimum in (
        (window_size, "Window size", 3),
        (bins, "Bins", 2),
        (max_cells, "Maximum cells", 1),
        (max_bin_cells, "Maximum bin-cells", 1),
    ):
        integer_budget(value, name, minimum)
    data, limits = as_array(values, float), as_array(value_range, float)
    fraction = float(minimum_valid_fraction)
    if (
        data.ndim != 2
        or data.size > max_cells
        or window_size % 2 == 0
        or window_size > 101
        or bins > 256
        or data.size * bins > max_bin_cells
    ):
        raise ValueError(
            "Invalid grid/window/bin count or texture work budget exceeded"
        )
    if (
        limits.shape != (2,)
        or not np.isfinite(limits).all()
        or not np.isfinite(limits[1] - limits[0])
        or limits[1] <= limits[0]
        or not 0 < fraction <= 1
    ):
        raise ValueError(
            "Finite increasing quantization limits and coverage fraction in (0,1] are required"
        )
    valid = np.isfinite(data)
    if (
        not valid.any()
        or np.isinf(data).any()
        or np.any(data[valid] < limits[0])
        or np.any(data[valid] > limits[1])
    ):
        raise ValueError(
            "Finite samples must lie inside the explicit quantization range; only NaN denotes missing data"
        )
    _cancel(canceled)
    weight = ndimage.uniform_filter(
        valid.astype(float), window_size, mode="constant", cval=0
    )
    count = np.rint(weight * window_size**2).astype(np.int64)
    quantized = np.zeros(data.shape, dtype=np.int16)
    quantized[valid] = np.minimum(
        np.floor((data[valid] - limits[0]) / (limits[1] - limits[0]) * bins), bins - 1
    ).astype(np.int16)
    entropy = np.zeros(data.shape)
    for level in range(bins):
        _cancel(canceled)
        share = ndimage.uniform_filter(
            ((quantized == level) & valid).astype(float),
            window_size,
            mode="constant",
            cval=0,
        )
        probability = np.divide(
            share, weight, out=np.zeros(data.shape), where=weight > 0
        )
        positive = probability > 0
        entropy[positive] -= probability[positive] * np.log2(probability[positive])
    scale = float(np.max(abs(data[valid]))) or 1.0
    normalized = np.where(valid, data / scale, 0.0)
    mean = np.divide(
        ndimage.uniform_filter(normalized, window_size, mode="constant", cval=0),
        weight,
        out=np.zeros(data.shape),
        where=weight > 0,
    )
    square_mean = np.divide(
        ndimage.uniform_filter(normalized**2, window_size, mode="constant", cval=0),
        weight,
        out=np.zeros(data.shape),
        where=weight > 0,
    )
    standard_deviation = np.sqrt(np.maximum(square_mean - mean**2, 0.0)) * scale
    if not isinstance(require_valid_center, (bool, np.bool_)):
        raise ValueError("require_valid_center must be Boolean")
    accepted = (valid if require_valid_center else np.ones(data.shape, bool)) & (
        count >= np.ceil(fraction * window_size**2)
    )
    entropy = np.clip(entropy, 0, np.log2(bins))
    entropy[~accepted] = np.nan
    standard_deviation[~accepted] = np.nan
    _cancel(canceled)
    return dict(
        entropy_bits=entropy,
        standard_deviation=standard_deviation,
        valid_count=count,
        valid_mask=accepted,
        recipe=dict(
            window_size=window_size,
            bins=bins,
            value_range=limits.tolist(),
            minimum_valid_fraction=fraction,
            require_valid_center=bool(require_valid_center),
            boundary="Outside-grid support absent; no fill",
            entropy_units="bits",
            standard_deviation_units="input units",
            scope="Quantized local texture, not lithology or geological boundaries",
        ),
    )


def local_orientation_entropy(
    azimuth_degrees,
    window_size,
    *,
    bin_origin_degrees,
    bins=18,
    minimum_count=3,
    max_cells=1_000_000,
    canceled=None,
):
    """Axial orientation entropy of sampled directions, not contact density.

    Azimuth is clockwise from grid north, modulo 180 degrees. NaN means no
    orientation sample. Bin origin is explicit because quantized entropy is
    sensitive to bin placement. Statistics can be supported at empty centres
    by neighbouring samples; this does not fill any measured field. Each sample
    has equal weight, not line length or geological confidence. minimum_count
    governs support; orientation entropy does not establish structural genesis.
    """
    integer_budget(window_size, "Window size", 3)
    integer_budget(bins, "Bins", 2)
    integer_budget(minimum_count, "Minimum orientation count")
    integer_budget(max_cells, "Maximum cells")
    angles = as_array(azimuth_degrees, float)
    origin = float(bin_origin_degrees)
    if (
        angles.ndim != 2
        or not angles.size
        or angles.size > max_cells
        or np.isinf(angles).any()
        or not np.isfinite(origin)
        or window_size % 2 == 0
        or window_size > 101
        or bins > 256
        or minimum_count > window_size**2
    ):
        raise ValueError(
            "Invalid orientation grid, bin origin, support/window or budget"
        )
    _cancel(canceled)
    if np.isfinite(angles).any():
        wrapped = np.mod(angles - origin, 180.0)
        result = local_grid_texture(
            wrapped,
            window_size,
            (0.0, 180.0),
            bins=bins,
            minimum_valid_fraction=minimum_count / window_size**2,
            max_cells=max_cells,
            require_valid_center=False,
            canceled=canceled,
        )
        entropy, count, mask = (
            result["entropy_bits"],
            result["valid_count"],
            result["valid_mask"],
        )
    else:
        entropy, count, mask = (
            np.full(angles.shape, np.nan),
            np.zeros(angles.shape, dtype=np.int64),
            np.zeros(angles.shape, bool),
        )
    return dict(
        entropy_bits=entropy,
        entropy_normalized=entropy / np.log2(bins),
        sample_count=count,
        valid_mask=mask,
        recipe=dict(
            window_size=window_size,
            bins=bins,
            bin_origin_degrees=origin,
            minimum_count=minimum_count,
            angles="Axial degrees clockwise from grid north",
            weighting="Equal orientation samples, not line length",
            scope="Neighbourhood orientation diversity, not faults or contact occurrence density",
        ),
    )

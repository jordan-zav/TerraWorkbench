"""Optional archaeological grid processing; independent of proprietary software."""

from __future__ import annotations
import hashlib
from pathlib import Path
import numpy as np


def _positive(value, name):
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(name + " must be finite and positive")
    return value


def directional_transfer(
    shape,
    cell_m,
    *,
    stripe_angle_degrees,
    half_width_degrees,
    wavelength_min_m,
    wavelength_max_m,
    strength,
):
    """Even real notch; stripe angle clockwise from grid north, not true north.

    Raised-cosine radial/angle shoulders suppress only the specified wavelength
    band. DC and all frequencies outside the band remain unchanged.
    """
    cell_m = _positive(cell_m, "Cell size")
    lo = _positive(wavelength_min_m, "Minimum wavelength")
    hi = _positive(wavelength_max_m, "Maximum wavelength")
    angle, width, strength = map(
        float, (stripe_angle_degrees, half_width_degrees, strength)
    )
    if (
        not np.isfinite([angle, width, strength]).all()
        or not 0 < width < 90
        or not 0 <= strength <= 1
    ):
        raise ValueError(
            "Use finite angle, angular half-width between 0 and 90, and strength from 0 to 1"
        )
    if lo >= hi or lo < 2 * cell_m:
        raise ValueError(
            "Wavelength band must be ordered and start at or above two cells"
        )
    if len(shape) != 2 or min(shape) < 2:
        raise ValueError("A 2D grid with at least two cells per axis is required")
    east, north = np.meshgrid(
        np.fft.fftfreq(shape[1], cell_m), np.fft.fftfreq(shape[0], cell_m)
    )
    radius = np.hypot(east, north)
    theta = np.radians(angle % 180)
    # Normal to stripes: north-south stripes have an east-west wavevector.
    alignment = np.divide(
        np.abs(east * np.cos(theta) - north * np.sin(theta)),
        radius,
        out=np.zeros_like(radius),
        where=radius > 0,
    )
    deviation = np.arccos(np.clip(alignment, 0, 1))
    wedge = np.cos(0.5 * np.pi * np.minimum(deviation / np.radians(width), 1)) ** 2
    f0, f1 = 1 / hi, 1 / lo
    position = np.clip((radius - f0) / (f1 - f0), 0, 1)
    band = np.sin(np.pi * position) ** 2
    transfer = 1 - strength * wedge * band
    # Self-aliased Nyquist rows must also respect exact discrete conjugacy.
    reverse = transfer[
        np.ix_((-np.arange(shape[0])) % shape[0], (-np.arange(shape[1])) % shape[1])
    ]
    transfer = (transfer + reverse) * 0.5
    transfer[0, 0] = 1
    return transfer


def directional_filter(grid, cell_m, *, padding_cells=16, **settings):
    from scipy.ndimage import distance_transform_edt

    arr = np.ma.asarray(grid, dtype=float).filled(np.nan)
    if (
        arr.ndim != 2
        or min(arr.shape) < 2
        or np.isinf(arr).any()
        or not np.isfinite(arr).any()
    ):
        raise ValueError("Provide a supported finite 2D grid; NaN is NoData")
    if type(padding_cells) is not int or not 0 <= padding_cells <= 4096:
        raise ValueError("Padding must be integer cells from 0 to 4096")
    if (arr.shape[0] + 2 * padding_cells) * (
        arr.shape[1] + 2 * padding_cells
    ) > 8_000_000:
        raise ValueError("Directional workspace exceeds 8 million cells")
    missing = ~np.isfinite(arr)
    work = arr.copy()
    if missing.any():
        indices = distance_transform_edt(
            missing, return_distances=False, return_indices=True
        )
        work[missing] = work[tuple(indices[:, missing])]
    if padding_cells:
        work = np.pad(work, padding_cells, mode="reflect")
    transfer = directional_transfer(work.shape, cell_m, **settings)
    filtered = np.fft.ifft2(np.fft.fft2(work) * transfer).real
    if padding_cells:
        filtered = filtered[padding_cells:-padding_cells, padding_cells:-padding_cells]
    filtered[missing] = np.nan
    delta = filtered[~missing] - arr[~missing]
    return filtered, dict(
        method="directional-notch-1",
        settings=dict(settings, padding_cells=padding_cells),
        cell_m=float(cell_m),
        orientation="angle clockwise from grid north; rows south to north",
        preparation="nearest fill; reflect padding; original support restored",
        removed_rms=float(np.sqrt(np.mean(delta**2))),
        changed_cells=int(np.count_nonzero(delta)),
        review="Directional archaeological features within the selected band are also attenuated; compare before and after.",
    )


def mosaic_arrays(
    layers, *, reference_index=0, min_overlap_cells=100, mad_clip=4.0, feather_power=1.0
):
    """Robust constant-offset graph fit followed by distance-weighted blending.

    Input layers already occupy one common lattice and union extent. Disconnected
    components retain their own anchor; no unsupported gap is filled.
    """
    from scipy.ndimage import distance_transform_edt

    if not isinstance(layers, (list, tuple)) or not 2 <= len(layers) <= 32:
        raise ValueError("Provide between two and 32 blocks")
    arrays = [np.ma.asarray(a, dtype=float).filled(np.nan) for a in layers]
    shape = arrays[0].shape
    if len(shape) != 2 or any(
        a.shape != shape or np.isinf(a).any() or not np.isfinite(a).any()
        for a in arrays
    ):
        raise ValueError(
            "Blocks must share a 2D lattice and each contain finite samples"
        )
    if np.prod(shape) * len(arrays) > 32_000_000:
        raise ValueError("Mosaic exceeds 32 million layer cells")
    if type(reference_index) is not int or not 0 <= reference_index < len(arrays):
        raise ValueError("Choose an existing reference block")
    if type(min_overlap_cells) is not int or min_overlap_cells < 3:
        raise ValueError("Minimum overlap must be integer and at least three cells")
    mad_clip = _positive(mad_clip, "MAD clipping factor")
    feather_power = float(feather_power)
    if not np.isfinite(feather_power) or not 0 <= feather_power <= 4:
        raise ValueError("Feather power must be from zero to four")
    edges, neighbours = [], [set() for a in arrays]
    for i, a in enumerate(arrays):
        for j in range(i + 1, len(arrays)):
            b = arrays[j]
            valid = np.isfinite(a) & np.isfinite(b)
            d = a[valid] - b[valid]
            if d.size < min_overlap_cells:
                continue
            centre = float(np.median(d))
            mad = float(np.median(np.abs(d - centre)))
            tolerance = max(
                mad_clip * 1.4826 * mad,
                np.finfo(float).eps * max(1.0, float(np.max(np.abs(d)))) * 32,
            )
            kept = np.abs(d - centre) <= tolerance
            if kept.sum() < min_overlap_cells:
                continue
            edges.append(
                dict(
                    i=i,
                    j=j,
                    difference=float(np.median(d[kept])),
                    cells=int(d.size),
                    inliers=int(kept.sum()),
                    mad=mad,
                )
            )
            neighbours[i].add(j)
            neighbours[j].add(i)
    pending = set(range(len(arrays)))
    components = []
    while pending:
        group, stack = [], [min(pending)]
        while stack:
            node = stack.pop()
            if node not in pending:
                continue
            pending.remove(node)
            group.append(node)
            stack.extend(neighbours[node] & pending)
        components.append(sorted(group))
    offsets = np.zeros(len(arrays))
    anchors = []
    for group in components:
        anchor = reference_index if reference_index in group else group[0]
        anchors.append(anchor)
        variables = [i for i in group if i != anchor]
        if not variables:
            continue
        rows, targets = [], []
        for edge in edges:
            if edge["i"] not in group:
                continue
            row = np.zeros(len(variables))
            weight = np.sqrt(edge["inliers"])
            if edge["i"] in variables:
                row[variables.index(edge["i"])] = weight
            if edge["j"] in variables:
                row[variables.index(edge["j"])] = -weight
            rows.append(row)
            targets.append(-edge["difference"] * weight)
        offsets[variables] = np.linalg.lstsq(rows, targets, rcond=None)[0]
    total = np.zeros(shape)
    weighted = np.zeros(shape)
    count = np.zeros(shape, dtype="uint16")
    weights = []
    for a, offset in zip(arrays, offsets):
        valid = np.isfinite(a)
        distance = distance_transform_edt(np.pad(valid, 1))[1:-1, 1:-1]
        w = np.where(valid, distance**feather_power, 0.0)
        weights.append(w)
        total += w
        weighted += np.where(valid, a + offset, 0.0) * w
        count += valid.astype("uint16")
    mosaic = np.divide(weighted, total, out=np.full(shape, np.nan), where=total > 0)
    variance = np.zeros(shape)
    for a, offset, w in zip(arrays, offsets, weights):
        variance += np.where(np.isfinite(a), a + offset - mosaic, 0.0) ** 2 * w
    spread = np.sqrt(
        np.divide(variance, total, out=np.full(shape, np.nan), where=total > 0)
    )
    for edge in edges:
        edge["residual_after"] = (
            edge["difference"] + offsets[edge["i"]] - offsets[edge["j"]]
        )
    metadata = dict(
        method="overlap-offset-feather-1",
        offsets_added=offsets.tolist(),
        overlap_edges=edges,
        connected_components=components,
        component_anchors=anchors,
        reference_index=reference_index,
        min_overlap_cells=min_overlap_cells,
        mad_clip=mad_clip,
        feather_power=feather_power,
        connected=len(components) == 1,
        fitting="pairwise MAD-clipped median; weighted graph least squares; constant offsets only",
        blending="distance to each original support boundary; union mask; no gap filling",
        review="Disconnected groups have independent zero levels. Genuine differences between acquisition epochs can enter the offset fit.",
    )
    return dict(mosaic=mosaic, count=count, overlap_spread=spread), metadata


def _metric(crs):
    from pyproj import CRS

    value = CRS.from_user_input(crs)
    if not value.is_projected or any(
        abs(a.unit_conversion_factor - 1) > 1e-12 for a in value.axis_info[:2]
    ):
        raise ValueError("Use a projected CRS with metre units")


def mosaic_files(paths, **settings):
    import rasterio
    from rasterio.transform import from_origin

    if not 2 <= len(paths) <= 32 or len({Path(p).resolve() for p in paths}) != len(
        paths
    ):
        raise ValueError("Choose two to 32 distinct rasters")
    headers = []
    for path in paths:
        with rasterio.open(path) as ds:
            _metric(ds.crs)
            if (
                ds.count != 1
                or ds.transform.b
                or ds.transform.d
                or ds.transform.a <= 0
                or ds.transform.e >= 0
            ):
                raise ValueError("Use single-band north-up rasters")
            headers.append((ds.crs, ds.res, ds.bounds, ds.tags().get("units")))
    crs, (dx, dy), _, units = headers[0]
    if not units or any(
        h[0] != crs
        or not np.allclose(h[1], (dx, dy), rtol=0, atol=1e-10)
        or h[3] != units
        for h in headers
    ):
        raise ValueError(
            "All blocks must share CRS, resolution and explicit units tags; resampling is not implicit"
        )
    left = min(h[2].left for h in headers)
    top = max(h[2].top for h in headers)
    right = max(h[2].right for h in headers)
    bottom = min(h[2].bottom for h in headers)
    cols = (right - left) / dx
    rows = (top - bottom) / dy
    if (
        abs(cols - round(cols)) > 1e-6
        or abs(rows - round(rows)) > 1e-6
        or round(cols) * round(rows) * len(paths) > 32_000_000
    ):
        raise ValueError(
            "Blocks must share one aligned lattice within the memory limit"
        )
    shape = (round(rows), round(cols))
    layers = []
    for path, header in zip(paths, headers):
        col = (header[2].left - left) / dx
        row = (top - header[2].top) / dy
        if abs(col - round(col)) > 1e-6 or abs(row - round(row)) > 1e-6:
            raise ValueError("Block origins do not align; resampling must be explicit")
        with rasterio.open(path) as ds:
            a = np.full(shape, np.nan)
            r, c = round(row), round(col)
            a[r : r + ds.height, c : c + ds.width] = (
                ds.read(1, masked=True).astype("float64").filled(np.nan)
            )
        layers.append(a)
    products, metadata = mosaic_arrays(layers, **settings)
    metadata.update(inputs=_fingerprints(paths), units=units, settings=settings)
    return products, metadata, from_origin(left, top, dx, dy), crs


def _fingerprints(paths):
    result = []
    for path in paths:
        h = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        result.append(dict(name=Path(path).name, sha256=h.hexdigest()))
    return result


def wavelet_settings(
    shape,
    cell_m,
    *,
    stripe_direction="NS",
    wavelet="db4",
    decomposition_level=3,
    first_level=1,
    last_level=3,
    strength=0.25,
    padding_cells=16,
):
    import pywt

    cell_m = _positive(cell_m, "Cell size")
    if stripe_direction not in ("NS", "EW"):
        raise ValueError("Wavelet stripe direction must be NS or EW in grid axes.")
    if wavelet not in ("haar", "db2", "db4", "sym4"):
        raise ValueError("Choose haar, db2, db4 or sym4.")
    if any(
        type(v) is not int
        for v in (decomposition_level, first_level, last_level, padding_cells)
    ):
        raise ValueError("Wavelet levels and padding must be integers.")
    if not 0 <= padding_cells <= 256:
        raise ValueError("Wavelet padding must be 0–256 cells.")
    maximum = 8
    if shape is not None:
        if len(shape) != 2 or min(shape) < 2 or np.prod(shape) > 4_000_000:
            raise ValueError(
                "Wavelet workspace exceeds limits or invalid raster shape."
            )
        if np.prod(np.array(shape) + 2 * padding_cells) > 8_000_000:
            raise ValueError("Padded wavelet workspace exceeds limit.")
        # Require valid levels on the original grid, not only its padding.
        maximum = pywt.dwtn_max_level(shape, pywt.Wavelet(wavelet))
    if not 1 <= first_level <= last_level <= decomposition_level <= min(maximum, 8):
        raise ValueError(
            f"Wavelet levels must satisfy 1 <= first <= last <= decomposition <= {min(maximum, 8)}."
        )
    strength = float(strength)
    if not np.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError("Wavelet suppression strength must be 0–1.")
    return dict(
        stripe_direction=stripe_direction,
        wavelet=wavelet,
        decomposition_level=decomposition_level,
        first_level=first_level,
        last_level=last_level,
        strength=strength,
        padding_cells=padding_cells,
    )


def wavelet_directional_filter(grid, cell_m, **settings):
    """Directional DWT detail attenuation with exact source support restored.

    Method family: Fedi & Florio (2003), doi:10.1046/j.1365-2478.2003.00373.x;
    archaeological application: Bianco et al. (2024), doi:10.1002/arp.1936.
    This selectable orthogonal-wavelet implementation is not a reproduction
    of the interpolating mother wavelet used by Bianco et al.
    Rows increase south to north. NS stripes vary across columns (cV);
    EW stripes vary across rows (cH). Other details and approximation retained.
    """
    import pywt
    from scipy.ndimage import distance_transform_edt

    arr = np.ma.asarray(grid, dtype=float).filled(np.nan)
    cfg = wavelet_settings(arr.shape, cell_m, **settings)
    if np.isinf(arr).any() or not np.isfinite(arr).any():
        raise ValueError("Wavelet grid needs finite samples without infinities.")
    missing = ~np.isfinite(arr)
    work = arr.copy()
    pad = cfg["padding_cells"]
    if cfg["strength"]:
        if missing.any():
            indices = distance_transform_edt(
                missing, return_distances=False, return_indices=True
            )
            work[missing] = work[tuple(indices[:, missing])]
        if pad:
            work = np.pad(work, pad, mode="reflect")
        magnitude = float(np.max(abs(work)))
        scale = magnitude or 1.0
        coefficients = pywt.wavedec2(
            work / scale,
            cfg["wavelet"],
            mode="symmetric",
            level=cfg["decomposition_level"],
        )
        component = 1 if cfg["stripe_direction"] == "NS" else 0
        for index in range(1, len(coefficients)):
            level = cfg["decomposition_level"] - index + 1
            if cfg["first_level"] <= level <= cfg["last_level"]:
                detail = list(coefficients[index])
                detail[component] = detail[component] * (1 - cfg["strength"])
                coefficients[index] = tuple(detail)
        result = (
            pywt.waverec2(coefficients, cfg["wavelet"], mode="symmetric")[
                : work.shape[0], : work.shape[1]
            ]
            * scale
        )
        if pad:
            result = result[pad:-pad, pad:-pad]
        result[missing] = np.nan
    else:
        result = arr.copy()
    if not np.isfinite(result[~missing]).all():
        raise ValueError("Wavelet numerical overflow.")
    delta = result[~missing] - arr[~missing]
    return result, dict(
        method="directional-dwt-detail-1",
        settings=cfg,
        cell_m=float(cell_m),
        references=[
            "https://doi.org/10.1046/j.1365-2478.2003.00373.x",
            "https://doi.org/10.1002/arp.1936",
        ],
        implementation="Independent orthogonal DWT; differs from the cited interpolating mother wavelet",
        orientation="NS/EW in grid axes; rows south to north",
        preparation="nearest fill; reflect padding; symmetric DWT; original mask restored",
        approximate_detail_scales_m={
            str(level): float(cell_m * 2**level)
            for level in range(cfg["first_level"], cfg["last_level"] + 1)
        },
        removed_rms=float(np.sqrt(np.mean(delta**2))),
        changed_cells=int(np.count_nonzero(delta)),
        review="Real linear anomalies in selected orientations and scales are attenuated too. Inspect original, filtered and removed maps.",
    )

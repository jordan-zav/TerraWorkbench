"""Terrain relief and explicit spatial comparison with magnetic grids."""

from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from scipy.ndimage import uniform_filter, minimum_filter, binary_erosion

MAX_CELLS = 4_000_000
AUTHOR_SOURCE = "https://github.com/horengo/MSRM-Multi-Scale-Relief-Model/blob/master/Original%20GEE%20JavaScript%20implementation.js"


def _hillshade_gradients(values, pixel_transform):
    values = np.ma.asarray(values, dtype=float).filled(np.nan)
    if values.ndim != 2 or min(values.shape) < 2:
        raise ValueError("Hillshade requires at least two rows and columns.")
    matrix = np.asarray(pixel_transform, dtype=float).reshape(2, 2)
    inverse = np.linalg.inv(matrix)
    rows, columns = np.gradient(values)
    for axis, gradient in enumerate((rows, columns)):
        original = np.swapaxes(values, 0, axis)
        derivative = np.swapaxes(gradient, 0, axis)
        difference = np.diff(original, axis=0)
        for target in (derivative[1:], derivative[:-1]):
            missing = ~np.isfinite(target)
            target[missing] = difference[missing]
        derivative[~np.isfinite(original)] = np.nan
    east = columns * inverse[0, 0] + rows * inverse[1, 0]
    north = columns * inverse[0, 1] + rows * inverse[1, 1]
    return values, east, north


def automatic_hillshade_z(values, pixel_transform):
    """Return tan(30°) divided by the 90th percentile of finite gradient magnitudes.

    The four affine coefficients map (column, row) offsets to (east, north).
    Flat or unsupported gradients use a factor of one.
    """
    _, east, north = _hillshade_gradients(values, pixel_transform)
    return _hillshade_z(east, north)


def _hillshade_z(east, north):
    magnitude = np.hypot(east, north)
    valid = magnitude[np.isfinite(magnitude)]
    reference = np.percentile(valid, 90) if valid.size else 0.0
    if reference == 0.0:
        # A mostly flat raster can still contain real gradients.
        positive = valid[valid > 0]
        reference = np.percentile(positive, 90) if positive.size else 0.0
    return math.tan(math.pi / 6) / float(reference) if reference > 0 else 1.0


def _illumination(east, north, azimuth, altitude):
    azimuth, altitude = np.radians(azimuth), np.radians(altitude)
    return np.maximum(0.0, (
        -east * np.sin(azimuth) * np.cos(altitude)
        - north * np.cos(azimuth) * np.cos(altitude)
        + np.sin(altitude)
    ) / np.sqrt(1 + east * east + north * north))


def hillshade_arrays(values, pixel_transform, directions, altitude=45, z_factor=None, canceled=None):
    """Yield one shaded array per direction and the shared, effective z factor.

    Azimuths are clockwise from north. Edges and neighbours of holes use
    one-sided differences where possible. Original holes stay masked.
    """
    values, east, north = _hillshade_gradients(values, pixel_transform)
    factor = _hillshade_z(east, north) if z_factor is None else float(z_factor)
    if not np.isfinite(factor) or factor <= 0 or not 0 <= altitude <= 90:
        raise ValueError("Hillshade requires a positive finite z factor and altitude in [0, 90].")
    valid = np.isfinite(values)
    east = np.nan_to_num(east, nan=0.0, posinf=0.0, neginf=0.0) * factor
    north = np.nan_to_num(north, nan=0.0, posinf=0.0, neginf=0.0) * factor
    for azimuth in directions:
        _check(canceled)
        if not np.isfinite(azimuth):
            raise ValueError("Hillshade azimuth must be finite.")
        shading = _illumination(east, north, azimuth, altitude)
        yield np.where(valid, shading, np.nan), factor


def _check(canceled):
    if canceled and canceled():
        raise InterruptedError("Terrain processing canceled.")


def _hash(path, canceled):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            _check(canceled)
            digest.update(block)
    return digest.hexdigest()


def _metre_crs(crs):
    from pyproj import CRS

    value = CRS.from_user_input(crs)
    return value.is_projected and all(
        abs(axis.unit_conversion_factor - 1.0) < 1e-9 for axis in value.axis_info[:2]
    )


def _box(values, radius, canceled=None):
    _check(canceled)
    if radius < 0 or radius > 1024:
        raise ValueError("Terrain boxcar radius must be between 0 and 1024 cells.")
    finite = np.isfinite(values)
    width = 2 * radius + 1
    # A full footprint is required: no extrapolation at dataset edges or gaps.
    support = minimum_filter(
        finite.astype(np.uint8), size=width, mode="constant", cval=0
    ).astype(bool)
    center = float(np.median(values[finite])) if finite.any() else 0.0
    output = (
        uniform_filter(
            np.where(finite, values - center, 0.0),
            size=width,
            mode="constant",
            cval=0.0,
        )
        + center
    )
    output[~support] = np.nan
    return output


def relief_arrays(
    values,
    resolution_metres,
    scales_metres,
    msrm_min_metres,
    msrm_max_metres,
    msrm_exponent=2.0,
    canceled=None,
):
    """Native square-pixel relief, no resampling; elevation values are metres.

    Local residual is elevation minus a square boxcar mean. MSRM is the
    author's mean of consecutive low-pass surface differences; fractional
    pixel radii are rounded upward and recorded. No export rounding is applied.
    """
    values = np.ma.asarray(values, dtype=float).filled(np.nan)
    if values.ndim != 2 or values.size > MAX_CELLS:
        raise ValueError(
            "Terrain processing requires a 2D grid of at most 4 million cells."
        )
    args = [resolution_metres, msrm_min_metres, msrm_max_metres, msrm_exponent] + list(
        scales_metres
    )
    if not all(np.isfinite(v) and v > 0 for v in args):
        raise ValueError(
            "Terrain scales, resolution and exponent must be finite and positive."
        )
    if not 1 <= len(scales_metres) <= 8 or msrm_max_metres <= max(
        msrm_min_metres, resolution_metres
    ):
        raise ValueError(
            "Provide 1 to 8 LRM scales and an MSRM maximum greater than its minimum and cell size."
        )
    if not 0.1 <= msrm_exponent <= 8:
        raise ValueError("MSRM exponent must be between 0.1 and 8.")
    rr = float(resolution_metres)
    i = math.floor(((max(msrm_min_metres, rr) - rr) / (2 * rr)) ** (1 / msrm_exponent))
    n = math.ceil(((msrm_max_metres - rr) / (2 * rr)) ** (1 / msrm_exponent))
    if n - i < 1 or n - i > 64 or n**msrm_exponent > 1024:
        raise ValueError("MSRM exceeds 64 relief intervals or 1024-cell radius.")
    arrays = {"terrain_dtm": values.copy()}
    windows = {}
    for scale in scales_metres:
        radius = math.ceil(float(scale) / (2 * rr))
        key = "terrain_lrm_" + format(float(scale), "g").replace(".", "p") + "m"
        if key in windows:
            raise ValueError("Duplicate LRM scales.")
        arrays[key] = values - _box(values, radius, canceled)
        windows[key] = {
            "requested_width_metres": float(scale),
            "radius_cells": radius,
            "effective_width_metres": (2 * radius + 1) * rr,
        }
    radii = [math.ceil(k**msrm_exponent) for k in range(i, n + 1)]
    previous = _box(values, radii[0], canceled)
    accumulated = np.zeros(values.shape)
    support = np.isfinite(previous)
    for radius in radii[1:]:
        current = _box(values, radius, canceled)
        support &= np.isfinite(current)
        accumulated += np.nan_to_num(previous - current)
        previous = current
    arrays["terrain_msrm"] = np.where(support, accumulated / (n - i), np.nan)
    gradient_support = binary_erosion(
        np.isfinite(values), structure=np.ones((3, 3)), border_value=0
    )
    if min(values.shape) < 3:
        raise ValueError("DTM requires at least three rows and columns.")
    dzdy, dzdx = np.gradient(values, rr, rr)
    slope = np.arctan(np.hypot(dzdx, dzdy))
    arrays["terrain_slope"] = np.where(gradient_support, np.degrees(slope), np.nan)
    arrays["terrain_hillshade"] = np.where(
        gradient_support, _illumination(dzdx, -dzdy, 315.0, 45.0), np.nan
    )
    arrays["terrain_support"] = support.astype(float)
    return arrays, {
        "lrm": windows,
        "msrm": {
            "minimum_metres": float(msrm_min_metres),
            "maximum_metres": float(msrm_max_metres),
            "exponent": float(msrm_exponent),
            "i": i,
            "n": n,
            "radii_cells": radii,
            "source": AUTHOR_SOURCE,
            "boundary": "full square footprint; gaps and outer edges masked",
            "export_rounding": False,
        },
    }


def run_terrain(
    dtm_path,
    magnetic_path,
    output_dir,
    scales_metres=(5.0, 20.0),
    msrm_min_metres=1.0,
    msrm_max_metres=20.0,
    msrm_exponent=2.0,
    elevation_unit="m",
    canceled=None,
):
    """Publish terrain products on the exact magnetic grid and correlation evidence.

    DTM elevations require explicit metre or foot units. Relief is computed at
    native DTM resolution before bilinear alignment. Geographic DTMs are first
    warped to the magnetic projected metre CRS at GDAL estimated resolution.
    Correlation measures spatial association and does not assign anomaly age.
    """
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from rasterio.transform import from_origin

    _check(canceled)
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError(
            "Terrain output directory already exists; use a new run directory."
        )
    if elevation_unit not in ("m", "ft"):
        raise ValueError("Elevation unit must be explicitly m or ft.")
    provenance = {
        name: {"path": str(Path(path).resolve()), "sha256": _hash(path, canceled)}
        for name, path in [("dtm", dtm_path), ("magnetic", magnetic_path)]
    }
    with rasterio.open(magnetic_path) as reference:
        if not reference.crs or not _metre_crs(reference.crs):
            raise ValueError("Magnetic reference must have a projected metre CRS.")
        if reference.width * reference.height > MAX_CELLS:
            raise ValueError("Magnetic reference exceeds 4 million cells.")
        target_transform, target_crs, target_shape = (
            reference.transform,
            reference.crs,
            reference.shape,
        )
        if (
            target_transform.b
            or target_transform.d
            or target_transform.a <= 0
            or target_transform.e >= 0
        ):
            raise ValueError("Magnetic reference must be north-up and unrotated.")
        magnetic = reference.read(1, masked=True).astype(float).filled(np.nan)
        profile = reference.profile.copy()
    with rasterio.open(dtm_path) as dtm:
        if not dtm.crs:
            raise ValueError("DTM requires a CRS.")
        if dtm.width * dtm.height > MAX_CELLS:
            raise ValueError("Native DTM exceeds 4 million cells.")
        native = dtm.read(1, masked=True).astype(float).filled(np.nan) * (
            0.3048 if elevation_unit == "ft" else 1.0
        )
        native[~np.isfinite(native)] = np.nan
        transform, crs = dtm.transform, dtm.crs
        warp_native = (
            not _metre_crs(crs)
            or transform.b
            or transform.d
            or transform.a <= 0
            or transform.e >= 0
            or not np.isclose(transform.a, -transform.e)
        )
        if warp_native:
            transform, width, height = calculate_default_transform(
                crs, target_crs, dtm.width, dtm.height, *dtm.bounds
            )
            rr = max(abs(transform.a), abs(transform.e))
            width = math.ceil(width * abs(transform.a) / rr)
            height = math.ceil(height * abs(transform.e) / rr)
            transform = from_origin(transform.c, transform.f, rr, rr)
            if width * height > MAX_CELLS:
                raise ValueError("Reprojected DTM exceeds 4 million cells.")
            warped = np.full((height, width), np.nan)
            _check(canceled)
            reproject(
                native,
                warped,
                src_transform=dtm.transform,
                src_crs=crs,
                dst_transform=transform,
                dst_crs=target_crs,
                src_nodata=np.nan,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
                num_threads=1,
            )
            native, crs = warped, target_crs
    rr = abs(transform.a)
    arrays, methods = relief_arrays(
        native,
        rr,
        scales_metres,
        msrm_min_metres,
        msrm_max_metres,
        msrm_exponent,
        canceled,
    )
    aligned, metrics = {}, {}
    for key, array in arrays.items():
        _check(canceled)
        dest = np.full(target_shape, np.nan)
        reproject(
            array,
            dest,
            src_transform=transform,
            src_crs=crs,
            dst_transform=target_transform,
            dst_crs=target_crs,
            src_nodata=np.nan,
            dst_nodata=np.nan,
            resampling=Resampling.nearest
            if key == "terrain_support"
            else Resampling.bilinear,
            num_threads=1,
        )
        # Bilinear may interpolate next to nodata; nearest valid support keeps
        # unsupported footprints excluded from visual fusion.
        valid = np.zeros(target_shape, dtype=np.uint8)
        reproject(
            np.isfinite(array).astype(np.uint8),
            valid,
            src_transform=transform,
            src_crs=crs,
            dst_transform=target_transform,
            dst_crs=target_crs,
            resampling=Resampling.nearest,
            num_threads=1,
        )
        dest[(valid == 0) | ~np.isfinite(magnetic)] = np.nan
        aligned[key] = dest
        common = np.isfinite(dest) & np.isfinite(magnetic)
        count = int(common.sum())
        correlation = None
        if count >= 3 and np.std(dest[common]) > 0 and np.std(magnetic[common]) > 0:
            correlation = float(np.corrcoef(dest[common], magnetic[common])[0, 1])
        metrics[key] = {
            "common_cells": count,
            "fraction_magnetic_support": count
            / max(1, int(np.isfinite(magnetic).sum())),
            "pearson_correlation": correlation,
        }
    if not metrics["terrain_dtm"]["common_cells"]:
        raise ValueError("DTM and magnetic grid have no finite overlap.")
    report = {
        "sources": provenance,
        "methods": methods,
        "native_cell_metres": rr,
        "native_reprojected": bool(warp_native),
        "target_crs": str(target_crs),
        "target_transform": list(target_transform),
        "target_shape": list(target_shape),
        "elevation_input_unit": elevation_unit,
        "resampling": "bilinear terrain; nearest support; masked to magnetic finite support",
        "metrics": metrics,
        "hillshade": {"azimuth_degrees": 315.0, "altitude_degrees": 45.0},
    }
    report["warnings"] = [
        key
        + " has no common supported cells; reduce relief scales or inspect terrain coverage."
        for key, value in metrics.items()
        if not value["common_cells"]
    ]
    _check(canceled)
    output_dir.mkdir(parents=True)
    products = {}
    try:
        profile.update(
            driver="GTiff", count=1, dtype="float64", nodata=np.nan, compress="deflate"
        )
        for key, array in aligned.items():
            _check(canceled)
            path = output_dir / (key + ".tif")
            unit = (
                "degrees"
                if key == "terrain_slope"
                else "dimensionless"
                if key in ("terrain_hillshade", "terrain_support")
                else "m"
            )
            with rasterio.open(path, "w", **profile) as dest:
                dest.write(array, 1)
                dest.update_tags(
                    units=unit,
                    terrain_method=key,
                    source_dtm_sha256=provenance["dtm"]["sha256"],
                )
                dest.set_band_unit(1, unit)
            products[key] = str(path)
        report_path = output_dir / "terrain_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
        )
        _check(canceled)
    except BaseException:
        for path in output_dir.iterdir():
            path.unlink()
        output_dir.rmdir()
        raise
    return {"products": products, "report": report, "report_path": str(report_path)}

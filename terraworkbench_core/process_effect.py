"""Compare the numerical effect of two aligned, same-unit GeoTIFF grids."""
from __future__ import annotations

import numpy as np


def _check(canceled):
    if canceled and canceled():
        raise InterruptedError("Process-effect comparison canceled.")


def _units(raster):
    values = []
    for tags in (raster.tags(), raster.tags(1)):
        for key, value in tags.items():
            if key.lower() in ("units", "unittype") and str(value).strip():
                values.append(str(value).strip())
    band_unit = raster.units[0]
    if band_unit and str(band_unit).strip():
        values.append(str(band_unit).strip())
    if len(set(values)) > 1:
        raise ValueError("Conflicting unit metadata in a grid.")
    return values[0] if values else None


def compare_geotiffs(before_path, after_path, canceled=None):
    """Return before/after/effect arrays and common-support change statistics.

    Arrays retain GeoTIFF row order (north to south); display with origin upper.
    No resampling, unit conversion or support expansion is performed. Missing
    unit tags are allowed only when absent on both grids. Metrics use only cells
    finite in both grids. Individual arrays preserve their original valid cells.
    """
    import rasterio

    _check(canceled)
    with rasterio.open(before_path) as before_raster, rasterio.open(after_path) as after_raster:
        if before_raster.shape != after_raster.shape:
            raise ValueError("Grids must have exactly the same shape.")
        if before_raster.crs != after_raster.crs:
            raise ValueError("Grids must have exactly the same CRS.")
        if before_raster.transform != after_raster.transform:
            raise ValueError("Grids must have exactly the same transform; no resampling is performed.")
        if before_raster.width * before_raster.height > 4_000_000:
            raise ValueError("Comparison exceeds 4 million grid cells.")
        transform = before_raster.transform
        if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
            raise ValueError("Comparison requires north-up, unrotated grids.")
        before_unit, after_unit = _units(before_raster), _units(after_raster)
        if before_unit != after_unit:
            raise ValueError("Grid units must match, including their metadata availability.")
        for raster in (before_raster, after_raster):
            if np.dtype(raster.dtypes[0]).kind not in 'iuf':
                raise ValueError("Comparison requires real numerical grid values.")
        _check(canceled)
        before = before_raster.read(1, masked=True).astype(np.float64).filled(np.nan)
        _check(canceled)
        after = after_raster.read(1, masked=True).astype(np.float64).filled(np.nan)
        bounds = before_raster.bounds
        extent = [float(bounds.left), float(bounds.right), float(bounds.bottom), float(bounds.top)]
        crs = before_raster.crs.to_string() if before_raster.crs else None
    _check(canceled)
    before[~np.isfinite(before)] = np.nan
    after[~np.isfinite(after)] = np.nan
    supported_before, supported_after = np.isfinite(before), np.isfinite(after)
    common = supported_before & supported_after
    count = int(common.sum())
    if not count:
        raise ValueError("Grids have no finite cells in common.")
    difference = np.full(before.shape, np.nan, dtype=np.float64)
    with np.errstate(over='ignore', invalid='ignore'):
        change = after[common] - before[common]
    if not np.isfinite(change).all():
        raise ValueError("Grid differences exceed finite numerical range.")
    difference[common] = change
    absolute = np.abs(change)
    # Scale RMS before squaring to avoid overflow from otherwise finite changes.
    scale = float(absolute.max())
    rmse = float(np.sqrt(np.mean((change / scale)**2)) * scale) if scale else 0.
    mean_change = float(np.mean(change / scale) * scale) if scale else 0.
    mae = float(np.mean(absolute / scale) * scale) if scale else 0.
    metrics = {"common_cells": count,
               "before_only_cells": int((supported_before & ~supported_after).sum()),
               "after_only_cells": int((supported_after & ~supported_before).sum()),
               "mean_change": mean_change, "mae": mae, "rmse": rmse,
               "p95": float(np.percentile(absolute, 95)), "max_abs": scale}
    _check(canceled)
    return {"before": before, "after": after, "difference": difference,
            "extent": extent, "units": before_unit or "unknown", "metrics": metrics,
            "before_path": str(before_path), "after_path": str(after_path),
            "crs": crs, "transform": list(transform), "array_orientation": "north-to-south rows",
            "difference_definition": "after minus before on finite common support",
            "units_verified": before_unit is not None}

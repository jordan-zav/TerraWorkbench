"""Explicit horizontal-only, blocked coordinate transformation with PyProj."""

import numpy as np
from importlib.metadata import version

from ._array_contract import as_array
from ._calibration import integer_budget


def reproject_xy(
    x,
    y,
    source_crs,
    target_crs,
    *,
    block_size=100_000,
    max_points=10_000_000,
    canceled=None,
):
    """Transform aligned 1-D XY arrays, always XY, with no ballpark fallback.

    CRSs must be explicit geographic/projected 2-D definitions. Invalid input
    pairs remain NaN. A failure at a finite coordinate raises, never changes
    source coordinates or invents a vertical transformation. Required missing
    datum grids are errors (only_best=True), not silently substituted operations.
    """
    integer_budget(block_size, "Block size")
    integer_budget(max_points, "Maximum points")
    x, y = as_array(x, float), as_array(y, float)
    if x.ndim != 1 or y.shape != x.shape or x.size > max_points:
        raise ValueError("Aligned 1-D XY arrays within the point budget are required")
    if canceled is not None and canceled():
        raise RuntimeError("Coordinate transformation canceled")
    from pyproj import CRS, Transformer

    source, target = CRS.from_user_input(source_crs), CRS.from_user_input(target_crs)
    if any(
        len(crs.axis_info) != 2 or not (crs.is_geographic or crs.is_projected)
        for crs in (source, target)
    ):
        raise ValueError(
            "Only explicit horizontal 2-D geographic/projected CRSs are supported"
        )
    transformer = Transformer.from_crs(
        source, target, always_xy=True, allow_ballpark=False, only_best=True
    )
    output_x, output_y = np.full(x.shape, np.nan), np.full(y.shape, np.nan)
    valid = np.isfinite(x) & np.isfinite(y)
    for first in range(0, x.size, block_size):
        if canceled is not None and canceled():
            raise RuntimeError("Coordinate transformation canceled")
        indices = np.flatnonzero(valid[first : first + block_size]) + first
        if indices.size:
            if indices.size == 1:
                a, b = transformer.transform(
                    float(x[indices[0]]), float(y[indices[0]]), errcheck=True
                )
            else:
                a, b = transformer.transform(x[indices], y[indices], errcheck=True)
            if not np.isfinite(a).all() or not np.isfinite(b).all():
                raise ValueError(
                    "Projection returned nonfinite values for finite input"
                )
            output_x[indices], output_y[indices] = a, b
    if canceled is not None and canceled():
        raise RuntimeError("Coordinate transformation canceled")
    return dict(
        engine="pyproj",
        engine_version=version("pyproj"),
        x=output_x,
        y=output_y,
        valid=valid,
        recipe=dict(
            source_crs=source.to_wkt(),
            target_crs=target.to_wkt(),
            always_xy=True,
            allow_ballpark=False,
            only_best=True,
            vertical_transformation=False,
            description=transformer.description,
            accuracy_m=transformer.accuracy,
        ),
    )

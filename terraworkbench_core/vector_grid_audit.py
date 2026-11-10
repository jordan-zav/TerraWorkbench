"""Generic polygon/grid sampling; missing and subcell features are explicit."""

import numpy as np


def polygon_samples(values, geometry, transform):
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds
    from affine import Affine

    values = np.ma.asarray(values, dtype=float).filled(np.nan)
    if values.ndim != 2:
        raise ValueError("Polygon sampling requires a 2D array.")
    if transform.b or transform.d or transform.a <= 0 or transform.e >= 0:
        raise ValueError("Polygon sampling requires a north-up grid.")
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("Polygon must be nonempty and valid.")
    window = from_bounds(*geometry.bounds, transform=transform)
    row0 = int(np.floor(window.row_off))
    col0 = int(np.floor(window.col_off))
    row1 = int(np.ceil(window.row_off + window.height))
    col1 = int(np.ceil(window.col_off + window.width))
    height = max(1, row1 - row0)
    width = max(1, col1 - col0)
    if height * width > 4_000_000:
        raise ValueError("Polygon sampling window exceeds four million cells.")
    inside = geometry_mask(
        [geometry.__geo_interface__],
        out_shape=(height, width),
        transform=transform * Affine.translation(col0, row0),
        invert=True,
        all_touched=False,
    )
    expected = int(inside.sum())
    r0 = max(0, row0)
    r1 = min(values.shape[0], row1)
    c0 = max(0, col0)
    c1 = min(values.shape[1], col1)
    if r0 >= r1 or c0 >= c1:
        return np.empty(0), dict(
            expected_cells=expected,
            valid_cells=0,
            coverage_fraction=0.0 if expected else None,
        )
    sample = values[r0:r1, c0:c1]
    select = inside[r0 - row0 : r1 - row0, c0 - col0 : c1 - col0] & np.isfinite(sample)
    selected = sample[select]
    return selected, dict(
        expected_cells=expected,
        valid_cells=len(selected),
        coverage_fraction=len(selected) / expected if expected else None,
    )


def prepare_polygon(shape, geometry, transform):
    """Prepare center-in-polygon indices once for repeated depth slices."""
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds
    from affine import Affine

    if transform.b or transform.d or transform.a <= 0 or transform.e >= 0:
        raise ValueError("Polygon sampling requires a north-up grid.")
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("Polygon must be nonempty and valid.")
    window = from_bounds(*geometry.bounds, transform=transform)
    row0 = int(np.floor(window.row_off))
    col0 = int(np.floor(window.col_off))
    height = max(1, int(np.ceil(window.row_off + window.height)) - row0)
    width = max(1, int(np.ceil(window.col_off + window.width)) - col0)
    if height * width > 4_000_000:
        raise ValueError("Polygon sampling window exceeds four million cells.")
    inside = geometry_mask(
        [geometry.__geo_interface__],
        out_shape=(height, width),
        transform=transform * Affine.translation(col0, row0),
        invert=True,
        all_touched=False,
    )
    rr, cc = np.nonzero(inside)
    rr += row0
    cc += col0
    expected = len(rr)
    valid = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    return rr[valid], cc[valid], expected


def prepared_samples(values, prepared):
    rows, cols, expected = prepared
    sample = np.ma.asarray(values, dtype=float).filled(np.nan)[rows, cols]
    sample = sample[np.isfinite(sample)]
    return sample, dict(
        expected_cells=expected,
        valid_cells=len(sample),
        coverage_fraction=len(sample) / expected if expected else None,
    )

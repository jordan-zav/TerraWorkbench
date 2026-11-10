"""Physical cumulative horizontal distance in acquisition order."""

import numpy as np


def along_profile_distance(x, y, crs):
    try:
        from pyproj import CRS
    except ImportError as error:
        raise ImportError(
            "Physical profile distance requires terraworkbench-core[coordinates] (pyproj)"
        ) from error
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.ndim != 1 or y.shape != x.shape:
        raise ValueError("Profile X and Y must be equal-length vectors.")
    system = CRS.from_user_input(crs)
    if not (system.is_geographic or system.is_projected or system.is_engineering):
        raise ValueError("Distance requires a geographic or linear coordinate system.")
    if len(system.axis_info) < 2:
        raise ValueError("Coordinate units are required for distance.")
    factors = [a.unit_conversion_factor for a in system.axis_info[:2]]
    if any(f is None or not np.isfinite(f) or f <= 0 for f in factors):
        raise ValueError("Coordinate units cannot be converted.")
    valid = np.isfinite(x) & np.isfinite(y)
    distance = np.full(x.shape, np.nan)
    if not valid.any():
        raise ValueError("No finite coordinate pairs for distance.")
    steps = np.zeros(x.size, dtype=float)
    connected = valid[1:] & valid[:-1]
    rows = np.flatnonzero(connected) + 1
    if system.is_geographic:
        xx = x * factors[0] * 180 / np.pi
        yy = y * factors[1] * 180 / np.pi
        if np.any(abs(xx[valid]) > 180) or np.any(abs(yy[valid]) > 90):
            raise ValueError(
                "Invalid longitude/latitude for distance; confirm source CRS and columns."
            )
        _, _, segments = system.get_geod().inv(
            xx[rows - 1], yy[rows - 1], xx[rows], yy[rows]
        )
        steps[rows] = segments
    else:
        steps[rows] = np.hypot(
            (x[rows] - x[rows - 1]) * factors[0], (y[rows] - y[rows - 1]) * factors[1]
        )
    if not np.isfinite(steps).all():
        raise ValueError("Coordinate distance could not be calculated.")
    distance[valid] = np.cumsum(steps)[valid]
    return distance

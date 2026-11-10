"""Depth QC and minimum-curvature well trajectory; no LAS/DLIS format claim."""

import numpy as np

from ._array_contract import as_array


def minimum_curvature_trajectory(
    measured_depth_m, inclination_deg, azimuth_deg, *, collar_enu_m
):
    """Survey-station ENU coordinates by circular-arc minimum curvature.

    Inclination measured from downward vertical; azimuth clockwise from north.
    Survey starts at measured depth zero at the explicit collar; no invented
    unsurveyed segment. Antipodal directions are ambiguous and rejected.
    CRS/datum/declination correction must be established externally.
    """
    md, inclination, azimuth, collar = [
        as_array(a, float)
        for a in (measured_depth_m, inclination_deg, azimuth_deg, collar_enu_m)
    ]
    if (
        md.ndim != 1
        or md.size < 2
        or inclination.shape != md.shape
        or azimuth.shape != md.shape
        or collar.shape != (3,)
        or not all(np.isfinite(a).all() for a in (md, inclination, azimuth, collar))
        or md[0] != 0
        or np.any(np.diff(md) <= 0)
        or np.any(inclination < 0)
        or np.any(inclination > 180)
    ):
        raise ValueError(
            "Finite increasing MD from zero, matching directions and explicit ENU collar required"
        )
    inc, azi = np.deg2rad(inclination), np.deg2rad(azimuth)
    directions = np.column_stack(
        [np.sin(inc) * np.sin(azi), np.sin(inc) * np.cos(azi), -np.cos(inc)]
    )
    dogleg = np.arccos(np.clip(np.sum(directions[:-1] * directions[1:], axis=1), -1, 1))
    if np.any(dogleg > np.pi - 1e-6):
        raise ValueError(
            "Antipodal survey orientations have no unique minimum-curvature arc"
        )
    ratio = np.ones(dogleg.shape)
    nonzero = dogleg > 1e-7
    ratio[nonzero] = 2 * np.tan(dogleg[nonzero] / 2) / dogleg[nonzero]
    step = (
        np.diff(md)[:, None] * (directions[:-1] + directions[1:]) * ratio[:, None] / 2
    )
    position = np.vstack([collar, collar + np.cumsum(step, axis=0)])
    return {
        "measured_depth_m": md.copy(),
        "coordinates_enu_m": position,
        "true_vertical_depth_m": collar[2] - position[:, 2],
        "dogleg_deg": np.rad2deg(dogleg),
        "dogleg_deg_per_30m": np.rad2deg(dogleg) * 30 / np.diff(md),
        "convention": "inclination from down; azimuth clockwise from north; z up",
    }


def log_depth_qc(depth_m, curves, *, missing_value=None, maximum_gap_m):
    """Validate depth order, retain curve NoData, report gaps/duplicates.

    Does NOT silently sort, merge duplicate depths, fill gaps, assign a depth
    datum or convert an unknown curve unit. Numeric text import is separate
    from dedicated LAS/DLIS metadata preservation.
    """
    depth, data = as_array(depth_m, float), as_array(curves, float)
    if (
        depth.ndim != 1
        or depth.size < 2
        or not np.isfinite(depth).all()
        or data.ndim != 2
        or data.shape[0] != depth.size
        or np.isinf(data).any()
    ):
        raise ValueError(
            "Finite depth vector and matching (sample,curve) matrix required"
        )
    if not np.isfinite(maximum_gap_m) or maximum_gap_m <= 0:
        raise ValueError("Explicit positive depth-gap threshold required")
    output = data.copy()
    if missing_value is not None:
        if not np.isfinite(missing_value):
            raise ValueError("Missing sentinel must be finite or None")
        output[output == missing_value] = np.nan
    delta = np.diff(depth)
    return {
        "depth_m": depth.copy(),
        "curves": output,
        "strictly_increasing": bool(np.all(delta > 0)),
        "strictly_decreasing": bool(np.all(delta < 0)),
        "duplicate_intervals": np.flatnonzero(delta == 0),
        "large_gap_intervals": np.flatnonzero(abs(delta) > maximum_gap_m),
        "direction_reversals": np.flatnonzero(delta[:-1] * delta[1:] < 0) + 1,
        "missing_count_per_curve": np.isnan(output).sum(axis=0),
        "warning": "Depth datum and curve units require explicit source metadata",
    }

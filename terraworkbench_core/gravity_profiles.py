"""Analytic 2-D polygon gravity and fixed-geometry density estimation.

Coordinates are cross-section x and upward z, metres; density is kg/m3.
Bodies extend infinitely normal to the section. Returned vertical gravity is
positive downward in mGal. No end, terrain, datum or regional correction.
"""

import numpy as np
from scipy.constants import G

from ._array_contract import as_array
from ._calibration import gaussian_calibration, integer_budget


def _cross(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def _polygon(vertices):
    p = as_array(vertices, float)
    if p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(p).all():
        raise ValueError("Polygon requires finite x/upward-z vertices")
    if len(p) > 1 and np.array_equal(p[0], p[-1]):
        p = p[:-1]
    if not 3 <= len(p) <= 1024:
        raise ValueError("A polygon needs 3 to 1024 vertices")
    p = p - p[0]  # geometry checks do not depend on large survey offsets
    q = np.roll(p, -1, axis=0)
    scale = float(np.max(np.ptp(p, axis=0)))
    tolerance = 1e-12 * scale**2
    if scale == 0 or np.any(np.linalg.norm(q - p, axis=1) <= 1e-12 * scale):
        raise ValueError("Repeated/degenerate polygon edge")
    area2 = float(np.sum(_cross(p, q)))
    if abs(area2) <= tolerance:
        raise ValueError("Degenerate polygon area")
    # Reject self-crossing and nonadjacent touching/overlapping segments.
    for i in range(len(p) - 2):
        indices = np.arange(i + 2, len(p))
        if i == 0:
            indices = indices[indices != len(p) - 1]
        a, b = p[indices], q[indices]
        o1, o2 = _cross(q[i] - p[i], a - p[i]), _cross(q[i] - p[i], b - p[i])
        o3, o4 = _cross(b - a, p[i] - a), _cross(b - a, q[i] - a)
        crossing = (
            (o1 <= tolerance) & (o2 >= -tolerance)
            | (o2 <= tolerance) & (o1 >= -tolerance)
        ) & (
            (o3 <= tolerance) & (o4 >= -tolerance)
            | (o4 <= tolerance) & (o3 >= -tolerance)
        )
        overlap = np.all(
            np.maximum(np.minimum(p[i], q[i]), np.minimum(a, b))
            <= np.minimum(np.maximum(p[i], q[i]), np.maximum(a, b)) + 1e-12 * scale,
            axis=1,
        )
        if np.any(crossing & overlap):
            raise ValueError("Polygon edges intersect or touch nonadjacent edges")
    original = as_array(vertices, float)
    if len(original) != len(p):
        original = original[:-1]
    return original.copy() if area2 > 0 else original[::-1].copy()


def _primitive(s, height):
    radius2 = s * s + height * height
    product = np.zeros_like(s)
    np.multiply(
        s, np.log(np.maximum(radius2, np.finfo(float).tiny)), out=product, where=s != 0
    )
    return product - 2 * s + 2 * height * np.arctan2(s, height)


def polygon_gravity_2d(
    observation_xz_m,
    polygons_xz_m,
    density_kg_m3,
    *,
    max_interactions=20_000_000,
    block_size=256,
    canceled=None,
):
    """Integrate polygon edges analytically; horizontal edges need no perturbation.

    Simple concave polygons and either vertex order are supported. Holes require
    separate negative-contrast bodies. Overlapping bodies add their contrasts.
    Limits count station-edge interactions, not just rectangular grid size.
    """
    integer_budget(max_interactions, "max_interactions")
    integer_budget(block_size, "block_size")
    obs = as_array(observation_xz_m, float)
    if obs.ndim != 2 or obs.shape[1] != 2 or not len(obs) or not np.isfinite(obs).all():
        raise ValueError("Finite nonempty station x/upward-z matrix required")
    if (
        not isinstance(polygons_xz_m, (list, tuple, np.ndarray))
        or not 1 <= len(polygons_xz_m) <= 128
    ):
        raise ValueError("Supply 1 to 128 polygon bodies")
    if canceled is not None and canceled():
        raise InterruptedError("Polygon gravity canceled")
    polygons = [_polygon(p) for p in polygons_xz_m]
    density = as_array(density_kg_m3, float)
    if density.shape != (len(polygons),) or not np.isfinite(density).all():
        raise ValueError("Finite density contrast per polygon required")
    interactions = len(obs) * sum(len(p) for p in polygons)
    if interactions > max_interactions:
        raise ValueError("Polygon interaction budget exceeded")
    result = np.zeros(len(obs))
    for polygon, rho in zip(polygons, density):
        origin = polygon[0]
        p = polygon - origin
        edge = np.roll(p, -1, axis=0) - p
        length = np.linalg.norm(edge, axis=1)
        unit = edge / length[:, None]
        for start in range(0, len(obs), block_size):
            if canceled is not None and canceled():
                raise InterruptedError("Polygon gravity canceled")
            delta = (
                p[None, :, :] - (obs[start : start + block_size] - origin)[:, None, :]
            )
            along = np.sum(delta * unit, axis=-1)
            height = abs(_cross(delta, unit))
            integral = _primitive(along + length, height) - _primitive(along, height)
            result[start : start + block_size] += (
                G * 1e5 * rho * np.sum(unit[:, 0] * integral, axis=1)
            )
    if not np.isfinite(result).all():
        raise ValueError("Polygon gravity arithmetic overflow")
    return dict(
        gravity_mgal=result,
        recipe=dict(
            method="analytic-polygon-log-edge-integral",
            coordinates="x and upward z, metres",
            gravity_positive="down",
            density_unit="kg/m3",
            extent="infinite out-of-section strike",
            interactions=interactions,
            gravitational_constant_si=float(G),
        ),
    )


def fit_polygon_densities(
    observation_xz_m,
    polygons_xz_m,
    observed_mgal,
    reading_std_mgal,
    *,
    fit_offset=False,
    maximum_condition=1e8,
    max_elements=2_000_000,
    max_interactions=20_000_000,
    canceled=None,
):
    """Known-error GLS density contrasts, fixed geometry, optional constant offset.

    Signed contrasts are unconstrained. Formal covariance conditions on exact
    body geometry and independent absolute measurement errors, without residual
    rescaling. Rank deficiency is rejected instead of returning arbitrary masses.
    """
    integer_budget(max_elements, "max_elements")
    if type(fit_offset) is not bool:
        raise ValueError("fit_offset must be boolean")
    obs = as_array(observation_xz_m, float)
    values, std = as_array(observed_mgal, float), as_array(reading_std_mgal, float)
    if (
        obs.ndim != 2
        or obs.shape[1] != 2
        or values.shape != (len(obs),)
        or std.shape != values.shape
        or not np.isfinite(values).all()
        or not np.isfinite(std).all()
        or np.any(std <= 0)
    ):
        raise ValueError(
            "Aligned observations and positive finite mGal errors required"
        )
    n_body = len(polygons_xz_m)
    parameters = n_body + int(fit_offset)
    if (
        not 1 <= n_body <= 128
        or len(obs) < parameters
        or len(obs) * parameters + parameters**2 > max_elements
    ):
        raise ValueError("Polygon density fit shape/element budget exceeded")
    # Budget is global over all response columns, not reset per body.
    if len(obs) * sum(len(p) for p in polygons_xz_m) > max_interactions:
        raise ValueError("Polygon interaction budget exceeded")
    columns = []
    for polygon in polygons_xz_m:
        columns.append(
            polygon_gravity_2d(
                obs,
                [polygon],
                [1.0],
                max_interactions=max_interactions,
                canceled=canceled,
            )["gravity_mgal"]
        )
    if fit_offset:
        columns.append(np.ones(len(obs)))
    design = np.column_stack(columns)
    coefficients, covariance, diagnostics = gaussian_calibration(
        design[:, None, :],
        values[:, None],
        std[:, None, None] ** 2,
        maximum_condition=maximum_condition,
    )
    predicted = design @ coefficients
    return dict(
        density_kg_m3=coefficients[:n_body],
        density_covariance=covariance[:n_body, :n_body],
        offset_mgal=float(coefficients[-1]) if fit_offset else 0.0,
        parameter_covariance=covariance,
        predicted_mgal=predicted,
        residual_mgal=values - predicted,
        parameter_order=[f"density_{i}_kg_m3" for i in range(n_body)]
        + (["offset_mgal"] if fit_offset else []),
        **diagnostics,
        uncertainty_note="Fixed geometry and absolute independent reading errors; no geometric uncertainty or geological uniqueness",
    )

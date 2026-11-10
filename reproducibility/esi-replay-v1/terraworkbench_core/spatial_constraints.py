"""Explicit geological support/depth constraints, never inferred from anomalies."""

import numpy as np

from ._array_contract import as_array
from ._calibration import integer_budget


def spatial_property_constraints(
    cell_centers_enu_m,
    *,
    lower,
    upper,
    background_value,
    support_prisms_m=None,
    depth_limits_m=None,
    surface_elevation_m=None,
    mode="hard",
    outside_weight=1.0,
    max_cells=1_000_000,
):
    """Per-cell property bounds and multiplicative prior weights from stated support.

    Hard mode fixes outside cells to an explicit background. Soft mode retains
    property limits everywhere and increases regularization weights outside.
    Support is a union of boxes intersected with the optional depth interval;
    membership uses cell CENTERS, not clipped cell volumes. Depth is supplied
    surface elevation minus upward cell z. Surface may be scalar or per cell.
    Bounds/weights are user priors, not probabilities or data-derived geology.
    For Cartesian MVI the scalar limits apply to EACH vector component when
    supplied as per-cell bounds; they are not amplitude or direction cones.
    """
    integer_budget(max_cells, "max_cells")
    xyz = as_array(cell_centers_enu_m, float)
    if (
        xyz.ndim != 2
        or xyz.shape[1] != 3
        or not 1 <= len(xyz) <= max_cells
        or not np.isfinite(xyz).all()
    ):
        raise ValueError("Finite nonempty ENU cell centers within cell budget required")
    if (
        not np.isfinite([lower, upper, background_value, outside_weight]).all()
        or lower >= upper
        or outside_weight < 1
    ):
        raise ValueError(
            "Finite ordered scalar limits/background and outside_weight >=1 required"
        )
    if (
        mode not in ("hard", "soft")
        or (mode == "hard" and outside_weight != 1)
        or (mode == "soft" and outside_weight <= 1)
    ):
        raise ValueError(
            "Hard mode uses weight 1; soft mode requires outside_weight >1"
        )
    if support_prisms_m is None and depth_limits_m is None:
        raise ValueError("Supply an explicit geological support or depth interval")
    support = np.ones(len(xyz), bool)
    if support_prisms_m is not None:
        boxes = as_array(support_prisms_m, float)
        if (
            boxes.ndim != 2
            or boxes.shape[1] != 6
            or not 1 <= len(boxes) <= 128
            or not np.isfinite(boxes).all()
            or np.any(boxes[:, ::2] >= boxes[:, 1::2])
        ):
            raise ValueError(
                "Supply 1..128 ordered finite west/east/south/north/bottom/top boxes"
            )
        support[:] = False
        for box in boxes:
            support |= np.all((xyz >= box[::2]) & (xyz <= box[1::2]), axis=1)
    if depth_limits_m is not None:
        interval = as_array(depth_limits_m, float)
        surface = as_array(surface_elevation_m, float)
        if (
            interval.shape != (2,)
            or not np.isfinite(interval).all()
            or interval[0] < 0
            or interval[0] >= interval[1]
            or surface.shape not in ((), (len(xyz),))
            or not np.isfinite(surface).all()
        ):
            raise ValueError(
                "Ordered nonnegative depth limits and explicit finite surface elevation required"
            )
        depth = surface - xyz[:, 2]
        support &= (depth >= interval[0]) & (depth <= interval[1])
    elif surface_elevation_m is not None:
        raise ValueError("Surface elevation applies only with depth_limits_m")
    if not support.any():
        raise ValueError("No cell centers lie in the stated geological support")
    lo, hi = np.full(len(xyz), float(lower)), np.full(len(xyz), float(upper))
    weights = np.ones(len(xyz))
    if mode == "hard":
        lo[~support] = hi[~support] = background_value
    else:
        weights[~support] = outside_weight
    return dict(
        lower=lo,
        upper=hi,
        cell_weights=weights,
        support_mask=support,
        supported_cells=int(support.sum()),
        fixed_cells=int((lo == hi).sum()),
        recipe=dict(
            mode=mode,
            membership="cell centers; no cell-volume clipping",
            coordinates="ENU projected metres, upward z",
            depth="explicit surface minus cell z",
            prior_scope="Caller-supplied geological hypothesis; not inferred or certified from data",
        ),
    )

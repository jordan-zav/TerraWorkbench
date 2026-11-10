"""Optional SimPEG DC sounding forward/inverse on horizontal 1D layers.

Input resistivity ohm m, thickness m, coordinates m. ABMN polarity and remote
electrodes follow electrical.py. Not an ERT 2.5D/3D or topographic inversion.
"""

import numpy as np
from scipy.optimize import least_squares

from ._array_contract import as_array
from .electrical import geometric_factor, validate_abmn


def dc_layered(electrodes, abmn, resistivity_ohm_m, thicknesses_m):
    """Unit-current transfer resistance and apparent resistivity for ABMN.

    Source current is exactly 1 A; output transfer resistance is ohms, not a
    measured voltage unless current is 1 A. A common electrode plane is used
    as the Earth surface. The last layer is a half-space.
    """
    xyz, q = validate_abmn(electrodes, abmn)
    rho, thickness = as_array(resistivity_ohm_m, float), as_array(thicknesses_m, float)
    if (
        rho.ndim != 1
        or not 1 <= len(rho) <= 128
        or thickness.shape != (len(rho) - 1,)
        or not np.isfinite(rho).all()
        or not np.isfinite(thickness).all()
        or np.any(rho <= 0)
        or np.any(thickness <= 0)
        or len(q) > 2048
    ):
        raise ValueError(
            "Require 1..128 positive resistivities, n-1 thicknesses and at most 2048 quadrupoles"
        )
    factor = geometric_factor(xyz, q)
    try:
        import simpeg
        from simpeg.electromagnetics.static import resistivity as dc
    except ImportError as error:
        raise ImportError(
            "DC sounding requires terraworkbench-core[electrical] on Python >=3.11"
        ) from error
    if not simpeg.__version__.startswith("0.25."):
        raise RuntimeError("DC sounding requires the declared SimPEG 0.25.x API")
    xyz[:, 2] -= xyz[q[0, 0], 2]
    sources = []
    for a, b, m, n in q:
        if n == -1:
            receiver = dc.receivers.Pole(xyz[m][None, :], data_type="volt")
        else:
            receiver = dc.receivers.Dipole(
                xyz[m][None, :], xyz[n][None, :], data_type="volt"
            )
        if b == -1:
            source = dc.sources.Pole([receiver], location=xyz[a], current=1.0)
        else:
            source = dc.sources.Dipole(
                [receiver], location_a=xyz[a], location_b=xyz[b], current=1.0
            )
        sources.append(source)
    # SimPEG 0.25's logarithmic quintic Hankel spline has only four knots
    # when every electrode offset is identical (e.g. a single pole-pole
    # reading). Add an unobserved computational offset to span enough knots;
    # discard its prediction. This does not create or fit an observed datum.
    offsets = []
    for i, j in ((0, 2), (1, 2), (0, 3), (1, 3)):
        real = (q[:, i] >= 0) & (q[:, j] >= 0)
        offsets.extend(np.linalg.norm(xyz[q[real, i]] - xyz[q[real, j]], axis=1))
    offset_min, offset_max = min(offsets), max(offsets)
    numerical_guard = offset_max / offset_min < 2
    if numerical_guard:
        origin = xyz[q[0, 0]]
        guard_receiver = dc.receivers.Pole(
            (origin + [2 * offset_min, 0.0, 0.0])[None, :], data_type="volt"
        )
        sources.append(dc.sources.Pole([guard_receiver], location=origin, current=1.0))
    simulation = dc.Simulation1DLayers(
        survey=dc.Survey(sources), rho=rho, thicknesses=thickness
    )
    resistance = as_array(simulation.dpred(None))[: len(q)]
    if not np.isfinite(resistance).all():
        raise RuntimeError("DC backend returned nonfinite resistance")
    return {
        "resistance_ohm": resistance,
        "rho_a_ohm_m": factor * resistance,
        "resistivity_ohm_m": rho.copy(),
        "thicknesses_m": thickness.copy(),
        "geometric_factor_m": factor,
        "earth_dimension": "1D",
        "engine": "SimPEG",
        "engine_version": simpeg.__version__,
        "source_current_a": 1.0,
        "hankel_auxiliary_offset": numerical_guard,
    }


def fit_dc_resistivity(
    electrodes,
    abmn,
    observed_resistance_ohm,
    *,
    resistance_std_ohm,
    initial_resistivity_ohm_m,
    thicknesses_m,
    bounds_ohm_m=(0.01, 1e7),
    max_evaluations=100,
    cancel=None,
):
    """Local WLS resistivity fitting with fixed layer thicknesses and ABMN.

    Signed resistance is fitted in original units with explicit errors. Layer
    equivalence/DOI are not resolved automatically; no topographic corrections.
    """
    _, q = validate_abmn(electrodes, abmn)
    obs, std, rho, bounds = [
        as_array(v, float)
        for v in (
            observed_resistance_ohm,
            resistance_std_ohm,
            initial_resistivity_ohm_m,
            bounds_ohm_m,
        )
    ]
    if (
        obs.shape != (len(q),)
        or std.shape != obs.shape
        or rho.ndim != 1
        or not 1 <= rho.size <= len(q)
        or bounds.shape != (2,)
        or not all(np.isfinite(v).all() for v in (obs, std, rho, bounds))
        or np.any(std <= 0)
        or not 0 < bounds[0] < bounds[1]
        or np.any(rho <= bounds[0])
        or np.any(rho >= bounds[1])
    ):
        raise ValueError(
            "Invalid matching DC observations/errors, initial model or bounds"
        )
    if (
        isinstance(max_evaluations, bool)
        or not isinstance(max_evaluations, int)
        or not 1 <= max_evaluations <= 1000
    ):
        raise ValueError("max_evaluations must be integer in 1..1000")

    def residual(model):
        if cancel is not None and cancel():
            raise InterruptedError("DC sounding fit cancelled")
        prediction = dc_layered(electrodes, abmn, np.exp(model), thicknesses_m)
        return (prediction["resistance_ohm"] - obs) / std

    fit = least_squares(
        residual, np.log(rho), bounds=np.log(bounds), max_nfev=max_evaluations
    )
    return {
        "resistivity_ohm_m": np.exp(fit.x),
        "success": bool(fit.success),
        "message": fit.message,
        "evaluations": fit.nfev,
        "chi_squared": float(fit.fun @ fit.fun),
        "log_resistivity_jacobian": fit.jac,
        "active_bounds": fit.active_mask,
        "parameterization": "log resistivity, fixed thickness",
    }

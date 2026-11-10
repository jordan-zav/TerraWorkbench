"""MT response primitives with explicit units and exp(+i omega t) convention.

Impedance Z=E/H in ohms, frequency Hz, earth resistivity ohm m, layers m.
This module is not an EDI/MTH5 reader or a robust time-series TF estimator.
Horizontal coordinates for tensors are north/east, not grid east/north.
"""

import numpy as np
from scipy.constants import mu_0
from scipy.optimize import least_squares

from ._array_contract import as_array


def _frequencies(frequency_hz):
    f = as_array(frequency_hz, float)
    if (
        f.ndim != 1
        or not 1 <= f.size <= 10000
        or not np.isfinite(f).all()
        or np.any(f <= 0)
    ):
        raise ValueError("Finite positive frequency vector required, maximum 10000")
    return f


def layered_impedance(frequency_hz, resistivity_ohm_m, thicknesses_m):
    """Stable tanh recursion for a horizontally layered isotropic Earth.

    Displacement current neglected; permeability mu0, no magnetic layers/IP.
    Returns the positive xy impedance. For a 1D tensor Zyx=-Zxy.
    """
    f = _frequencies(frequency_hz)
    rho, thickness = as_array(resistivity_ohm_m, float), as_array(thicknesses_m, float)
    if (
        rho.ndim != 1
        or not 1 <= rho.size <= 512
        or thickness.shape != (rho.size - 1,)
        or not np.isfinite(rho).all()
        or not np.isfinite(thickness).all()
        or np.any(rho <= 0)
        or np.any(thickness <= 0)
    ):
        raise ValueError("Positive resistivities and n-1 positive thicknesses required")
    iwmu = 2j * np.pi * f * mu_0
    impedance = np.sqrt(iwmu * rho[-1])
    for resistivity, h in zip(rho[-2::-1], thickness[::-1]):
        eta = np.sqrt(iwmu * resistivity)
        optical = np.sqrt(iwmu / resistivity) * h
        # exp(-2q h) vanishes for deep/thick conductive layers. Evaluate the
        # asymptotic tanh=1 rather than overflowing complex hyperbolic terms.
        attenuation = np.ones(optical.shape, complex)
        finite_depth = optical.real < 20
        attenuation[finite_depth] = np.tanh(optical[finite_depth])
        impedance = (
            eta * (impedance + eta * attenuation) / (eta + impedance * attenuation)
        )
    return {
        "impedance_ohm": impedance,
        "frequency_hz": f.copy(),
        "time_convention": "exp(+i omega t)",
        "earth_dimension": "1D",
        "resistivity_ohm_m": rho.copy(),
        "thicknesses_m": thickness.copy(),
    }


def apparent_resistivity_phase(frequency_hz, impedance_ohm):
    """rho_a=|E/H|^2/(mu0*omega); phase in [-180,180] degrees, not folded.

    Supports (frequency,) components or (frequency,2,2) tensors. In a 1D
    passive Earth xy is +45 and yx is -135 degrees for a uniform half-space.
    Zero impedance has undefined phase, represented by NaN.
    """
    f = _frequencies(frequency_hz)
    z = as_array(impedance_ohm, complex)
    if z.shape not in ((f.size,), (f.size, 2, 2)) or not np.isfinite(z).all():
        raise ValueError("Impedance must be finite components or 2x2 tensors in ohms")
    omega = (2 * np.pi * f).reshape((f.size,) + (1,) * (z.ndim - 1))
    rho = abs(z) ** 2 / (omega * mu_0)
    phase = np.where(abs(z) > 0, np.angle(z, deg=True), np.nan)
    return {"rho_a_ohm_m": rho, "phase_deg": phase}


def mt_units_to_ohms(impedance_mv_km_nt):
    """Convert the common (mV/km)/nT E/B units to E/H ohms in free space."""
    z = as_array(impedance_mv_km_nt, complex)
    if not np.isfinite(z).all():
        raise ValueError("Finite impedance required")
    return z * (1000 * mu_0)


def phase_tensor(impedance_ohm, *, maximum_condition=1e8):
    """Phi=Re(Z)^-1 Im(Z); reject singular real parts, never pseudoinvert.

    A real, nonsingular left-side galvanic distortion cancels. This does not
    recover amplitude or remove static shift from apparent resistivity.
    """
    z = as_array(impedance_ohm, complex)
    if z.ndim < 2 or z.shape[-2:] != (2, 2) or not np.isfinite(z).all():
        raise ValueError("Finite (...,2,2) impedance required")
    if not np.isfinite(maximum_condition) or maximum_condition < 1:
        raise ValueError("maximum_condition must be finite and at least one")
    condition = np.linalg.cond(z.real)
    if np.any(condition > maximum_condition) or not np.isfinite(condition).all():
        raise ValueError(
            "Ill-conditioned real impedance; phase tensor not identifiable"
        )
    return {
        "phase_tensor": np.linalg.solve(z.real, z.imag),
        "real_condition": condition,
    }


def fit_layered_resistivity(
    frequency_hz,
    impedance_ohm,
    *,
    real_std_ohm,
    imag_std_ohm,
    initial_resistivity_ohm_m,
    thicknesses_m,
    bounds_ohm_m=(0.01, 1e7),
    max_evaluations=100,
    cancel=None,
):
    """Local bounded log-resistivity fit with fixed thicknesses and geometry.

    No automatic layer selection or posterior uniqueness claim. Real/imaginary
    errors are explicit and independent in this fit, not a full covariance.
    """
    f = _frequencies(frequency_hz)
    obs = as_array(impedance_ohm, complex)
    re, im = as_array(real_std_ohm, float), as_array(imag_std_ohm, float)
    rho, bounds = (
        as_array(initial_resistivity_ohm_m, float),
        as_array(bounds_ohm_m, float),
    )
    if (
        obs.shape != f.shape
        or re.shape != f.shape
        or im.shape != f.shape
        or not all(np.isfinite(a).all() for a in (obs, re, im, rho, bounds))
        or np.any(re <= 0)
        or np.any(im <= 0)
        or rho.ndim != 1
        or not len(rho)
        or len(rho) > 2 * len(f)
        or bounds.shape != (2,)
        or not 0 < bounds[0] < bounds[1]
        or np.any(rho <= bounds[0])
        or np.any(rho >= bounds[1])
    ):
        raise ValueError("Invalid data/errors, initial resistivities or bounds")
    if (
        isinstance(max_evaluations, bool)
        or not isinstance(max_evaluations, int)
        or not 1 <= max_evaluations <= 1000
    ):
        raise ValueError("max_evaluations must be integer in 1..1000")

    def residual(model):
        if cancel is not None and cancel():
            raise InterruptedError("MT fitting cancelled")
        prediction = layered_impedance(f, np.exp(model), thicknesses_m)["impedance_ohm"]
        return np.r_[
            (prediction.real - obs.real) / re, (prediction.imag - obs.imag) / im
        ]

    fit = least_squares(
        residual, np.log(rho), bounds=np.log(bounds), max_nfev=max_evaluations
    )
    return {
        "resistivity_ohm_m": np.exp(fit.x),
        "success": bool(fit.success),
        "message": fit.message,
        "chi_squared": float(fit.fun @ fit.fun),
        "evaluations": fit.nfev,
        "active_bounds": fit.active_mask,
        "log_resistivity_jacobian": fit.jac,
        "parameterization": "log resistivity, fixed thickness",
    }

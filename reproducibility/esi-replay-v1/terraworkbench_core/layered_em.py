"""Optional SimPEG layered-earth EM forward models and bounded FDEM fitting.

Horizontal, isotropic layers with nonmagnetic permeability, no IP. Coordinates
are east/north/up in metres, ground at z=0. Conductivity S/m, thickness m,
dipole moment A*m^2. No QGIS; SimPEG imported only when an operation runs.
These are 1D earth responses, not 3D heterogeneous-earth simulations.
"""

import numpy as np
from scipy.constants import mu_0
from scipy.optimize import least_squares

from ._array_contract import as_array


def _model(conductivity, thicknesses, source, receiver, moment):
    sigma, h = as_array(conductivity, float), as_array(thicknesses, float)
    tx, rx = as_array(source, float), as_array(receiver, float)
    if (
        sigma.ndim != 1
        or len(sigma) < 1
        or len(sigma) > 256
        or h.shape != (len(sigma) - 1,)
        or not np.isfinite(sigma).all()
        or np.any(sigma <= 0)
        or not np.isfinite(h).all()
        or np.any(h <= 0)
    ):
        raise ValueError(
            "Require 1..256 positive layer conductivities and n-1 positive thicknesses"
        )
    if (
        tx.shape != (3,)
        or rx.shape != (3,)
        or not np.isfinite(tx).all()
        or not np.isfinite(rx).all()
        or min(tx[2], rx[2]) < 0
    ):
        raise ValueError("Finite source/receiver above ground z=0 required")
    if np.linalg.norm(tx[:2] - rx[:2]) <= 0:
        raise ValueError(
            "A nonzero horizontal offset is required by this layered adapter"
        )
    if not np.isfinite(moment) or moment <= 0:
        raise ValueError("Dipole moment must be positive A m^2")
    return sigma, h, tx, rx


def _engines():
    try:
        import simpeg
        from simpeg.electromagnetics import frequency_domain, time_domain
    except ImportError as error:
        raise ImportError(
            "Layered EM requires terraworkbench-core[em] on Python >=3.11"
        ) from error
    if not simpeg.__version__.startswith("0.25."):
        raise RuntimeError("Layered EM adapter requires the declared SimPEG 0.25.x API")
    return frequency_domain, time_domain, simpeg.__version__


def fdem_layered(
    frequency_hz,
    conductivity_s_m,
    thicknesses_m,
    *,
    source_m,
    receiver_m,
    moment_a_m2=1.0,
    source_axis="z",
    receiver_axis="z",
):
    """Complex SECONDARY magnetic flux density (tesla), ordered by input f.

    Real/imaginary quadrature follows SimPEG's native frequency convention;
    no ppm normalization, primary-field subtraction or phase rotation inferred.
    """
    sigma, h, tx, rx = _model(
        conductivity_s_m, thicknesses_m, source_m, receiver_m, moment_a_m2
    )
    f = as_array(frequency_hz, float)
    if (
        f.ndim != 1
        or not 1 <= len(f) <= 512
        or not np.isfinite(f).all()
        or np.any(f <= 0)
    ):
        raise ValueError("Require 1..512 finite positive frequencies in Hz")
    if source_axis not in ("x", "y", "z") or receiver_axis not in ("x", "y", "z"):
        raise ValueError("Dipole/receiver axis must be x, y or z")
    fd, _, version = _engines()
    sources = []
    for frequency in f:
        # The 0.25 layered projection computes H; flux-density receiver names
        # do not apply mu0 there. Request H explicitly and convert in air.
        receivers = [
            fd.receivers.PointMagneticFieldSecondary(
                rx[None, :], orientation=receiver_axis, component=part
            )
            for part in ("real", "imag")
        ]
        sources.append(
            fd.sources.MagDipole(
                receivers,
                frequency=float(frequency),
                location=tx,
                orientation=source_axis,
                moment=moment_a_m2,
            )
        )
    simulation = fd.Simulation1DLayered(
        survey=fd.Survey(sources), sigma=sigma, thicknesses=h
    )
    raw = as_array(simulation.dpred(None)).reshape(len(f), 2)
    result = mu_0 * (raw[:, 0] + 1j * raw[:, 1])
    if not np.isfinite(result).all():
        raise RuntimeError("Layered EM backend returned nonfinite fields")
    return {
        "secondary_b_t": result,
        "frequency_hz": f.copy(),
        "conductivity_s_m": sigma.copy(),
        "thicknesses_m": h.copy(),
        "engine": "SimPEG",
        "engine_version": version,
        "earth_dimension": "1D",
        "source_m": tx,
        "receiver_m": rx,
        "source_axis": source_axis,
        "receiver_axis": receiver_axis,
        "moment_a_m2": moment_a_m2,
    }


def tem_stepoff_layered(
    times_s,
    conductivity_s_m,
    thicknesses_m,
    *,
    source_m,
    receiver_m,
    moment_a_m2=1.0,
    source_axis="z",
    receiver_axis="z",
):
    """Point-time dB/dt (T/s) following an ideal magnetic-dipole step-off at 0.

    The source is on from minus infinity. This does not approximate a finite
    ramp, arbitrary waveform, finite loop or instrument receiver convolution.
    """
    sigma, h, tx, rx = _model(
        conductivity_s_m, thicknesses_m, source_m, receiver_m, moment_a_m2
    )
    t = as_array(times_s, float)
    if (
        t.ndim != 1
        or not 1 <= len(t) <= 2048
        or not np.isfinite(t).all()
        or np.any(t <= 0)
        or np.any(np.diff(t) <= 0)
    ):
        raise ValueError("Require increasing positive point times after turn-off")
    if source_axis not in ("x", "y", "z") or receiver_axis not in ("x", "y", "z"):
        raise ValueError("Dipole/receiver axis must be x, y or z")
    _, td, version = _engines()
    receiver = td.receivers.PointMagneticFluxTimeDerivative(
        rx[None, :], times=t, orientation=receiver_axis
    )
    source = td.sources.MagDipole(
        [receiver],
        location=tx,
        orientation=source_axis,
        moment=moment_a_m2,
        waveform=td.sources.StepOffWaveform(),
    )
    simulation = td.Simulation1DLayered(
        survey=td.Survey([source]), sigma=sigma, thicknesses=h
    )
    result = as_array(simulation.dpred(None))
    if not np.isfinite(result).all():
        raise RuntimeError("Layered EM backend returned nonfinite fields")
    return {
        "dbdt_t_s": result,
        "times_s": t.copy(),
        "engine": "SimPEG",
        "engine_version": version,
        "earth_dimension": "1D",
        "waveform": "ideal step-off at t=0",
        "conductivity_s_m": sigma.copy(),
        "thicknesses_m": h.copy(),
        "source_m": tx,
        "receiver_m": rx,
        "source_axis": source_axis,
        "receiver_axis": receiver_axis,
        "moment_a_m2": moment_a_m2,
    }


def tem_gate_average(
    gates_s,
    conductivity_s_m,
    thicknesses_m,
    *,
    quadrature_order=6,
    waveform_times_s=None,
    relative_current=None,
    **geometry,
):
    """Boxcar time average of dB/dt by Gauss-Legendre quadrature.

    Gates may overlap but must start after 0. Integration accuracy must be
    checked by increasing quadrature order for wide gates/fast transients.
    Default is ideal step-off. Both waveform arrays select a finite piecewise
    linear waveform instead; see tem_waveform_layered for their conventions.
    """
    gates = as_array(gates_s, float)
    if (
        gates.ndim != 2
        or gates.shape[1] != 2
        or not 1 <= len(gates) <= 128
        or not np.isfinite(gates).all()
        or np.any(gates[:, 0] <= 0)
        or np.any(gates[:, 1] <= gates[:, 0])
    ):
        raise ValueError("Require 1..128 positive nonempty gates in seconds")
    if (
        isinstance(quadrature_order, bool)
        or not isinstance(quadrature_order, (int, np.integer))
        or not 2 <= quadrature_order <= 16
    ):
        raise ValueError("Quadrature order must be an integer in 2..16")
    nodes, weights = np.polynomial.legendre.leggauss(quadrature_order)
    times = gates.mean(axis=1)[:, None] + np.diff(gates, axis=1) * nodes / 2
    unique, inverse = np.unique(times, return_inverse=True)
    if waveform_times_s is None and relative_current is None:
        prediction = tem_stepoff_layered(
            unique, conductivity_s_m, thicknesses_m, **geometry
        )
    elif waveform_times_s is not None and relative_current is not None:
        prediction = tem_waveform_layered(
            unique,
            conductivity_s_m,
            thicknesses_m,
            waveform_times_s=waveform_times_s,
            relative_current=relative_current,
            **geometry,
        )
    else:
        raise ValueError("Both waveform_times_s and relative_current are required")
    samples = prediction["dbdt_t_s"][inverse].reshape(times.shape)
    return {
        "gate_dbdt_t_s": samples @ weights / 2,
        "gates_s": gates.copy(),
        "quadrature_order": quadrature_order,
        "engine": prediction["engine"],
        "engine_version": prediction["engine_version"],
        "waveform": prediction["waveform"],
        "averaging": "boxcar",
    }


def tem_waveform_layered(
    times_s,
    conductivity_s_m,
    thicknesses_m,
    *,
    waveform_times_s,
    relative_current,
    source_m,
    receiver_m,
    moment_a_m2=1.0,
    source_axis="z",
    receiver_axis="z",
):
    """dB/dt T/s for an explicit normalized piecewise-linear dipole waveform.

    Waveform knots increase strictly, end at t=0 with current=0 and precede
    all positive observation times. Relative currents lie in [-1,1] and
    multiply moment_a_m2 (peak dipole moment, NOT current in amperes).
    Current before the first knot remains at its first value; use initial
    zero plus a turn-on ramp to model a finite pulse, not infinite on-time.
    No receiver response, finite loop or automatically repeated pulses.
    """
    sigma, h, tx, rx = _model(
        conductivity_s_m, thicknesses_m, source_m, receiver_m, moment_a_m2
    )
    times = as_array(times_s, float)
    knots, current = (
        as_array(waveform_times_s, float),
        as_array(relative_current, float),
    )
    if (
        times.ndim != 1
        or not 1 <= len(times) <= 2048
        or not np.isfinite(times).all()
        or np.any(times <= 0)
        or np.any(np.diff(times) <= 0)
    ):
        raise ValueError("Require increasing positive observation times after turn-off")
    if (
        knots.ndim != 1
        or not 2 <= knots.size <= 128
        or current.shape != knots.shape
        or not np.isfinite(knots).all()
        or not np.isfinite(current).all()
        or np.any(np.diff(knots) <= 0)
        or knots[-1] != 0
        or current[-1] != 0
        or np.any(abs(current) > 1)
        or not np.any(current != 0)
    ):
        raise ValueError(
            "Require 2..128 increasing waveform knots ending at (0,0), relative currents within [-1,1]"
        )
    if source_axis not in ("x", "y", "z") or receiver_axis not in ("x", "y", "z"):
        raise ValueError("Dipole/receiver axis must be x, y or z")
    _, td, version = _engines()
    receiver = td.receivers.PointMagneticFluxTimeDerivative(
        rx[None, :], times=times, orientation=receiver_axis
    )
    waveform = td.sources.PiecewiseLinearWaveform(
        times=knots, currents=current, off_time=0.0
    )
    source = td.sources.MagDipole(
        [receiver],
        location=tx,
        orientation=source_axis,
        moment=moment_a_m2,
        waveform=waveform,
    )
    simulation = td.Simulation1DLayered(
        survey=td.Survey([source]), sigma=sigma, thicknesses=h
    )
    result = as_array(simulation.dpred(None))
    if not np.isfinite(result).all():
        raise RuntimeError("Layered waveform TEM backend returned nonfinite fields")
    return {
        "dbdt_t_s": result,
        "times_s": times.copy(),
        "waveform_times_s": knots.copy(),
        "relative_current": current.copy(),
        "initial_relative_current": float(current[0]),
        "waveform": "normalized piecewise linear; final turn-off at t=0",
        "engine": "SimPEG",
        "engine_version": version,
        "earth_dimension": "1D",
        "conductivity_s_m": sigma.copy(),
        "thicknesses_m": h.copy(),
        "source_m": tx,
        "receiver_m": rx,
        "source_axis": source_axis,
        "receiver_axis": receiver_axis,
        "moment_a_m2": moment_a_m2,
    }


def fit_tem_conductivity(
    observed_dbdt_t_s,
    *,
    data_std_t_s,
    initial_conductivity_s_m,
    thicknesses_m,
    times_s=None,
    gates_s=None,
    waveform_times_s=None,
    relative_current=None,
    quadrature_order=6,
    bounds_s_m=(1e-6, 10.0),
    max_evaluations=60,
    max_forward_evaluations=300,
    cancel=None,
    **geometry,
):
    """Bounded log-conductivity fit of signed point-time OR gate TEM data.

    Fixed layer thicknesses/geometry/waveform, independent explicit errors,
    no regularizer or automatic DOI. Supply exactly one of times_s/gates_s.
    Forward-call budget counts finite-difference Jacobian calls too. A hard
    budget violation raises RuntimeError; optimizer limit returns success=False.
    This is local 1D fitting, not spatially constrained or 3D inversion.
    """
    obs, std, initial, bounds = [
        as_array(a, float)
        for a in (observed_dbdt_t_s, data_std_t_s, initial_conductivity_s_m, bounds_s_m)
    ]
    if (times_s is None) == (gates_s is None):
        raise ValueError("Specify exactly one of point times_s or finite gates_s")
    if (waveform_times_s is None) != (relative_current is None):
        raise ValueError("Both waveform arrays are required")
    if (
        obs.ndim != 1
        or not len(obs)
        or std.shape != obs.shape
        or initial.ndim != 1
        or not 1 <= len(initial) <= min(len(obs), 256)
        or bounds.shape != (2,)
        or not all(np.isfinite(a).all() for a in (obs, std, initial, bounds))
        or np.any(std <= 0)
        or not 0 < bounds[0] < bounds[1]
        or np.any(initial <= bounds[0])
        or np.any(initial >= bounds[1])
    ):
        raise ValueError("Invalid TEM data/errors, initial conductivities or bounds")
    sample_axis = as_array(times_s if times_s is not None else gates_s, float)
    if (times_s is not None and sample_axis.shape != obs.shape) or (
        gates_s is not None and sample_axis.shape != (len(obs), 2)
    ):
        raise ValueError("Observation count must match point times or gate rows")
    for name, limit, maximum in (
        ("max_evaluations", max_evaluations, 1000),
        ("max_forward_evaluations", max_forward_evaluations, 10000),
    ):
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, np.integer))
            or not 1 <= limit <= maximum
        ):
            raise ValueError(name + " must be an explicit positive bounded integer")
    calls = 0
    engine_version = None

    def residual(log_sigma):
        nonlocal calls, engine_version
        if cancel is not None and cancel():
            raise InterruptedError("TEM fitting cancelled")
        if calls >= max_forward_evaluations:
            raise RuntimeError("TEM forward-call budget exceeded")
        calls += 1
        sigma = np.exp(log_sigma)
        if gates_s is not None:
            prediction = tem_gate_average(
                sample_axis,
                sigma,
                thicknesses_m,
                quadrature_order=quadrature_order,
                waveform_times_s=waveform_times_s,
                relative_current=relative_current,
                **geometry,
            )
            value = prediction["gate_dbdt_t_s"]
        elif waveform_times_s is not None:
            prediction = tem_waveform_layered(
                sample_axis,
                sigma,
                thicknesses_m,
                waveform_times_s=waveform_times_s,
                relative_current=relative_current,
                **geometry,
            )
            value = prediction["dbdt_t_s"]
        else:
            prediction = tem_stepoff_layered(
                sample_axis, sigma, thicknesses_m, **geometry
            )
            value = prediction["dbdt_t_s"]
        engine_version = prediction["engine_version"]
        return (value - obs) / std

    fit = least_squares(
        residual, np.log(initial), bounds=np.log(bounds), max_nfev=max_evaluations
    )
    singular = np.linalg.svd(fit.jac, compute_uv=False)
    rank = np.linalg.matrix_rank(fit.jac)
    return {
        "conductivity_s_m": np.exp(fit.x),
        "success": bool(fit.success),
        "message": fit.message,
        "evaluations": fit.nfev,
        "forward_evaluations": calls,
        "chi_squared": float(fit.fun @ fit.fun),
        "predicted_dbdt_t_s": obs + fit.fun * std,
        "weighted_residual": fit.fun,
        "log_conductivity_jacobian": fit.jac,
        "jacobian_singular_values": singular,
        "locally_full_rank": bool(rank == len(initial)),
        "active_bounds": fit.active_mask,
        "engine": "SimPEG",
        "engine_version": engine_version,
        "earth_dimension": "1D",
        "data_sampling": "gates" if gates_s is not None else "points",
        "parameterization": "log conductivity; fixed thickness, geometry and waveform",
    }


def fit_fdem_conductivity(
    frequency_hz,
    observed_secondary_b_t,
    *,
    real_std_t,
    imag_std_t,
    initial_conductivity_s_m,
    thicknesses_m,
    bounds_s_m=(1e-6, 10.0),
    max_evaluations=60,
    cancel=None,
    **geometry,
):
    """Bounded log-conductivity fit, fixed known layers/geometry, no regularizer.

    Errors for real/imag data must be positive and externally supplied. This
    local least-squares fit is not unique geological inversion, LCI or 3D EM.
    Success and termination are explicit; evaluation limit is not success.
    """
    obs = as_array(observed_secondary_b_t, complex)
    f = as_array(frequency_hz, float)
    initial = as_array(initial_conductivity_s_m, float)
    re, im = as_array(real_std_t, float), as_array(imag_std_t, float)
    bounds = as_array(bounds_s_m, float)
    if (
        obs.shape != f.shape
        or obs.ndim != 1
        or re.shape != obs.shape
        or im.shape != obs.shape
        or not all(np.isfinite(a).all() for a in (obs, re, im, initial, bounds))
        or np.any(re <= 0)
        or np.any(im <= 0)
        or initial.ndim != 1
        or not len(initial)
        or bounds.shape != (2,)
        or not 0 < bounds[0] < bounds[1]
        or np.any(initial <= bounds[0])
        or np.any(initial >= bounds[1])
        or initial.size > 2 * obs.size
    ):
        raise ValueError(
            "Invalid observations/errors, initial conductivities or bounds"
        )
    if (
        isinstance(max_evaluations, bool)
        or not isinstance(max_evaluations, int)
        or not 1 <= max_evaluations <= 1000
    ):
        raise ValueError("max_evaluations must be an integer in 1..1000")

    def residual(log_sigma):
        if cancel is not None and cancel():
            raise InterruptedError("FDEM fitting cancelled")
        predicted = fdem_layered(f, np.exp(log_sigma), thicknesses_m, **geometry)[
            "secondary_b_t"
        ]
        return np.r_[(predicted.real - obs.real) / re, (predicted.imag - obs.imag) / im]

    result = least_squares(
        residual, np.log(initial), bounds=np.log(bounds), max_nfev=max_evaluations
    )
    return {
        "conductivity_s_m": np.exp(result.x),
        "success": bool(result.success),
        "message": result.message,
        "evaluations": result.nfev,
        "chi_squared": float(result.fun @ result.fun),
        "log_conductivity_jacobian": result.jac,
        "active_bounds": result.active_mask,
        "earth_dimension": "1D",
        "parameterization": "log conductivity, fixed thickness",
    }

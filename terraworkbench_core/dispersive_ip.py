"""Pelton resistivity spectra and quasi-static Cole-Cole step/pulse-off IP.

exp(+i omega t); positive chargeability gives negative imaginary resistivity.
Spatial calculations use a supplied normalized static-IP sensitivity matrix:
fixed conductivity/geometry and small-polarization linearization, not Maxwell EM.
"""

import numpy as np
from scipy.integrate import quad_vec
from scipy.optimize import least_squares

from ._array_contract import as_array
from .electrical import cole_cole_resistivity


def _parameters(m, tau, exponent):
    p = as_array([m, tau, exponent], float)
    if (
        p.shape != (3,)
        or not np.isfinite(p).all()
        or not 0 <= m < 1
        or not 1e-12 <= tau <= 1e12
        or not 0 < exponent <= 1
    ):
        raise ValueError("Require 0<=m<1, 1e-12<=tau<=1e12 seconds and 0<c<=1")
    return p


def cole_cole_decay(
    times_s=None,
    chargeability=0.1,
    tau_s=1.0,
    exponent=0.5,
    *,
    gates_s=None,
    pulse_duration_s=None,
    normalization="dc",
    cancel=None,
):
    """Normalized secondary voltage V/V at times OR rectangular mean gates.

    Infinite charged step-off by default. A finite positive on-pulse begins
    at -pulse_duration_s and switches off at zero. 'dc' uses fully charged
    primary voltage; 'pulse' uses primary immediately before that switch-off.
    Cole-Cole relaxation is Mittag-Leffler, not a stretched exponential.
    """
    m, tau, c = _parameters(chargeability, tau_s, exponent)
    if (times_s is None) == (gates_s is None):
        raise ValueError("Supply times_s OR gates_s")
    gate = gates_s is not None
    samples = as_array(gates_s if gate else times_s, float)
    if (gate and (samples.ndim != 2 or samples.shape[1] != 2)) or (
        not gate and samples.ndim != 1
    ):
        raise ValueError("Times must be a vector; gates must have shape (n,2)")
    if (
        not 1 <= len(samples) <= 4096
        or not np.isfinite(samples).all()
        or np.any(samples < 0)
        or np.any(samples > 1e12)
    ):
        raise ValueError(
            "Require 1..4096 finite nonnegative samples no greater than 1e12 seconds"
        )
    if gate and np.any(samples[:, 1] <= samples[:, 0]):
        raise ValueError("Gate ends must exceed starts")
    if pulse_duration_s is not None and (
        not np.isfinite(pulse_duration_s) or not 0 < pulse_duration_s <= 1e12
    ):
        raise ValueError("Pulse duration must be positive finite seconds <=1e12")
    if normalization not in ("dc", "pulse"):
        raise ValueError("Normalization must be dc or pulse")

    values = _relaxation_response(samples, tau, c, gate, pulse_duration_s, cancel)
    denominator = 1.0 if normalization == "dc" else 1.0 - m * values[-1]
    return m * values[:-1] / denominator


def _relaxation_response(samples, tau, c, gate, pulse_duration_s, cancel):
    """Validated unit relaxation/gate means plus charging-state relaxation.

    Shared by single-pulse and prescribed piecewise-constant current histories.
    Callers validate shape, positive tau, exponent and finite shifted times.
    """

    def check_cancel():
        if cancel is not None and cancel():
            raise InterruptedError("IP decay cancelled")

    def response(rate):
        check_cancel()
        if gate:
            width_rate = (samples[:, 1] - samples[:, 0]) * rate
            mean = np.divide(
                -np.expm1(-width_rate),
                width_rate,
                out=np.ones_like(width_rate),
                where=width_rate != 0,
            )
            values = np.exp(-samples[:, 0] * rate) * mean
        else:
            values = np.exp(-samples * rate)
        if pulse_duration_s is not None:
            values *= -np.expm1(-pulse_duration_s * rate)
        # Carry the charging-state relaxation in the same integral, so
        # measured-pulse normalization is a ratio of integrals.
        charging = 0.0 if pulse_duration_s is None else np.exp(-pulse_duration_s * rate)
        return np.r_[values, charging]

    if c == 1:
        values = response(1.0 / tau)
    else:
        # The completely monotone relaxation is an exponential mixture.
        # Its rate CDF inverse is [sin(pi*c*p)/sin(pi*c*(1-p))]**(1/c)/tau.
        def mixture(p):
            log_rate = (
                np.log(np.sin(np.pi * c * p)) - np.log(np.sin(np.pi * c * (1 - p)))
            ) / c - np.log(tau)
            return response(np.exp(np.clip(log_rate, -300.0, 300.0)))

        values, _, info = quad_vec(
            mixture, 0.0, 1.0, epsabs=2e-12, epsrel=2e-11, limit=512, full_output=True
        )
        if not info.success:
            raise RuntimeError("Cole-Cole relaxation quadrature did not converge")
    return values


def ip_decay_forward(
    times_s=None,
    chargeability=0.1,
    tau_s=1.0,
    exponent=0.5,
    *,
    gates_s=None,
    pulse_duration_s=None,
    normalization="dc",
    cancel=None,
):
    """Workflow-friendly decay with explicit V/V units and primary convention."""
    values = cole_cole_decay(
        times_s,
        chargeability,
        tau_s,
        exponent,
        gates_s=gates_s,
        pulse_duration_s=pulse_duration_s,
        normalization=normalization,
        cancel=cancel,
    )
    return {
        "decay_v_v": values,
        "normalization": normalization,
        "pulse_duration_s": pulse_duration_s,
        "units": "V/V",
        "waveform": "infinite charged step-off"
        if pulse_duration_s is None
        else "single finite on-pulse",
    }


def _noise(observed, standard_deviation, covariance):
    obs = as_array(observed)
    if not np.isfinite(obs).all():
        raise ValueError("Observations must be finite")
    if covariance is not None:
        if standard_deviation is not None or not np.iscomplexobj(obs):
            raise ValueError("Choose complex covariance OR standard deviations")
        from ._calibration import covariance_array

        factor = np.linalg.cholesky(
            covariance_array(covariance, 2, obs.size, strict=True)
        )

        def whiten(delta):
            vector = np.c_[delta.ravel().real, delta.ravel().imag]
            return np.linalg.solve(factor, vector[..., None])[..., 0].ravel()
    else:
        std = as_array(standard_deviation, float)
        if (
            std.shape not in ((), obs.shape)
            or not np.isfinite(std).all()
            or np.any(std <= 0)
        ):
            raise ValueError(
                "Positive finite errors must be scalar or match observations"
            )

        def whiten(delta):
            values = (delta / std).ravel()
            return (
                np.r_[values.real, values.imag] if np.iscomplexobj(values) else values
            )

    return obs, whiten


def _fit(
    predict,
    observed,
    initial,
    reference,
    lower,
    upper,
    log_indices,
    *,
    standard_deviation,
    covariance=None,
    beta=0.0,
    max_evaluations=100,
    max_forward_evaluations=2000,
    cancel=None,
):
    obs = as_array(observed)
    arrays = [as_array(v, float).copy() for v in (initial, reference, lower, upper)]
    start, prior, low, high = arrays
    if (
        start.ndim != 1
        or not 1 <= start.size <= 96
        or any(a.shape != start.shape or not np.isfinite(a).all() for a in arrays)
    ):
        raise ValueError(
            "Matching finite initial/reference/bound vectors with 1..96 parameters required"
        )
    if (
        np.any(low >= high)
        or np.any(start < low)
        or np.any(start > high)
        or not np.isfinite(beta)
        or beta < 0
    ):
        raise ValueError(
            "Initial values must lie within increasing bounds and beta must be nonnegative"
        )
    for limit in (max_evaluations, max_forward_evaluations):
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, np.integer))
            or not 1 <= limit <= 10000
        ):
            raise ValueError("Evaluation budgets must be integers in 1..10000")
    jacobian_elements = (
        obs.size * start.size * (2 if np.iscomplexobj(obs) else 1) + start.size**2
    )
    if jacobian_elements > 2_000_000:
        raise ValueError("IP dense Jacobian element budget exceeded")
    obs, whiten = _noise(obs, standard_deviation, covariance)
    for array in arrays:
        if np.any(array[log_indices] <= 0):
            raise ValueError(
                "Log parameters and their bounds/reference must be positive"
            )
        array[log_indices] = np.log(array[log_indices])
    calls = 0

    def unpack(values):
        physical = values.copy()
        physical[log_indices] = np.exp(physical[log_indices])
        return physical

    def evaluate(values):
        nonlocal calls
        if cancel is not None and cancel():
            raise InterruptedError("Dispersive IP inversion cancelled")
        if calls >= max_forward_evaluations:
            raise RuntimeError("Dispersive IP forward-call budget exceeded")
        calls += 1
        prediction = predict(unpack(values))
        if prediction.shape != obs.shape or not np.isfinite(prediction).all():
            raise ValueError(
                "Prediction and finite observations must have matching shapes"
            )
        return prediction

    def residual(values):
        return np.r_[whiten(evaluate(values) - obs), np.sqrt(beta) * (values - prior)]

    fitted = least_squares(
        residual,
        start,
        bounds=(low, high),
        max_nfev=max_evaluations,
        jac="3-point",
        diff_step=1e-4,
        ftol=1e-10,
        xtol=1e-10,
        gtol=1e-8,
    )
    if cancel is not None and cancel():
        raise InterruptedError("Dispersive IP inversion cancelled")
    model = unpack(fitted.x)
    # Final prediction is an explicitly counted forward evaluation too.
    prediction = evaluate(fitted.x)
    data_residual = whiten(prediction - obs)
    jac = fitted.jac[: len(data_residual)]
    singular = np.linalg.svd(jac, compute_uv=False)
    rank = (
        int(np.sum(singular > (singular[0] * max(jac.shape) * np.finfo(float).eps)))
        if singular.size
        else 0
    )
    return {
        "parameters": model,
        "predicted": prediction,
        "success": bool(fitted.success),
        "message": str(fitted.message),
        "weighted_rms": float(np.sqrt(np.mean(data_residual**2))),
        "data_chi_squared": float(data_residual @ data_residual),
        "data_rank": rank,
        "data_jacobian_singular_values": singular,
        "active_bounds": fitted.active_mask,
        "forward_evaluations": calls,
        "optimizer_evaluations": int(fitted.nfev),
        "beta": float(beta),
        "reference": as_array(reference, float).copy(),
        "parameterization": "physical parameters, specified positive parameters fitted in log space",
        "log_parameter_indices": np.asarray(log_indices, dtype=int),
        "uncertainty_note": "Local bounded fixed-model fit; rank and data fit do not establish uniqueness",
    }


def fit_cole_cole_spectrum(
    frequency_hz,
    observed_resistivity_ohm_m,
    *,
    initial,
    standard_deviation=None,
    data_covariance=None,
    reference=None,
    beta=0.0,
    lower=(1e-6, 0.0, 1e-9, 0.1),
    upper=(1e9, 0.95, 1e9, 1.0),
    **solver_options,
):
    """Fit rho0 (ohm m), m (V/V), tau_rho (s), c to complex resistivity.

    Standard deviation applies to each real/imaginary component; alternatively
    provide per-record 2x2 covariance in (ohm m)^2. No phase-sign guessing.
    """
    f = as_array(frequency_hz, float)
    obs = as_array(observed_resistivity_ohm_m, complex)
    if (
        f.ndim != 1
        or not 3 <= f.size <= 4096
        or obs.shape != f.shape
        or not np.isfinite(f).all()
        or np.any(f < 0)
    ):
        raise ValueError(
            "Require matching 3..4096 spectra and nonnegative finite frequencies"
        )
    if np.asarray(initial).shape != (4,):
        raise ValueError("Initial spectrum parameters are [rho0,m,tau_rho,c]")
    for parameters in (initial, initial if reference is None else reference):
        if np.asarray(parameters).shape != (4,):
            raise ValueError("Spectral reference must have four physical parameters")
        _parameters(*as_array(parameters, float)[1:])
    low, high = as_array(lower, float), as_array(upper, float)
    if (
        low.shape != (4,)
        or high.shape != (4,)
        or low[0] <= 0
        or low[1] < 0
        or high[1] >= 1
        or low[2] < 1e-12
        or high[2] > 1e12
        or low[3] <= 0
        or high[3] > 1
    ):
        raise ValueError("Spectral parameter bounds exceed their physical domains")
    result = _fit(
        lambda p: cole_cole_resistivity(f, *p),
        obs,
        initial,
        initial if reference is None else reference,
        low,
        high,
        [0, 2],
        standard_deviation=standard_deviation,
        covariance=data_covariance,
        beta=beta,
        **solver_options,
    )
    result.update(
        zip(
            ("rho_zero_ohm_m", "chargeability_v_v", "tau_rho_s", "exponent"),
            result["parameters"],
        )
    )
    result["phase_convention"] = "exp(+i omega t); negative imaginary resistivity"
    return result


def fit_ip_decay(
    observed_v_v,
    *,
    times_s=None,
    gates_s=None,
    initial,
    standard_deviation,
    reference=None,
    beta=0.0,
    pulse_duration_s=None,
    normalization="dc",
    lower=(0.0, 1e-9, 0.1),
    upper=(0.95, 1e9, 1.0),
    **solver_options,
):
    """Fit m, tau_rho, c to normalized step/pulse-off samples or gate means."""
    obs = as_array(observed_v_v, float)
    if obs.ndim != 1 or obs.size < 4 or np.asarray(initial).shape != (3,):
        raise ValueError(
            "Require at least four decay samples and initial [m,tau_rho,c]"
        )
    for parameters in (initial, initial if reference is None else reference):
        if np.asarray(parameters).shape != (3,):
            raise ValueError("Decay reference must have three physical parameters")
        _parameters(*as_array(parameters, float))
    low, high = as_array(lower, float), as_array(upper, float)
    if (
        low.shape != (3,)
        or high.shape != (3,)
        or low[0] < 0
        or high[0] >= 1
        or low[1] < 1e-12
        or high[1] > 1e12
        or low[2] <= 0
        or high[2] > 1
    ):
        raise ValueError("Decay parameter bounds exceed their physical domains")
    cancel = solver_options.get("cancel")

    def predict(p):
        return cole_cole_decay(
            times_s,
            *p,
            gates_s=gates_s,
            pulse_duration_s=pulse_duration_s,
            normalization=normalization,
            cancel=cancel,
        )

    result = _fit(
        predict,
        obs,
        initial,
        initial if reference is None else reference,
        low,
        high,
        [1],
        standard_deviation=standard_deviation,
        beta=beta,
        **solver_options,
    )
    result.update(
        zip(("chargeability_v_v", "tau_rho_s", "exponent"), result["parameters"])
    )
    result.update(
        normalization=normalization, pulse_duration_s=pulse_duration_s, units="V/V"
    )
    return result


def dispersive_ip_forward(
    sensitivity,
    sample_coordinates,
    chargeability,
    tau_s,
    exponent,
    *,
    domain="frequency",
    gates=False,
    pulse_duration_s=None,
    normalization="dc",
    cancel=None,
):
    """Spatial linearized IP: rows are ABMN, columns are samples/gates.

    Frequency output is complex IP anomaly 1-rho(omega)/rho_dc (V/V),
    NOT complex resistivity itself. Time output is secondary/primary V/V,
    with dc or measured finite-pulse primary normalization selected explicitly.
    Sensitivity columns represent fixed cells/zones and conductivity.
    """
    S = as_array(sensitivity, float)
    m, tau, c = [as_array(v, float) for v in (chargeability, tau_s, exponent)]
    if (
        S.ndim != 2
        or not S.shape[0]
        or not 1 <= S.shape[1] <= 32
        or S.size > 2_000_000
        or not np.isfinite(S).all()
        or m.shape != (S.shape[1],)
        or tau.shape != m.shape
        or c.shape != m.shape
    ):
        raise ValueError(
            "Finite sensitivity and matching parameter vectors for at most 32 cells/zones required"
        )
    values = []
    charging = []
    for mi, ti, ci in zip(m, tau, c):
        _parameters(mi, ti, ci)
        if cancel is not None and cancel():
            raise InterruptedError("Spatial dispersive IP cancelled")
        if domain == "frequency":
            if gates or pulse_duration_s is not None or normalization != "dc":
                raise ValueError("Time waveform options do not apply to spectra")
            f = as_array(sample_coordinates, float)
            if f.ndim != 1 or not 1 <= f.size <= 4096:
                raise ValueError(
                    "Frequency samples must be a nonempty vector up to 4096 values"
                )
            values.append(1.0 - cole_cole_resistivity(f, 1.0, mi, ti, ci))
        elif domain == "time":
            if normalization not in ("dc", "pulse"):
                raise ValueError("Normalization must be dc or pulse")
            values.append(
                cole_cole_decay(
                    None if gates else sample_coordinates,
                    mi,
                    ti,
                    ci,
                    gates_s=sample_coordinates if gates else None,
                    pulse_duration_s=pulse_duration_s,
                    cancel=cancel,
                )
            )
            if normalization == "pulse":
                charging.append(
                    0.0
                    if pulse_duration_s is None
                    else float(
                        cole_cole_decay([pulse_duration_s], mi, ti, ci, cancel=cancel)[
                            0
                        ]
                    )
                )
        else:
            raise ValueError("Domain must be frequency or time")
    if S.shape[0] * np.asarray(values).shape[1] > 100000:
        raise ValueError("Spatial IP output sample budget exceeded")
    prediction = S @ np.asarray(values)
    if domain == "time" and normalization == "pulse":
        primary = 1.0 - S @ np.asarray(charging)
        if np.any(abs(primary) < 1e-8):
            raise ValueError("Predicted finite-pulse primary is too close to zero")
        prediction = prediction / primary[:, None]
    return prediction


def fit_dispersive_ip(
    sensitivity,
    sample_coordinates,
    observed,
    *,
    initial,
    reference,
    standard_deviation=None,
    data_covariance=None,
    beta,
    domain="frequency",
    gates=False,
    pulse_duration_s=None,
    normalization="dc",
    lower=(0.0, 1e-9, 0.1),
    upper=(0.5, 1e9, 1.0),
    **solver_options,
):
    """Recover [m,tau_rho,c] per prescribed cell/zone using static sensitivity.

    initial/reference are (n_zones,3). This is small-polarization, fixed-
    conductivity inversion, not a nonlinear complex-conductivity PDE solve.
    """
    S = as_array(sensitivity, float)
    start, prior = as_array(initial, float), as_array(reference, float)
    if (
        S.ndim != 2
        or start.shape != (S.shape[1], 3)
        or prior.shape != start.shape
        or S.shape[1] < 1
        or S.shape[1] > 32
    ):
        raise ValueError(
            "Require sensitivity and (n_zones,3) initial/reference parameters"
        )
    for parameters in (start, prior):
        for row in parameters:
            _parameters(*row)
    low, high = as_array(lower, float), as_array(upper, float)
    if (
        low.shape != (3,)
        or high.shape != (3,)
        or low[0] < 0
        or high[0] >= 1
        or low[1] < 1e-12
        or high[1] > 1e12
        or low[2] <= 0
        or high[2] > 1
    ):
        raise ValueError("Spatial IP bounds exceed their physical domains")
    obs = as_array(observed, complex if domain == "frequency" else float)
    if obs.ndim != 2 or obs.shape[0] != S.shape[0]:
        raise ValueError("Observed shape must be (n_ABMN,n_samples)")

    def predict(vector):
        p = vector.reshape(-1, 3)
        return dispersive_ip_forward(
            S,
            sample_coordinates,
            *p.T,
            domain=domain,
            gates=gates,
            pulse_duration_s=pulse_duration_s,
            normalization=normalization,
            cancel=solver_options.get("cancel"),
        )

    result = _fit(
        predict,
        obs,
        start.ravel(),
        prior.ravel(),
        np.tile(low, len(start)),
        np.tile(high, len(start)),
        np.arange(1, start.size, 3),
        standard_deviation=standard_deviation,
        covariance=data_covariance,
        beta=beta,
        **solver_options,
    )
    model = result["parameters"].reshape(-1, 3)
    result.update(
        chargeability_v_v=model[:, 0],
        tau_rho_s=model[:, 1],
        exponent=model[:, 2],
        domain=domain,
        approximation="small-polarization static sensitivity; conductivity and geometry fixed",
        normalization=normalization,
        units="dimensionless complex IP anomaly" if domain == "frequency" else "V/V",
    )
    return result

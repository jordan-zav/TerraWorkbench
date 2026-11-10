"""Calibrated two-detector radon proxy with a temporal Gaussian prior.

This is an explicit linear model, NOT automatic radon concentration estimation
or reproduction of a proprietary/full IAEA processing recipe. Instrument,
cosmic and live-time corrections and measured response coefficients are
external inputs. Do not infer calibration coefficients from unknown geology.
"""

import numpy as np
from scipy.linalg import solve_banded

from ._array_contract import as_array


def paired_detector_radon(
    times_s,
    downward_u_rate,
    upward_u_rate,
    *,
    downward_std,
    upward_std,
    downward_radon_response,
    upward_ground_response,
    upward_radon_response,
    roughness,
    covariance_down_up=0.0,
    segment_ids=None,
    max_samples=3_000_000,
):
    """Joint terrestrial U-window rate and calibrated radon proxy versus time.

    Model d=g+alpha*r, u=beta*g+gamma*r. Rates already corrected for non-radon
    backgrounds; supplied alpha/beta/gamma define r units (NOT Bq/m^3 unless
    independently calibrated). Errors are Gaussian, per-record covariance is
    allowed; different times are independent in the likelihood.

    Prior penalty roughness*sum((r[i+1]-r[i])**2/delta_t), within contiguous
    segments only. roughness=0 gives the exact per-record 2x2 inverse. Returned
    variances are marginal posterior variances CONDITIONAL on fixed noise,
    coefficients and roughness, not frequentist smoothing standard errors.
    Negative estimates remain flagged, never clipped. O(n) tridiagonal solve.
    """
    time, down, up, sd, su = [
        as_array(v, float)
        for v in (times_s, downward_u_rate, upward_u_rate, downward_std, upward_std)
    ]
    if (
        time.ndim != 1
        or not 2 <= time.size <= max_samples
        or any(v.shape != time.shape for v in (down, up, sd, su))
        or not all(np.isfinite(v).all() for v in (time, down, up, sd, su))
        or np.any(sd <= 0)
        or np.any(su <= 0)
    ):
        raise ValueError(
            "Matching finite time/rate vectors and positive errors within sample budget required"
        )
    alpha, beta, gamma = (
        downward_radon_response,
        upward_ground_response,
        upward_radon_response,
    )
    if (
        not np.isfinite([alpha, beta, gamma, roughness]).all()
        or alpha < 0
        or beta < 0
        or gamma <= 0
        or roughness < 0
    ):
        raise ValueError(
            "Explicit nonnegative responses/roughness and positive upward radon response required"
        )
    determinant_response = gamma - alpha * beta
    if abs(determinant_response) <= 1e-8 * max(abs(gamma), abs(alpha * beta)):
        raise ValueError(
            "Detector responses cannot distinguish terrestrial and radon contributions"
        )
    covariance = np.broadcast_to(as_array(covariance_down_up, float), time.shape)
    if not np.isfinite(covariance).all() or np.any(abs(covariance) >= sd * su):
        raise ValueError(
            "Per-record detector noise covariance must be positive definite"
        )
    groups = np.zeros(len(time), int) if segment_ids is None else as_array(segment_ids)
    if groups.shape != time.shape or groups.dtype.kind not in "iubUS":
        raise ValueError("Contiguous segment IDs must be integer/string per record")
    linked = groups[1:] == groups[:-1]
    dt = np.diff(time)
    if np.any(dt[linked] <= 0):
        raise ValueError("Times must increase strictly within every contiguous segment")
    raw_radon = (up - beta * down) / determinant_response
    raw_radon_variance = (
        su**2 + beta**2 * sd**2 - 2 * beta * covariance
    ) / determinant_response**2
    weight = 1 / raw_radon_variance
    coupling = np.zeros(len(time) - 1)
    coupling[linked] = roughness / dt[linked]
    diagonal = weight.copy()
    diagonal[:-1] += coupling
    diagonal[1:] += coupling
    off = -coupling
    bands = np.zeros((3, len(time)))
    bands[1] = diagonal
    bands[0, 1:], bands[2, :-1] = off, off
    if not np.isfinite(bands).all() or np.any(weight <= 0):
        raise ValueError(
            "Temporal precision overflows; check time/error/roughness scales"
        )
    radon = solve_banded((1, 1), bands, weight * raw_radon)
    # LDL' recursion for exact inverse diagonal, not a diagonal approximation.
    pivot = np.empty(len(time))
    multiplier = np.empty(len(time) - 1)
    pivot[0] = diagonal[0]
    for i in range(len(time) - 1):
        if pivot[i] <= 0 or not np.isfinite(pivot[i]):
            raise ValueError(
                "Ill-conditioned temporal precision; reduce roughness or rescale"
            )
        multiplier[i] = off[i] / pivot[i]
        pivot[i + 1] = diagonal[i + 1] - off[i] * multiplier[i]
    if pivot[-1] <= 0 or not np.isfinite(pivot[-1]):
        raise ValueError("Ill-conditioned temporal precision")
    radon_variance = np.empty(len(time))
    radon_variance[-1] = 1 / pivot[-1]
    for i in range(len(time) - 2, -1, -1):
        radon_variance[i] = 1 / pivot[i] + multiplier[i] ** 2 * radon_variance[i + 1]
    # g | r is independent between records. Integrate over the correlated
    # posterior r to obtain correct marginal g variances and local g/r covariance.
    determinant_noise = sd**2 * su**2 - covariance**2
    b1 = (su**2 - beta * covariance) / determinant_noise
    b2 = (beta * sd**2 - covariance) / determinant_noise
    ground_precision = b1 + beta * b2
    ground_offset = (b1 * down + b2 * up) / ground_precision
    ground_radon = (alpha * b1 + gamma * b2) / ground_precision
    ground = ground_offset - ground_radon * radon
    ground_variance = 1 / ground_precision + ground_radon**2 * radon_variance
    predicted_down, predicted_up = ground + alpha * radon, beta * ground + gamma * radon
    return {
        "terrestrial_u_rate": ground,
        "radon_proxy": radon,
        "raw_radon_proxy": raw_radon,
        "terrestrial_posterior_variance": ground_variance,
        "radon_posterior_variance": radon_variance,
        "local_ground_radon_posterior_covariance": -ground_radon * radon_variance,
        "predicted_downward": predicted_down,
        "predicted_upward": predicted_up,
        "negative_ground": ground < 0,
        "negative_radon": radon < 0,
        "roughness": roughness,
        "linked_intervals": linked,
        "responses": {"down_radon": alpha, "up_ground": beta, "up_radon": gamma},
        "model": "calibrated two-detector linear mixture with temporal Gaussian prior",
        "uncertainty_note": "Conditional on calibration/noise/prior; not atmospheric concentration or full radionuclide processing",
    }

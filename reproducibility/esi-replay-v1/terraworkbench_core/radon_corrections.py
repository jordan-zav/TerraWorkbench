"""Calibrated airborne radon separation; no guessed detector coefficients.

IAEA-TECDOC-1363 (2003), section 5.5.6: upward-window and full-spectrum
mixture models. Outputs retain signed estimates and conditional uncertainty.
The methods do not convert a radon proxy into Bq/m3 without external calibration.
"""

import numpy as np

from ._array_contract import as_array
from ._calibration import covariance_array, integer_budget


def upward_window_radon(
    upward_u_rate,
    downward_u_rate,
    downward_th_rate,
    rate_covariance,
    coefficients,
    *,
    coefficient_covariance=None,
    max_samples=3_000_000,
    block_size=4096,
    canceled=None,
):
    """IAEA upward-detector equation with six supplied calibration constants.

    Rate order: upward U, downward U, downward Th, already corrected for
    instrument/cosmic background. Coefficients: a1,a2,au,at,bu,bt, where
    up_radon=au*down_U_radon+bu and down_Th_radon=at*down_U_radon+bt.
    The terrestrial upward contribution is a1*U_ground+a2*Th_ground.
    Covariances may be shared or per record; coefficient covariance is shared.
    Measurement/calibration errors must be independent. Shared coefficients
    correlate records; only marginal per-record covariance is returned.
    """
    integer_budget(max_samples, "max_samples")
    integer_budget(block_size, "block_size")
    up, u, th = [
        as_array(value, float)
        for value in (upward_u_rate, downward_u_rate, downward_th_rate)
    ]
    if (
        up.ndim != 1
        or not 1 <= len(up) <= max_samples
        or u.shape != up.shape
        or th.shape != up.shape
        or not all(np.isfinite(a).all() for a in (up, u, th))
    ):
        raise ValueError(
            "Aligned complete finite rate channels within sample budget required"
        )
    p = as_array(coefficients, float)
    if p.shape != (6,) or not np.isfinite(p).all():
        raise ValueError("Supply six finite coefficients: a1,a2,au,at,bu,bt")
    a1, a2, au, at, bu, bt = p
    denominator = au - a1 - a2 * at
    if abs(denominator) <= 1e-8 * max(
        abs(au), abs(a1), abs(a2 * at), np.finfo(float).tiny
    ):
        raise ValueError(
            "Calibrated detector responses cannot separate atmospheric and terrestrial U"
        )
    noise = covariance_array(rate_covariance, 3, len(up))
    calibration = (
        np.zeros((6, 6))
        if coefficient_covariance is None
        else covariance_array(coefficient_covariance, 6)
    )
    radon = np.empty(len(up))
    variance = np.empty(len(up))
    terrestrial = np.empty((len(up), 2))
    terrestrial_covariance = np.empty((len(up), 2, 2))
    data_gradient = np.array([1.0, -a1, -a2]) / denominator
    denominator_gradient = np.array([-1.0, -at, 1.0, -a2, 0.0, 0.0])
    for start in range(0, len(up), block_size):
        if canceled is not None and canceled():
            raise InterruptedError("Radon correction canceled")
        end = min(start + block_size, len(up))
        r = (
            up[start:end] - a1 * u[start:end] - a2 * th[start:end] + a2 * bt - bu
        ) / denominator
        numerator_gradient = np.column_stack(
            [
                -u[start:end],
                -th[start:end] + bt,
                np.zeros(len(r)),
                np.zeros(len(r)),
                -np.ones(len(r)),
                np.full(len(r), a2),
            ]
        )
        calibration_gradient = (
            numerator_gradient - r[:, None] * denominator_gradient
        ) / denominator
        radon[start:end] = r
        variance[start:end] = np.einsum(
            "i,nij,j->n", data_gradient, noise[start:end], data_gradient
        ) + np.einsum(
            "ni,ij,nj->n", calibration_gradient, calibration, calibration_gradient
        )
        terrestrial[start:end] = np.c_[u[start:end] - r, th[start:end] - at * r - bt]
        jd = np.stack(
            [
                np.array([0.0, 1.0, 0.0]) - data_gradient,
                np.array([0.0, 0.0, 1.0]) - at * data_gradient,
            ]
        )
        jp = np.stack([-calibration_gradient, -at * calibration_gradient], axis=1)
        jp[:, 1, 3] -= r
        jp[:, 1, 5] -= 1
        terrestrial_covariance[start:end] = np.einsum(
            "ai,nij,bj->nab", jd, noise[start:end], jd
        ) + np.einsum("nai,ij,nbj->nab", jp, calibration, jp)
    if not all(
        np.isfinite(a).all()
        for a in (radon, variance, terrestrial, terrestrial_covariance)
    ):
        raise ValueError(
            "Radon/covariance arithmetic overflow; review calibration and units"
        )
    return dict(
        radon_u_rate=radon,
        radon_variance=variance,
        terrestrial_u_rate=terrestrial[:, 0],
        terrestrial_th_rate=terrestrial[:, 1],
        terrestrial_covariance=terrestrial_covariance,
        negative_radon=radon < 0,
        negative_terrestrial=terrestrial < 0,
        coefficients=p.copy(),
        coefficient_order=["a1", "a2", "au", "at", "bu", "bt"],
        calibration_uncertainty_included=coefficient_covariance is not None,
        recipe=dict(
            method="IAEA-TECDOC-1363-equation-5.7",
            rate_covariance_order=["upward_U", "downward_U", "downward_Th"],
            missing_policy="caller must split or mask incomplete records explicitly",
            units="same count-rate units as supplied calibration",
            uncertainty="First-order calibration propagation; cross-record calibration covariance not materialized; no atmospheric concentration conversion",
        ),
    )


def calibrated_window_radon(
    window_rates,
    rate_covariance,
    response_matrix,
    *,
    radon_component=3,
    max_samples=3_000_000,
    maximum_condition=1e8,
    block_size=4096,
    canceled=None,
):
    """Separate four calibrated window components, including atmospheric radon.

    Input shape (records,4), response (windows,components), fixed known response.
    A possible basis is continuum-corrected low-Bi, K, U and Th windows with
    columns K/U/Th/Rn. This is a general calibrated window mixture, not a claim
    that arbitrary low-energy sums reproduce the IAEA continuum-subtracted L.
    Output covariance includes correlation from estimating and subtracting radon
    from those same measurements. Shared calibration uncertainty is excluded.
    """
    integer_budget(max_samples, "max_samples")
    integer_budget(block_size, "block_size")
    if (
        isinstance(radon_component, bool)
        or not isinstance(radon_component, (int, np.integer))
        or not 0 <= radon_component < 4
    ):
        raise ValueError("radon_component must index one of four components")
    y, a = as_array(window_rates, float), as_array(response_matrix, float)
    if (
        y.ndim != 2
        or y.shape[1] != 4
        or not 1 <= len(y) <= max_samples
        or a.shape != (4, 4)
        or not all(np.isfinite(v).all() for v in (y, a))
    ):
        raise ValueError("Finite records/four-window rates and a 4x4 response required")
    scale = np.linalg.norm(a, axis=0)
    if (
        not np.isfinite(maximum_condition)
        or maximum_condition < 1
        or np.any(scale == 0)
        or np.linalg.cond(a / scale) > maximum_condition
    ):
        raise ValueError("Window response is singular or ill-conditioned")
    inverse = np.linalg.inv(a)
    projection = np.eye(4) - np.outer(a[:, radon_component], inverse[radon_component])
    noise = covariance_array(rate_covariance, 4, len(y))
    components = np.empty_like(y)
    covariance = np.empty((len(y), 4, 4))
    corrected = np.empty_like(y)
    corrected_covariance = np.empty_like(covariance)
    for start in range(0, len(y), block_size):
        if canceled is not None and canceled():
            raise InterruptedError("Window radon correction canceled")
        end = min(start + block_size, len(y))
        components[start:end] = y[start:end] @ inverse.T
        corrected[start:end] = y[start:end] @ projection.T
        covariance[start:end] = np.einsum(
            "ai,nij,bj->nab", inverse, noise[start:end], inverse
        )
        corrected_covariance[start:end] = np.einsum(
            "ai,nij,bj->nab", projection, noise[start:end], projection
        )
    if not all(
        np.isfinite(v).all()
        for v in (components, covariance, corrected, corrected_covariance)
    ):
        raise ValueError("Window separation/covariance overflow")
    return dict(
        component_rates=components,
        component_covariance=covariance,
        corrected_window_rates=corrected,
        corrected_window_covariance=corrected_covariance,
        negative_components=components < 0,
        radon_component=int(radon_component),
        uncertainty_note="Conditional on fixed known window response; same-measurement radon subtraction covariance retained",
    )


def full_spectrum_radon(
    spectra,
    response_matrix,
    rate_std,
    component_names,
    *,
    radon_component=3,
    maximum_condition=1e8,
    max_elements=5_000_000,
    canceled=None,
):
    """Signed weighted full-spectrum separation with a calibrated radon template.

    spectra=(records,channels), response=(channels,components), std shared per
    channel or per record. Spectra and templates must share energy calibration,
    rate/exposure convention and geometry. Independent Gaussian channel errors
    are explicit inputs, never invented from zero counts. Correlated rebinned
    bins need a separate covariance-aware likelihood; this API rejects that
    noise model by contract. Coefficients are allowed negative and flagged.
    """
    integer_budget(max_elements, "max_elements")
    y, a, std = (
        as_array(spectra, float),
        as_array(response_matrix, float),
        as_array(rate_std, float),
    )
    if (
        y.ndim != 2
        or a.ndim != 2
        or not len(y)
        or a.shape[0] != y.shape[1]
        or not 1 <= a.shape[1] <= 8
        or y.shape[1] < a.shape[1]
        or y.size * 3 + a.size > max_elements
    ):
        raise ValueError(
            "Bounded records/channels and channels/components matrices required"
        )
    if (
        std.shape not in (y.shape, (y.shape[1],))
        or not all(np.isfinite(v).all() for v in (y, a, std))
        or np.any(std <= 0)
    ):
        raise ValueError(
            "Finite spectra/response and positive independent channel errors required"
        )
    std = np.broadcast_to(std, y.shape)
    k = a.shape[1]
    if (
        not isinstance(component_names, (list, tuple))
        or len(component_names) != k
        or len(set(component_names)) != k
        or any(not isinstance(s, str) or not s.strip() for s in component_names)
    ):
        raise ValueError("Unique explicit component_names required")
    if (
        isinstance(radon_component, bool)
        or not isinstance(radon_component, (int, np.integer))
        or not 0 <= radon_component < k
    ):
        raise ValueError("Explicit valid radon component index required")
    if not np.isfinite(maximum_condition) or maximum_condition < 1:
        raise ValueError("maximum_condition must be finite and >=1")
    coefficients = np.empty((len(y), k))
    covariance = np.empty((len(y), k, k))
    corrected = np.empty_like(y)
    corrected_variance = np.empty_like(y)
    chi_squared = np.empty(len(y))
    condition = np.empty(len(y))
    for i in range(len(y)):
        if canceled is not None and canceled():
            raise InterruptedError("Full-spectrum radon correction canceled")
        weighted = a / std[i, :, None]
        scale = np.linalg.norm(weighted, axis=0)
        if np.any(scale == 0) or not np.isfinite(scale).all():
            raise ValueError(
                "Zero or numerically unbounded response template is not identifiable"
            )
        u, s, vh = np.linalg.svd(weighted / scale, full_matrices=False)
        if (
            s[-1] <= s[0] / maximum_condition
            or s[-1] <= np.finfo(float).eps * max(a.shape) * s[0]
        ):
            raise ValueError(
                "Full-spectrum templates are rank deficient or ill-conditioned"
            )
        condition[i] = s[0] / s[-1]
        inverse = (vh.T / s) @ u.T
        inverse /= scale[:, None]
        coefficients[i] = inverse @ (y[i] / std[i])
        covariance[i] = inverse @ inverse.T
        radon = coefficients[i, radon_component]
        template = a[:, radon_component]
        corrected[i] = y[i] - template * radon
        # B maps the raw spectrum to the estimated coefficients. Its radon row
        # is correlated with each raw channel, so variance cannot simply add.
        cross = std[i] * inverse[radon_component]
        corrected_variance[i] = (
            std[i] ** 2
            + template**2 * covariance[i, radon_component, radon_component]
            - 2 * template * cross
        )
        # A projection can remove a channel exactly. Permit only rounding-sized
        # cancellation at zero; larger negative variances indicate instability.
        tolerance = (
            64
            * np.finfo(float).eps
            * (
                std[i] ** 2
                + template**2 * covariance[i, radon_component, radon_component]
            )
        )
        if np.any(corrected_variance[i] < -tolerance):
            raise ValueError("Unstable negative corrected spectral variance")
        corrected_variance[i] = np.maximum(corrected_variance[i], 0.0)
        chi_squared[i] = np.sum(((y[i] - a @ coefficients[i]) / std[i]) ** 2)
    if not all(
        np.isfinite(v).all()
        for v in (coefficients, covariance, corrected, corrected_variance, chi_squared)
    ):
        raise ValueError("Full-spectrum arithmetic overflow")
    return dict(
        component_rates=coefficients,
        component_covariance=covariance,
        corrected_spectra=corrected,
        corrected_variance=corrected_variance,
        chi_squared=chi_squared,
        degrees_of_freedom=y.shape[1] - k,
        design_condition=condition,
        component_names=list(component_names),
        radon_component=int(radon_component),
        negative_components=coefficients < 0,
        recipe=dict(
            method="calibrated-weighted-full-spectrum-radon-separation",
            units="template-defined component units",
            uncertainty="Independent fixed channel errors and known templates; same-spectrum subtraction covariance retained; energy/template/calibration uncertainty excluded",
        ),
    )

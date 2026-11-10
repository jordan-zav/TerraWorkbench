"""Measured spectrometer response and first-order calibration uncertainty.

No automatic pad geometry, height, live-time, aircraft, cosmic or radon correction.
Concentrations of standards are treated as exact; units are caller supplied.
"""

import numpy as np

from ._array_contract import as_array
from ._calibration import covariance_array, gaussian_calibration, integer_budget


def _labels(labels, count, name):
    if (
        not isinstance(labels, (list, tuple))
        or len(labels) != count
        or any(not isinstance(v, str) or not v.strip() for v in labels)
    ):
        raise ValueError(name + " requires an explicit nonempty string per channel")
    return list(labels)


def fit_radiometric_response(
    known_concentrations,
    window_rates,
    rate_covariance,
    *,
    component_names,
    concentration_units,
    window_names,
    maximum_condition=1e10,
    max_elements=2_000_000,
):
    """Fit rates = concentration @ sensitivity.T + offset by full GLS.

    All standards must be comparable in geometry/exposure/corrections. Known
    concentrations are exact, not errors-in-variables. Covariance across windows
    is supported; covariance across standard records is not. Coefficient order
    is window-major [sensitivities to all components, offset], repeated per window.
    No positivity constraints or clipping; inspect negative sensitivities.
    """
    integer_budget(max_elements, "max_elements")
    c, y = as_array(known_concentrations, float), as_array(window_rates, float)
    if (
        c.ndim != 2
        or y.ndim != 2
        or c.shape[0] != y.shape[0]
        or not 1 <= c.shape[1] <= 8
        or not 1 <= y.shape[1] <= 8
        or c.shape[0] < c.shape[1] + 1
        or not np.isfinite(c).all()
        or not np.isfinite(y).all()
    ):
        raise ValueError(
            "Finite standard/component and standard/window matrices required"
        )
    n, k = c.shape
    m = y.shape[1]
    p = m * (k + 1)
    if n * m * p + 4 * p**2 + n * m**2 > max_elements:
        raise ValueError("Dense calibration element budget exceeded")
    names = _labels(component_names, k, "component_names")
    units = _labels(concentration_units, k, "concentration_units")
    windows = _labels(window_names, m, "window_names")
    if len(set(names)) != k or len(set(windows)) != m:
        raise ValueError(
            "Component and window names must be unique within their groups"
        )
    covariance = covariance_array(rate_covariance, m, n, strict=True)
    features = np.column_stack([c, np.ones(n)])
    design = np.zeros((n, m, p))
    for i in range(m):
        design[:, i, i * (k + 1) : (i + 1) * (k + 1)] = features
    coefficients, cov, diagnostics = gaussian_calibration(
        design, y, covariance, maximum_condition=maximum_condition
    )
    blocks = coefficients.reshape(m, k + 1)
    predicted = c @ blocks[:, :k].T + blocks[:, k]
    return {
        "sensitivity": blocks[:, :k].copy(),
        "offset_rate": blocks[:, k].copy(),
        "coefficient_covariance": cov,
        "coefficient_order": [
            f"{w}:{label}" for w in windows for label in names + ["offset"]
        ],
        "component_names": names,
        "concentration_units": units,
        "window_names": windows,
        "rate_units": "counts/s",
        "predicted_rates": predicted,
        "residual_rates": y - predicted,
        "negative_sensitivity": blocks[:, :k] < 0,
        **diagnostics,
        "uncertainty_note": "Conditional on exact standard concentrations and fixed geometry/corrections; no pad/reference uncertainty",
    }


def radiometric_concentrations(
    window_rates,
    rate_covariance,
    *,
    calibration,
    max_samples=3_000_000,
    max_output_elements=50_000_000,
    block_size=4096,
    maximum_condition=1e8,
    cancel=None,
):
    """Invert a square calibrated window response and propagate uncertainty.

    Delta-method first-order covariance includes measured rates AND sensitivity/
    offset uncertainty. Survey measurements must be independent of calibration
    records. Returns marginal per-record covariance, not cross-record covariance:
    a shared calibration creates correlated errors between survey points.
    Negative estimates remain marked. No conversion of eU/eTh to true elemental
    abundances, radioactive-equilibrium assertion or implicit altitude correction.
    """
    for value, label in (
        (max_samples, "max_samples"),
        (max_output_elements, "max_output_elements"),
        (block_size, "block_size"),
    ):
        integer_budget(value, label)
    y = as_array(window_rates, float)
    if y.ndim != 2 or not 1 <= len(y) <= max_samples or not np.isfinite(y).all():
        raise ValueError("Finite sample/window matrix within sample budget required")
    n, k = y.shape
    if not 1 <= k <= 8 or n * (k + k * k) > max_output_elements:
        raise ValueError("Concentration/covariance output budget exceeded")
    sensitivity = as_array(calibration["sensitivity"], float)
    offset = as_array(calibration["offset_rate"], float)
    if (
        sensitivity.shape != (k, k)
        or offset.shape != (k,)
        or not np.isfinite(sensitivity).all()
        or not np.isfinite(offset).all()
    ):
        raise ValueError("Finite square sensitivity and matching offset required")
    if (
        not np.isfinite(maximum_condition)
        or maximum_condition < 1
        or np.linalg.cond(sensitivity) > maximum_condition
    ):
        raise ValueError("Sensitivity is singular or ill-conditioned")
    names = _labels(calibration["component_names"], k, "component_names")
    units = _labels(calibration["concentration_units"], k, "concentration_units")
    cov_theta = covariance_array(calibration["coefficient_covariance"], k * (k + 1))
    noise = covariance_array(rate_covariance, k, n)
    inverse = np.linalg.inv(sensitivity)
    result = np.empty((n, k))
    covariance = np.empty((n, k, k))
    for first in range(0, n, block_size):
        if cancel is not None and cancel():
            raise InterruptedError("Radiometric calibration application cancelled")
        stop = min(n, first + block_size)
        x = (y[first:stop] - offset) @ inverse.T
        features = np.column_stack([x, np.ones(stop - first)])
        jacobian = -np.einsum("ai,bj->baij", inverse, features).reshape(
            stop - first, k, -1
        )
        propagated = np.einsum("ai,bij,cj->bac", inverse, noise[first:stop], inverse)
        propagated += np.einsum(
            "bip,pq,bjq->bij", jacobian, cov_theta, jacobian, optimize=True
        )
        result[first:stop], covariance[first:stop] = (
            x,
            (propagated + propagated.swapaxes(1, 2)) / 2,
        )
    if not np.isfinite(result).all() or not np.isfinite(covariance).all():
        raise ValueError(
            "Calibration propagation overflow; rescale units or reject unstable response"
        )
    return {
        "concentrations": result,
        "covariance": covariance,
        "negative": result < 0,
        "component_names": names,
        "concentration_units": units,
        "uncertainty_note": "First-order marginal covariance; shared-calibration cross-record covariance and standard/geometry errors are not returned",
    }

"""Small, explicitly bounded Gaussian calibration helpers."""

import numpy as np

from ._array_contract import as_array


def integer_budget(value, name, minimum=1):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, np.integer))
        or value < minimum
    ):
        raise ValueError(name + " must be an integer >= " + str(minimum))


def covariance_array(value, size, count=None, *, strict=False):
    """Validate shared or per-record covariance without fabricating errors."""
    a = as_array(value, float)
    shapes = [(size, size)]
    if count is not None:
        shapes.append((count, size, size))
    if a.shape not in shapes or not np.isfinite(a).all():
        raise ValueError("Finite covariance with matching dimensions required")
    scale = np.max(np.abs(a), axis=(-2, -1))
    asymmetry = np.max(np.abs(a - np.swapaxes(a, -1, -2)), axis=(-2, -1))
    if np.any(asymmetry > 1e-10 * np.maximum(scale, np.finfo(float).tiny)):
        raise ValueError("Covariance must be symmetric")
    a = (a + np.swapaxes(a, -1, -2)) / 2
    eigenvalues = np.linalg.eigvalsh(a)
    tolerance = 1e-12 * np.maximum(scale, np.finfo(float).tiny)
    if np.any(eigenvalues[..., 0] < -tolerance) or (
        strict and np.any(eigenvalues[..., 0] <= 0)
    ):
        raise ValueError(
            "Covariance must be positive " + ("definite" if strict else "semidefinite")
        )
    return a if count is None else np.broadcast_to(a, (count, size, size))


def gaussian_calibration(design, observed, covariance, *, maximum_condition):
    """Whiten records then SVD least squares; known noise, exact standards."""
    factor = np.linalg.cholesky(covariance)
    matrix = np.linalg.solve(factor, design).reshape(-1, design.shape[-1])
    data = np.linalg.solve(factor, observed[..., None]).ravel()
    # A gain multiplying teslas and an offset in teslas have very different
    # column scales. Conditioning/rank must not depend on arbitrary unit size.
    column_scale = np.linalg.norm(matrix, axis=0)
    if not np.isfinite(column_scale).all() or not np.isfinite(data).all():
        raise ValueError("Calibration whitening overflows; check errors/units")
    column_scale = np.where(column_scale > 0, column_scale, 1.0)
    normalized = matrix / column_scale
    normalized_coefficients, _, rank, singular = np.linalg.lstsq(
        normalized, data, rcond=None
    )
    if (
        not np.isfinite(maximum_condition)
        or maximum_condition < 1
        or rank < matrix.shape[1]
        or singular[0] / singular[-1] > maximum_condition
    ):
        raise ValueError("Calibration standards are rank deficient or ill-conditioned")
    _, _, vh = np.linalg.svd(normalized, full_matrices=False)
    coefficient_covariance = (
        ((vh.T / singular**2) @ vh) / column_scale[:, None] / column_scale[None, :]
    )
    coefficients = normalized_coefficients / column_scale
    residual = data - normalized @ normalized_coefficients
    return (
        coefficients,
        coefficient_covariance,
        {
            "chi_squared": float(residual @ residual),
            "degrees_of_freedom": matrix.shape[0] - matrix.shape[1],
            "design_condition": float(singular[0] / singular[-1]),
            "condition_basis": "noise-whitened, column-normalized design; unit-scale invariant",
            "noise_model": "Independent records, supplied full within-record Gaussian covariance; no residual rescaling",
        },
    )

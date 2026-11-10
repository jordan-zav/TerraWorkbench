"""Small-problem linear sensitivity diagnostics, not nonlinear certainty.

Explicit dense-matrix budgets. Do not feed a regional 3D sensitivity matrix
here without reducing the problem; these are audit/reference diagnostics.
"""

import numpy as np
from scipy.linalg import cho_factor, cho_solve

from ._array_contract import as_array


def fixed_l2_reference(
    sensitivity,
    observed,
    data_std,
    regularization,
    *,
    beta,
    reference_model=None,
    max_elements=2_000_000,
):
    """Small dense augmented-SVD oracle; fixed physical L2 prior, no bounds.

    Minimize ||Wd(Gm-d)||**2 + beta*||L(m-mref)||**2 without forming normal
    equations. This optimum need not equal the generating geological model.
    """
    from scipy.linalg import lstsq
    from ._calibration import integer_budget

    integer_budget(max_elements, "max_elements")

    g, d, sigma, reg = [
        as_array(v, float) for v in (sensitivity, observed, data_std, regularization)
    ]
    if (
        g.ndim != 2
        or min(g.shape) < 1
        or d.shape != (g.shape[0],)
        or sigma.shape != d.shape
        or reg.ndim != 2
        or reg.shape[1] != g.shape[1]
        or not all(np.isfinite(v).all() for v in (g, d, sigma, reg))
        or np.any(sigma <= 0)
        or not np.isfinite(beta)
        or beta <= 0
    ):
        raise ValueError("Require finite G/d/L, positive data errors and beta")
    n = g.shape[1]
    if 3 * (g.size + reg.size) + 4 * n * n > max_elements:
        raise ValueError("Dense L2 reference budget exceeded")
    reference = (
        np.zeros(n) if reference_model is None else as_array(reference_model, float)
    )
    if reference.shape != (n,) or not np.isfinite(reference).all():
        raise ValueError("Reference must be a finite model vector")
    a = g / sigma[:, None]
    augmented = np.vstack((a, np.sqrt(beta) * reg))
    rhs = np.r_[(d - g @ reference) / sigma, np.zeros(reg.shape[0])]
    shift, _, rank, singular = lstsq(augmented, rhs, lapack_driver="gelsd")
    if rank != n:
        raise ValueError(
            "Fixed L2 reference requires a full column rank augmented system"
        )
    residual = augmented @ shift - rhs
    gradient = augmented.T @ residual
    denominator = max(np.linalg.norm(augmented.T @ rhs), np.finfo(float).tiny)
    return dict(
        model=reference + shift,
        objective=float(residual @ residual),
        scaled_optimality=float(np.linalg.norm(gradient) / denominator),
        augmented_condition=float(singular[0] / singular[-1]),
        augmented_singular_values=singular,
        rank=int(rank),
        definition="fixed L2 unconstrained optimum, not geological truth",
    )


def linear_error_partition(
    sensitivity, data_std, model_error, cell_volumes, *, max_elements=2_000_000
):
    """Volume-weighted row/null partition for small linear sensitivity matrices.

    Numerical null space is determined by machine-rank SVD, not a geological
    resolution cutoff or a nonlinear IRLS posterior. Weak nonzero modes remain
    in the row space and must be inspected through the singular spectrum.
    """
    from ._calibration import integer_budget

    integer_budget(max_elements, "max_elements")
    g, std, error, volumes = [
        as_array(v, float) for v in (sensitivity, data_std, model_error, cell_volumes)
    ]
    if (
        g.ndim != 2
        or min(g.shape) < 1
        or std.shape != (g.shape[0],)
        or error.ndim not in (1, 2)
        or error.shape[0] != g.shape[1]
        or volumes.shape != (g.shape[1],)
        or not all(np.isfinite(v).all() for v in (g, std, error, volumes))
        or np.any(std <= 0)
        or np.any(volumes <= 0)
    ):
        raise ValueError(
            "Require finite G/error, positive standard deviations and volumes"
        )
    if 3 * g.size + 4 * min(g.shape) * g.shape[1] + 4 * error.size > max_elements:
        raise ValueError("Dense error partition budget exceeded")
    root = np.sqrt(volumes / volumes.max())
    a = g / std[:, None] / root[None, :]
    _, singular, vt = np.linalg.svd(a, full_matrices=False)
    cutoff = np.finfo(float).eps * max(a.shape) * singular[0]
    rank = int(np.count_nonzero(singular > cutoff))
    z = (root if error.ndim == 1 else root[:, None]) * error
    row = vt[:rank].T @ (vt[:rank] @ z)
    null = z - row
    energy = np.sum(z * z, axis=0)
    row_fraction = np.divide(
        np.sum(row * row, axis=0), energy, out=np.zeros_like(energy), where=energy > 0
    )
    null_fraction = np.divide(
        np.sum(null * null, axis=0), energy, out=np.zeros_like(energy), where=energy > 0
    )
    divisor = root if error.ndim == 1 else root[:, None]
    return dict(
        rank=rank,
        parameters=g.shape[1],
        numerical_nullity=g.shape[1] - rank,
        singular_values=singular,
        rank_cutoff=float(cutoff),
        row_error=row / divisor,
        null_error=null / divisor,
        row_energy_fraction=float(row_fraction) if error.ndim == 1 else row_fraction,
        null_energy_fraction=float(null_fraction) if error.ndim == 1 else null_fraction,
        definition="fixed linear numerical row/null partition; not nonlinear uncertainty",
    )


def linear_resolution(
    sensitivity, data_std, regularization, *, beta, max_elements=2_000_000
):
    """Gaussian linear covariance and resolution with fixed beta and L.

    G maps physical model parameters to physical data, Wd=diag(1/std).
    Precision=G.T*Wd**2*G+beta*L.T*L; resolution=precision^-1*G.T*Wd**2*G.
    The prior must make precision positive definite. This is NOT a nonlinear
    posterior, spatial DOI, or a covariance valid after adaptive IRLS/beta.
    """
    g, std, reg = (
        as_array(sensitivity, float),
        as_array(data_std, float),
        as_array(regularization, float),
    )
    if (
        g.ndim != 2
        or min(g.shape) < 1
        or std.shape != (g.shape[0],)
        or reg.ndim != 2
        or reg.shape[1] != g.shape[1]
        or not all(np.isfinite(a).all() for a in (g, std, reg))
        or np.any(std <= 0)
        or not np.isfinite(beta)
        or beta <= 0
    ):
        raise ValueError("Require finite G/L, positive data errors and beta")
    if g.size + reg.size + 6 * g.shape[1] ** 2 > max_elements:
        raise ValueError("Dense resolution/covariance budget exceeded")
    weighted = g / std[:, None]
    gram = weighted.T @ weighted
    precision = gram + beta * (reg.T @ reg)
    try:
        factor = cho_factor(precision)
    except np.linalg.LinAlgError as error:
        raise ValueError(
            "Prior and data do not constrain all model directions"
        ) from error
    covariance = cho_solve(factor, np.eye(g.shape[1]))
    resolution = cho_solve(factor, gram)
    singular = np.linalg.svd(weighted, compute_uv=False)
    return {
        "posterior_covariance": covariance,
        "resolution": resolution,
        "posterior_std": np.sqrt(np.maximum(np.diag(covariance), 0)),
        "sensitivity_norm": np.linalg.norm(weighted, axis=0),
        "whitened_singular_values": singular,
        "effective_parameters": float(np.trace(resolution)),
        "beta": float(beta),
        "model": "fixed linear Gaussian",
    }


def reference_model_doi(
    model_a, model_b, reference_a, reference_b, *, minimum_contrast
):
    """Signed reference-model sensitivity (ma-mb)/(ra-rb), no clipping.

    Both inversions must use the same parameterization, data and misfit
    settings. This conventional reference comparison is not a universal
    geological depth cutoff. Cells with insufficient reference contrast are
    invalid, rather than silently assigned zero or infinity.
    """
    a, b, ra, rb = np.broadcast_arrays(
        *[as_array(v, float) for v in (model_a, model_b, reference_a, reference_b)]
    )
    if not np.isfinite(minimum_contrast) or minimum_contrast <= 0:
        raise ValueError(
            "An explicit positive reference contrast threshold is required"
        )
    valid = (
        np.isfinite(a)
        & np.isfinite(b)
        & np.isfinite(ra)
        & np.isfinite(rb)
        & (abs(ra - rb) >= minimum_contrast)
    )
    doi = np.divide(a - b, ra - rb, out=np.full(a.shape, np.nan), where=valid)
    return {
        "doi": doi,
        "valid": valid,
        "note": "Reference dependence, not a calibrated depth or probability",
    }

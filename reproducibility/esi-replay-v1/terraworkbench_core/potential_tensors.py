"""Potential-field tensors, invariant diagnostics and optional prism forward.

Tensor basis everywhere in this API is east, north, UP. Gravity tensors are
potential Hessians in Eotvos (1e-9 s^-2); not derivatives of down-positive gz
with respect to up. Harmonica's down basis is converted explicitly.
"""

import numpy as np

from ._array_contract import as_array


def _tensor(values):
    a = as_array(values, float)
    if a.ndim < 2 or a.shape[-2:] != (3, 3) or not np.isfinite(a).all():
        raise ValueError("Finite (..., 3, 3) tensors required")
    if not np.allclose(a, np.swapaxes(a, -1, -2), rtol=1e-10, atol=1e-12):
        raise ValueError("Potential Hessian must be symmetric")
    return a


def rotate_tensor(tensor, rotation):
    """Transform T'=R*T*R.T; rows of R are new basis vectors in old basis.

    One proper orthonormal rotation is applied to the whole tensor array.
    """
    a, r = _tensor(tensor), as_array(rotation, float)
    if (
        r.shape != (3, 3)
        or not np.isfinite(r).all()
        or not np.allclose(r @ r.T, np.eye(3), atol=1e-10, rtol=0)
        or not np.isclose(np.linalg.det(r), 1.0, atol=1e-10, rtol=0)
    ):
        raise ValueError("rotation must be a proper orthonormal 3 by 3 matrix")
    return np.einsum("ij,...jk,lk->...il", r, a, r)


def tensor_invariants(tensor):
    """I1, I2, I3, sorted eigenvalues and deviator norm; input units preserved.

    Trace is a Laplace diagnostic only OUTSIDE source material. Do not force
    trace to zero inside a density body or when assessing measured noise.
    """
    a = _tensor(tensor)
    trace = np.trace(a, axis1=-2, axis2=-1)
    second = (trace**2 - np.einsum("...ij,...ji->...", a, a)) / 2
    deviator = a - trace[..., None, None] * np.eye(3) / 3
    return {
        "trace": trace,
        "second_invariant": second,
        "determinant": np.linalg.det(a),
        "eigenvalues": np.linalg.eigvalsh(a),
        "deviator_frobenius": np.linalg.norm(deviator, axis=(-2, -1)),
    }


def prism_gravity_tensor(
    coordinates_enu_m,
    prisms_m,
    density_kg_m3,
    *,
    block_size=1024,
    max_interactions=20_000_000,
    cancel=None,
):
    """Six-component forward Hessian, explicitly converted to up-positive basis.

    Prisms are (west,east,south,north,bottom,top). Observations on singular
    edges/vertices are rejected if the backend returns nonfinite derivatives.
    Cancellation is checked between bounded observation blocks. Parallel JIT
    is disabled to avoid competing with caller-managed parallelism.
    """
    xyz, p, density = (
        as_array(coordinates_enu_m, float),
        as_array(prisms_m, float),
        as_array(density_kg_m3, float),
    )
    if (
        xyz.ndim != 2
        or xyz.shape[1] != 3
        or len(xyz) < 1
        or p.ndim != 2
        or p.shape[1] != 6
        or len(p) < 1
        or density.shape != (len(p),)
        or not all(np.isfinite(a).all() for a in (xyz, p, density))
        or np.any(p[:, 0] >= p[:, 1])
        or np.any(p[:, 2] >= p[:, 3])
        or np.any(p[:, 4] >= p[:, 5])
    ):
        raise ValueError(
            "Finite observations, nonempty ordered prisms and matching kg/m3 densities required"
        )
    if (
        not isinstance(block_size, int)
        or isinstance(block_size, bool)
        or block_size <= 0
    ):
        raise ValueError("block_size must be a positive integer")
    if len(xyz) * len(p) > max_interactions:
        raise ValueError("Forward observation/source interaction budget exceeded")
    try:
        import harmonica
    except ImportError as error:
        raise ImportError(
            "Prism tensors require terraworkbench-core[prisms]"
        ) from error
    result = np.empty((len(xyz), 3, 3))
    for start in range(0, len(xyz), block_size):
        if cancel is not None and cancel():
            raise InterruptedError("Prism tensor calculation cancelled")
        stop = min(start + block_size, len(xyz))
        coordinates = tuple(xyz[start:stop].T)
        for i, j, field, sign in (
            (0, 0, "g_ee", 1),
            (1, 1, "g_nn", 1),
            (2, 2, "g_zz", 1),
            (0, 1, "g_en", 1),
            (0, 2, "g_ez", -1),
            (1, 2, "g_nz", -1),
        ):
            value = sign * harmonica.prism_gravity(
                coordinates, p, density, field, parallel=False
            )
            if not np.isfinite(value).all():
                raise ValueError(
                    "Undefined prism tensor at a singular observation point"
                )
            result[start:stop, i, j] = value
            result[start:stop, j, i] = value
    return {
        "tensor_eotvos": result,
        "basis": "east,north,up",
        "invariants": tensor_invariants(result),
        "engine": "Harmonica",
        "engine_version": harmonica.__version__,
        "density_units": "kg/m3",
    }

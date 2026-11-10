"""Standalone, budgeted equivalent-source interpolation and continuation.

Harmonica's Cartesian 1/r equivalent sources, not a physical density model.
Caller supplies source locations, damping and target heights; no fixed-height
FFT assumption. No extrapolation uncertainty or geological uniqueness claim.
"""

import numpy as np

from ._array_contract import as_array


def equivalent_source_predict(
    observation_enu_m,
    values,
    source_enu_m,
    target_enu_m,
    *,
    damping,
    max_kernel_elements=5_000_000,
    prediction_block_size=1024,
    cancel=None,
):
    """Fit an explicit source layer and predict arbitrary observation surfaces.

    Damping is positive or None (unregularized). Reject coincident sources and
    observation/target points. Training is dense and budgeted, predictions are
    blocked. Caller must validate damping and geometry using independent held-
    out data; fitted residuals are not a continuation accuracy certificate.
    """
    obs, data, points, target = [
        as_array(a, float)
        for a in (observation_enu_m, values, source_enu_m, target_enu_m)
    ]
    for xyz in (obs, points, target):
        if (
            xyz.ndim != 2
            or xyz.shape[1] != 3
            or len(xyz) < 1
            or not np.isfinite(xyz).all()
        ):
            raise ValueError(
                "Finite nonempty (n,3) ENU metre coordinate arrays required"
            )
    if data.shape != (len(obs),) or not np.isfinite(data).all():
        raise ValueError("Finite data must match observation coordinates")
    if damping is not None and (not np.isfinite(damping) or damping <= 0):
        raise ValueError("damping must be positive or explicitly None")
    if len(obs) * len(points) > max_kernel_elements:
        raise ValueError("Dense equivalent-source training budget exceeded")
    if (
        not isinstance(prediction_block_size, int)
        or isinstance(prediction_block_size, bool)
        or prediction_block_size < 1
    ):
        raise ValueError("prediction_block_size must be a positive integer")
    source_locations = {tuple(row) for row in points}
    if any(tuple(row) in source_locations for row in obs) or any(
        tuple(row) in source_locations for row in target
    ):
        raise ValueError("Sources must not coincide with observations or targets")
    if len(source_locations) != len(points):
        raise ValueError("Duplicate equivalent source locations are not identifiable")
    if cancel is not None and cancel():
        raise InterruptedError("Equivalent-source prediction cancelled")
    try:
        import harmonica
    except ImportError as error:
        raise ImportError(
            "Equivalent sources require terraworkbench-core[prisms]"
        ) from error
    model = harmonica.EquivalentSources(
        points=tuple(points.T), damping=damping, parallel=False, dtype="float64"
    )
    model.fit(tuple(obs.T), data)
    predicted = np.empty(len(target))
    for start in range(0, len(target), prediction_block_size):
        if cancel is not None and cancel():
            raise InterruptedError("Equivalent-source prediction cancelled")
        stop = min(start + prediction_block_size, len(target))
        predicted[start:stop] = model.predict(tuple(target[start:stop].T))
    fitted = model.predict(tuple(obs.T))
    if not np.isfinite(predicted).all() or not np.isfinite(fitted).all():
        raise RuntimeError("Equivalent-source backend returned nonfinite predictions")
    return {
        "predicted": predicted,
        "training_residual": data - fitted,
        "source_coefficients": np.array(model.coefs_),
        "source_enu_m": points.copy(),
        "damping": damping,
        "engine": "Harmonica",
        "engine_version": harmonica.__version__,
        "kernel": "1/r, Cartesian equivalent sources; field units inherited",
    }

"""Explicit complex gain/offset calibration with real-imaginary covariance."""

import numpy as np

from ._array_contract import as_array
from ._calibration import covariance_array, gaussian_calibration, integer_budget


def fit_complex_response(
    reference,
    measured,
    covariance,
    *,
    maximum_condition=1e10,
    max_samples=100_000,
):
    """Fit measured = gain*reference + offset, four real parameters by GLS.

    Reference is exact and in the SAME phasor convention as measured. Covariance
    is for [real, imag], within-record correlation allowed. One fixed complex
    gain/offset only: group calibration records by frequency, geometry and time
    where justified. This does not infer primary fields or response units/ppm.
    """
    integer_budget(max_samples, "max_samples", 2)
    x, y = as_array(reference, complex), as_array(measured, complex)
    if (
        x.ndim != 1
        or x.shape != y.shape
        or not 2 <= len(x) <= max_samples
        or not np.isfinite(x).all()
        or not np.isfinite(y).all()
    ):
        raise ValueError(
            "Matching finite complex calibration vectors within budget required"
        )
    noise = covariance_array(covariance, 2, len(x), strict=True)
    design = np.zeros((len(x), 2, 4))
    design[:, 0, 0], design[:, 0, 1], design[:, 0, 2] = x.real, -x.imag, 1.0
    design[:, 1, 0], design[:, 1, 1], design[:, 1, 3] = x.imag, x.real, 1.0
    parameters, cov, diagnostics = gaussian_calibration(
        design,
        np.column_stack([y.real, y.imag]),
        noise,
        maximum_condition=maximum_condition,
    )
    gain, offset = complex(*parameters[:2]), complex(*parameters[2:])
    return {
        "gain": gain,
        "offset": offset,
        "coefficient_covariance": cov,
        "coefficient_order": ["gain_real", "gain_imag", "offset_real", "offset_imag"],
        "predicted": gain * x + offset,
        "residual": y - (gain * x + offset),
        **diagnostics,
        "uncertainty_note": "Reference exact; no reference/geometry/phase-convention uncertainty or calibration drift model",
    }


def apply_complex_response(
    measured,
    covariance,
    *,
    calibration,
    minimum_gain=1e-12,
    max_samples=3_000_000,
    block_size=4096,
    cancel=None,
):
    """Correct (measured-offset)/gain with first-order marginal covariance.

    Measurement and calibration errors must be independent. Calibration errors
    are shared between samples: cross-sample covariance is NOT returned. Do not
    apply to the calibration records themselves as independent held-out data.
    The [real,imag] covariance retains correlation; no magnitude-only shortcut.
    """
    integer_budget(max_samples, "max_samples")
    integer_budget(block_size, "block_size")
    y = as_array(measured, complex)
    if y.ndim != 1 or not 1 <= len(y) <= max_samples or not np.isfinite(y).all():
        raise ValueError(
            "Finite complex measurement vector within sample budget required"
        )
    gain, offset = complex(calibration["gain"]), complex(calibration["offset"])
    if (
        not np.isfinite([gain, offset]).all()
        or not np.isfinite(minimum_gain)
        or minimum_gain <= 0
        or abs(gain) < minimum_gain
    ):
        raise ValueError(
            "Finite gain/offset with gain above positive minimum_gain required"
        )
    coeff_cov = covariance_array(calibration["coefficient_covariance"], 4)
    noise = covariance_array(covariance, 2, len(y))
    inverse_gain = 1 / gain
    rotation = np.array(
        [
            [inverse_gain.real, -inverse_gain.imag],
            [inverse_gain.imag, inverse_gain.real],
        ]
    )
    corrected = np.empty(len(y), complex)
    propagated = np.empty((len(y), 2, 2))
    for first in range(0, len(y), block_size):
        if cancel is not None and cancel():
            raise InterruptedError("Complex response correction cancelled")
        stop = min(len(y), first + block_size)
        z = (y[first:stop] - offset) / gain
        derivatives = np.column_stack(
            [
                -z / gain,
                -1j * z / gain,
                np.full(len(z), -1 / gain),
                np.full(len(z), -1j / gain),
            ]
        )
        jacobian = np.stack([derivatives.real, derivatives.imag], axis=1)
        cov = np.einsum("ai,bij,cj->bac", rotation, noise[first:stop], rotation)
        cov += np.einsum(
            "bip,pq,bjq->bij", jacobian, coeff_cov, jacobian, optimize=True
        )
        corrected[first:stop], propagated[first:stop] = (
            z,
            (cov + cov.swapaxes(1, 2)) / 2,
        )
    if not np.isfinite(corrected).all() or not np.isfinite(propagated).all():
        raise ValueError(
            "Complex response propagation overflow; unstable gain or units"
        )
    return {
        "corrected": corrected,
        "covariance_real_imag": propagated,
        "uncertainty_note": "First-order marginal covariance with shared gain/offset errors; cross-sample covariance not returned",
    }

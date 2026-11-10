"""Experimental compact magnetic dipoles, not a UXO identification system."""

import numpy as np
from scipy.constants import mu_0
from scipy.optimize import least_squares

from ._array_contract import as_array
from ._calibration import integer_budget


def _xyz(value, name):
    value = as_array(value, float)
    if (
        value.ndim != 2
        or value.shape[1] != 3
        or not len(value)
        or not np.isfinite(value).all()
    ):
        raise ValueError(name + " must be a finite nonempty (n,3) ENU array")
    return value


def _check_cancel(canceled):
    if canceled is not None and canceled():
        raise RuntimeError("Compact magnetic model canceled")


def _field(observations, positions, moments, block_size, minimum_distance_m, canceled):
    field = np.empty(observations.shape)
    for first in range(0, len(observations), block_size):
        _check_cancel(canceled)
        r = observations[first : first + block_size, None, :] - positions[None, :, :]
        squared = np.sum(r * r, axis=2)
        if np.any(squared < minimum_distance_m**2):
            raise ValueError(
                "Dipole/observation separation is below the explicit minimum"
            )
        projection = np.sum(r * moments[None, :, :], axis=2)
        response = (
            3 * r * projection[:, :, None] / squared[:, :, None] ** 2.5
            - moments[None, :, :] / squared[:, :, None] ** 1.5
        )
        field[first : first + block_size] = (mu_0 / (4 * np.pi) * 1e9) * response.sum(
            axis=1
        )
    if not np.isfinite(field).all():
        raise ValueError("Dipole forward arithmetic exceeded finite range")
    _check_cancel(canceled)
    return field


def magnetic_dipole_field(
    observation_xyz,
    source_xyz,
    moments_a_m2,
    *,
    minimum_distance_m,
    block_size=4096,
    max_interactions=5_000_000,
    canceled=None,
):
    """ENU magnetic anomaly in nT from explicit point moments in A m2.

    Positions are metres in a shared local Cartesian frame. No IGRF, coordinate
    transformation, sensor calibration or regional background is subtracted.
    The dipole approximation requires target dimensions small versus distance;
    it does not identify shape, explosive content, or clearance status.
    """
    integer_budget(block_size, "Block size")
    integer_budget(max_interactions, "Maximum interactions")
    observations, sources, moments = (
        _xyz(v, n)
        for v, n in (
            (observation_xyz, "Observations"),
            (source_xyz, "Sources"),
            (moments_a_m2, "Moments"),
        )
    )
    minimum = float(minimum_distance_m)
    if moments.shape != sources.shape or not np.isfinite(minimum) or minimum <= 0:
        raise ValueError(
            "Aligned moments and sources plus positive finite minimum distance are required"
        )
    if len(sources) > 128 or len(observations) * len(sources) > max_interactions:
        raise ValueError("Dipole source/interaction budget exceeded")
    return dict(
        field_enu_nt=_field(
            observations, sources, moments, block_size, minimum, canceled
        ),
        recipe=dict(
            axes="east,north,up",
            position_units="m",
            moment_units="A m2",
            field_units="nT",
            mu0_si=float(mu_0),
            minimum_distance_m=minimum,
            scope="Point dipoles only; no UXO classification or safety certification",
        ),
    )


def fit_magnetic_dipoles(
    observation_xyz,
    observed_nt,
    data_std_nt,
    initial_xyz,
    initial_moments_a_m2,
    position_lower,
    position_upper,
    moment_lower,
    moment_upper,
    *,
    minimum_distance_m,
    component="vector",
    inclination=None,
    declination=None,
    max_forward_calls=2000,
    max_total_interactions=100_000_000,
    max_nfev=100,
    rank_tolerance=1e-8,
    canceled=None,
):
    """Bounded local nonlinear fit of a caller-selected number of dipoles.

    Explicit seeds, position/moment bounds and positive independent data std
    are mandatory. Sources must stay below every observation by the explicit
    minimum distance. vector fits ENU (n,3); total fits the small-anomaly
    projection along supplied grid-north I/D, not the exact total vector norm.
    No regional/background term is inferred. Local covariance is conditional
    on fixed geometry/noise and a linearized full-rank Jacobian, not posterior
    target probability. Rank deficiency makes success false. No automatic
    source-number selection, source identity, UXO/AGC classification or EM61.
    """
    for value, name in (
        (max_forward_calls, "Maximum forward calls"),
        (max_total_interactions, "Maximum total interactions"),
        (max_nfev, "Maximum evaluations"),
    ):
        integer_budget(value, name)
    observations, positions, moments = (
        _xyz(v, n)
        for v, n in (
            (observation_xyz, "Observations"),
            (initial_xyz, "Initial sources"),
            (initial_moments_a_m2, "Initial moments"),
        )
    )
    if positions.shape != moments.shape or len(positions) > 16:
        raise ValueError(
            "One to sixteen explicitly seeded sources with matching moments are supported"
        )
    minimum, tolerance = float(minimum_distance_m), float(rank_tolerance)
    if (
        not np.isfinite([minimum, tolerance]).all()
        or minimum <= 0
        or not 0 < tolerance < 1
    ):
        raise ValueError("Positive distance and rank tolerance in (0,1) are required")
    shape = positions.shape
    bounds = [
        np.broadcast_to(as_array(value, float), shape).copy()
        for value in (position_lower, position_upper, moment_lower, moment_upper)
    ]
    lower, upper = (
        np.r_[bounds[0].ravel(), bounds[2].ravel()],
        np.r_[bounds[1].ravel(), bounds[3].ravel()],
    )
    initial = np.r_[positions.ravel(), moments.ravel()]
    if (
        not np.isfinite([*lower, *upper]).all()
        or np.any(lower >= upper)
        or np.any(initial < lower)
        or np.any(initial > upper)
    ):
        raise ValueError(
            "Finite strict bounds containing every initial position/moment are required"
        )
    if np.any(bounds[1][:, 2] >= observations[:, 2].min() - minimum):
        raise ValueError(
            "Source upper bounds must stay below all observations by the explicit minimum distance"
        )
    if component == "vector":
        projection = None
        expected_shape = observations.shape
    elif component == "total":
        if (
            inclination is None
            or declination is None
            or not np.isfinite([inclination, declination]).all()
            or not -90 <= inclination <= 90
            or not -180 <= declination <= 180
        ):
            raise ValueError(
                "Total-field fitting requires explicit finite grid-north inclination/declination"
            )
        inc, dec = np.deg2rad([inclination, declination])
        projection = np.array(
            [np.cos(inc) * np.sin(dec), np.cos(inc) * np.cos(dec), -np.sin(inc)]
        )
        expected_shape = (len(observations),)
    else:
        raise ValueError("Component must be vector or total")
    data = as_array(observed_nt, float)
    std = np.broadcast_to(as_array(data_std_nt, float), expected_shape)
    if (
        data.shape != expected_shape
        or not np.isfinite(data).all()
        or not np.isfinite(std).all()
        or np.any(std <= 0)
        or data.size < initial.size
    ):
        raise ValueError(
            "Aligned finite observations with positive independent standard deviations and sufficient data are required"
        )
    _check_cancel(canceled)
    interactions = len(observations) * len(positions)
    calls = 0
    count = len(positions) * 3
    # Numerical translation only: finite differences should not scale with UTM
    # eastings/northings. Return original coordinates and record the origin.
    origin = observations[0].copy()
    observations = observations - origin
    initial[:count] -= np.tile(origin, len(positions))
    lower[:count] -= np.tile(origin, len(positions))
    upper[:count] -= np.tile(origin, len(positions))
    if not np.isfinite(observations).all() or not np.isfinite([*lower, *upper]).all():
        raise ValueError("Coordinate translation exceeds finite range")

    def prediction(parameters):
        nonlocal calls
        _check_cancel(canceled)
        if (
            calls >= max_forward_calls
            or (calls + 1) * interactions > max_total_interactions
        ):
            raise RuntimeError("Compact fit forward/work budget exceeded")
        calls += 1
        field = _field(
            observations,
            parameters[:count].reshape(shape),
            parameters[count:].reshape(shape),
            4096,
            minimum,
            canceled,
        )
        return field if projection is None else field @ projection

    def residual(parameters):
        return ((prediction(parameters) - data) / std).ravel()

    fit = least_squares(
        residual,
        initial,
        bounds=(lower, upper),
        x_scale="jac",
        max_nfev=max_nfev,
        ftol=1e-10,
        xtol=1e-10,
        gtol=1e-10,
    )
    _check_cancel(canceled)
    if not np.isfinite(fit.jac).all():
        raise ValueError("Optimizer returned a nonfinite Jacobian")
    maxima = np.max(abs(fit.jac), axis=0)
    norms = maxima * np.linalg.norm(fit.jac / np.where(maxima > 0, maxima, 1.0), axis=0)
    safe_norms = np.where(norms > 0, norms, 1.0)
    _u, singular, vt = np.linalg.svd(fit.jac / safe_norms, full_matrices=False)
    rank = (
        int(np.count_nonzero(singular > tolerance * singular[0]))
        if singular.size and singular[0]
        else 0
    )
    full_rank = rank == initial.size
    covariance = None
    if full_rank and fit.success:
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            candidate = (
                ((vt.T / singular**2) @ vt) / safe_norms[:, None]
            ) / safe_norms[None, :]
        if np.isfinite(candidate).all():
            covariance = candidate
    predicted = prediction(fit.x)
    return dict(
        source_xyz=fit.x[:count].reshape(shape) + origin,
        moments_a_m2=fit.x[count:].reshape(shape),
        predicted_nt=predicted,
        residual_nt=predicted - data,
        success=bool(fit.success and full_rank),
        optimizer_success=bool(fit.success),
        locally_full_rank=full_rank,
        jacobian_rank=rank,
        local_covariance=covariance,
        local_covariance_available=covariance is not None,
        active_bounds=fit.active_mask,
        forward_calls=calls,
        optimizer_status=int(fit.status),
        optimizer_message=str(fit.message),
        recipe=dict(
            component=component,
            inclination=inclination,
            declination=declination,
            axes="east,north,up",
            position_units="m",
            moment_units="A m2",
            field_units="nT",
            minimum_distance_m=minimum,
            numerical_origin_enu_m=origin.tolist(),
            mu0_si=float(mu_0),
            initial_source_xyz=positions.tolist(),
            initial_moments_a_m2=moments.tolist(),
            parameter_order="all positions ENU, then all moments ENU",
            position_lower=bounds[0].tolist(),
            position_upper=bounds[1].tolist(),
            moment_lower=bounds[2].tolist(),
            moment_upper=bounds[3].tolist(),
            max_forward_calls=max_forward_calls,
            max_total_interactions=max_total_interactions,
            rank_tolerance=tolerance,
            covariance_scope="Local linearization, fixed independent noise, no geological/UXO probabilities",
            scope="Local seeded point-source fit, not shape/size/type or AGC classification",
        ),
    )

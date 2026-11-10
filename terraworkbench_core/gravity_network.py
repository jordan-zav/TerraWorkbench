"""Anchored land-gravity network adjustment and density regression.

Readings are calibrated mGal, times seconds. Drift is per instrument/session;
different sessions must have different IDs. No tide, instrument scale or
height correction is fabricated. Known station anchors are exact constraints.
"""

import numpy as np

from ._array_contract import as_array


def adjust_gravity_network(
    station_ids,
    instrument_ids,
    times_s,
    readings_mgal,
    reading_std_mgal,
    *,
    anchors_mgal,
    anchor_std_mgal=None,
    drift_degree=1,
    max_elements=2_000_000,
):
    """Weighted station+instrument-offset+polynomial-drift adjustment.

    A single reading equation is reading=g_station+offset_inst+drift_inst(t).
    Times are centered/scaled per instrument for conditioning; coefficients
    use normalized time. Rank deficiency/disconnected unanchored components
    are errors. Formal covariance assumes independent absolute reading errors;
    Anchors are exact unless anchor_std_mgal supplies a positive standard
    deviation per anchor; then anchor observations enter the GLS system and
    their uncertainty propagates to all station and drift estimates. Anchor
    errors are independent of each other and of instrument readings. Correlated
    reference/instrument errors require an explicitly different noise model.
    """
    stations, instruments = as_array(station_ids), as_array(instrument_ids)
    times, readings, std = (
        as_array(v, float) for v in (times_s, readings_mgal, reading_std_mgal)
    )
    if (
        stations.ndim != 1
        or len(stations) < 2
        or instruments.shape != stations.shape
        or times.shape != stations.shape
        or readings.shape != stations.shape
        or std.shape != stations.shape
        or not all(np.isfinite(v).all() for v in (times, readings, std))
        or np.any(std <= 0)
    ):
        raise ValueError(
            "Matching station/instrument IDs, finite observations/times and positive errors required"
        )
    if stations.dtype.kind not in "USiu" or instruments.dtype.kind not in "USiu":
        raise ValueError("Use string or integer station/instrument identifiers")
    if (
        isinstance(drift_degree, bool)
        or not isinstance(drift_degree, (int, np.integer))
        or drift_degree not in (0, 1, 2)
    ):
        raise ValueError("drift_degree must be 0, 1 or 2")
    unique_station = np.unique(stations)
    unique_instrument, instrument_index = np.unique(instruments, return_inverse=True)
    if not anchors_mgal or not all(k in unique_station for k in anchors_mgal):
        raise ValueError(
            "At least one known station anchor, all in the network, is required"
        )
    if not all(np.isfinite(v) for v in anchors_mgal.values()):
        raise ValueError("Anchors must be finite calibrated mGal")
    soft_anchors = anchor_std_mgal is not None
    if soft_anchors and (
        not isinstance(anchor_std_mgal, dict)
        or set(anchor_std_mgal) != set(anchors_mgal)
        or not all(np.isfinite(v) and v > 0 for v in anchor_std_mgal.values())
    ):
        raise ValueError("Supply a positive finite standard deviation for every anchor")
    unknown = (
        list(unique_station)
        if soft_anchors
        else [s for s in unique_station if s not in anchors_mgal]
    )
    columns = {s: i for i, s in enumerate(unknown)}
    n_model = len(unknown) + len(unique_instrument) * (drift_degree + 1)
    n_prior = len(anchors_mgal) if soft_anchors else 0
    if n_model < 1 or (len(times) + n_prior) * n_model + 4 * n_model**2 > max_elements:
        raise ValueError("Dense gravity adjustment budget exceeded")
    design = np.zeros((len(times), n_model))
    target = readings.copy()
    for row, station in enumerate(stations):
        if station in anchors_mgal and not soft_anchors:
            target[row] -= anchors_mgal[station]
        else:
            design[row, columns[station]] = 1
    origins, scales = [], []
    for i, instrument in enumerate(unique_instrument):
        take = instrument_index == i
        origin = np.mean(times[take])
        scale = np.ptp(times[take])
        if scale == 0:
            scale = 1.0
        normalized = (times[take] - origin) / scale
        offset = len(unknown) + i * (drift_degree + 1)
        design[take, offset : offset + drift_degree + 1] = normalized[
            :, None
        ] ** np.arange(drift_degree + 1)
        origins.append(origin)
        scales.append(scale)
    weighted = design / std[:, None]
    weighted_target = target / std
    anchor_order = list(anchors_mgal)
    if soft_anchors:
        prior = np.zeros((n_prior, n_model))
        for i, station in enumerate(anchor_order):
            prior[i, columns[station]] = 1.0
        anchor_error = np.array([anchor_std_mgal[s] for s in anchor_order])
        anchor_values = np.array([anchors_mgal[s] for s in anchor_order])
        weighted = np.vstack([weighted, prior / anchor_error[:, None]])
        weighted_target = np.r_[weighted_target, anchor_values / anchor_error]
    parameters, _, rank, singular = np.linalg.lstsq(
        weighted, weighted_target, rcond=None
    )
    if rank != n_model:
        raise ValueError(
            "Rank-deficient gravity network: check ties, repeated anchors and drift order"
        )
    dof = len(weighted_target) - rank
    _, _, vh = np.linalg.svd(weighted, full_matrices=False)
    covariance = (vh.T / singular**2) @ vh
    residual = target - design @ parameters
    gravity = np.array(
        [
            anchors_mgal[s]
            if s in anchors_mgal and not soft_anchors
            else parameters[columns[s]]
            for s in unique_station
        ]
    )
    gravity_std = np.array(
        [
            0.0
            if s in anchors_mgal and not soft_anchors
            else np.sqrt(covariance[columns[s], columns[s]])
            for s in unique_station
        ]
    )
    anchor_residual = (
        anchor_values - prior @ parameters
        if soft_anchors
        else np.zeros(len(anchor_order))
    )
    chi_readings = float(np.sum((residual / std) ** 2))
    chi_anchors = (
        float(np.sum((anchor_residual / anchor_error) ** 2)) if soft_anchors else 0.0
    )
    return {
        "station_ids": unique_station,
        "gravity_mgal": gravity,
        "formal_std_mgal": gravity_std,
        "instrument_ids": unique_instrument,
        "drift_degree": drift_degree,
        "drift_coefficients_mgal": parameters[len(unknown) :].reshape(
            -1, drift_degree + 1
        ),
        "time_origins_s": np.array(origins),
        "time_scales_s": np.array(scales),
        "residual_mgal": residual,
        "chi_squared": chi_readings + chi_anchors,
        "chi_squared_readings": chi_readings,
        "chi_squared_anchors": chi_anchors,
        "anchor_order": anchor_order,
        "anchor_residual_mgal": anchor_residual,
        "degrees_of_freedom": dof,
        "covariance": covariance,
        "condition": float(singular[0] / singular[-1]),
        "anchors_are_exact": not soft_anchors,
    }


def fit_bouguer_density(
    gravity_mgal, unit_density_effect_mgal_per_kg_m3, *, gravity_std_mgal, nuisance=None
):
    """Fit g=rho*effect+nuisance*coeff, with explicit unit-density correction.

    Parasnis-style regression; effect must be supplied consistently from the
    chosen slab/terrain model. Default nuisance is an intercept. Geological
    signals correlated with topography bias the estimate; uncertainty is only
    conditional WLS, not evidence for a unique physical subsurface density.
    """
    g, effect, std = (
        as_array(v, float)
        for v in (gravity_mgal, unit_density_effect_mgal_per_kg_m3, gravity_std_mgal)
    )
    if g.ndim != 1 or g.size < 4 or effect.shape != g.shape or std.shape != g.shape:
        raise ValueError("At least four matching gravity/effect/error samples required")
    background = np.ones((g.size, 1)) if nuisance is None else as_array(nuisance, float)
    if (
        background.ndim != 2
        or background.shape[0] != g.size
        or background.shape[1] + 2 > g.size
    ):
        raise ValueError(
            "Invalid nuisance design or insufficient residual degrees of freedom"
        )
    if not all(np.isfinite(v).all() for v in (g, effect, std, background)) or np.any(
        std <= 0
    ):
        raise ValueError("Finite inputs and positive gravity errors required")
    # Scale density column to g/cm3-sized coefficients for numerical stability.
    design = np.column_stack([1000 * effect, background])
    weighted = design / std[:, None]
    fit, _, rank, _ = np.linalg.lstsq(weighted, g / std, rcond=None)
    if rank != design.shape[1]:
        raise ValueError("Density effect is not separable from nuisance terms")
    covariance = np.linalg.inv(weighted.T @ weighted)
    residual = g - design @ fit
    return {
        "density_kg_m3": float(1000 * fit[0]),
        "conditional_density_std_kg_m3": float(1000 * np.sqrt(covariance[0, 0])),
        "nuisance_coefficients": fit[1:],
        "residual_mgal": residual,
        "chi_squared": float(np.sum((residual / std) ** 2)),
        "physical_positive_density": bool(fit[0] > 0),
        "warning": "Topography-correlated geology can bias this conditional regression",
    }

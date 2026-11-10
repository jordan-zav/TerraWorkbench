"""Cartesian static elastic thin-plate flexure with explicit periodic boundaries.

D nabla^4 w + delta_rho*g*w = pressure, w positive DOWN. Uniform elastic
thickness and restoring contrast, no membrane stress, viscosity or load feedback.
Input is prescribed net pressure in Pa, NOT unlabelled topography/density.
"""

import numpy as np

from ._array_contract import as_array
from ._calibration import integer_budget


def _setup(
    load_pa,
    spacing_m,
    young_modulus_pa,
    poisson_ratio,
    restoring_contrast_kg_m3,
    gravity_m_s2,
    max_cells,
):
    integer_budget(max_cells, "max_cells")
    load, ds = as_array(load_pa, float), as_array(spacing_m, float)
    if (
        load.ndim != 2
        or min(load.shape) < 2
        or load.size > max_cells
        or not np.isfinite(load).all()
    ):
        raise ValueError("Complete finite 2D pressure grid within cell budget required")
    if ds.shape != (2,) or not np.isfinite(ds).all() or np.any(ds <= 0):
        raise ValueError("Positive metric spacing (dy,dx) required")
    if (
        not np.isfinite(
            [young_modulus_pa, poisson_ratio, restoring_contrast_kg_m3, gravity_m_s2]
        ).all()
        or young_modulus_pa <= 0
        or not -1 < poisson_ratio < 0.5
        or restoring_contrast_kg_m3 <= 0
        or gravity_m_s2 <= 0
    ):
        raise ValueError(
            "Positive modulus/density contrast/gravity and -1 < Poisson ratio < .5 required"
        )
    ky = 2 * np.pi * np.fft.fftfreq(load.shape[0], ds[0])
    kx = 2 * np.pi * np.fft.fftfreq(load.shape[1], ds[1])
    k4 = (ky[:, None] ** 2 + kx[None, :] ** 2) ** 2
    foundation = restoring_contrast_kg_m3 * gravity_m_s2
    rigidity_per_te3 = young_modulus_pa / (12 * (1 - poisson_ratio**2))
    if (
        not np.isfinite(foundation)
        or not np.isfinite(rigidity_per_te3)
        or not np.isfinite(k4).all()
    ):
        raise ValueError("Flexural parameters overflow; check metric scales")
    return load, ds, k4, foundation, rigidity_per_te3


def _transfer(thickness, k4, foundation, rigidity_per_te3):
    if not np.isscalar(thickness) or not np.isfinite(thickness) or thickness < 0:
        raise ValueError("Nonnegative finite elastic thickness in metres required")
    with np.errstate(over="ignore", invalid="ignore"):
        rigidity = rigidity_per_te3 * np.float64(thickness) ** 3
        denominator = rigidity * k4 + foundation
    if not np.isfinite(rigidity) or not np.isfinite(denominator).all():
        raise ValueError("Flexural rigidity/transfer overflow")
    return 1 / denominator, float(rigidity)


def thin_plate_flexure(
    load_pa,
    spacing_m,
    *,
    elastic_thickness_m,
    young_modulus_pa,
    poisson_ratio,
    restoring_contrast_kg_m3,
    gravity_m_s2=9.80665,
    max_cells=1_000_000,
    cancel=None,
):
    """Static periodic elastic response to a complete prescribed pressure grid.

    FFT axes are row-northing and column-easting, spacing (dy,dx) in metres.
    Rigidity D=E*Te^3/[12*(1-nu^2)] in N m. No taper/padding, mean removal or
    missing-load filling. Zero thickness gives local pressure/(delta_rho*g).
    Mean load remains compensated at every thickness. Edges repeat periodically;
    design a regional load domain and check domain/refinement sensitivity.
    """
    load, ds, k4, foundation, scale = _setup(
        load_pa,
        spacing_m,
        young_modulus_pa,
        poisson_ratio,
        restoring_contrast_kg_m3,
        gravity_m_s2,
        max_cells,
    )
    transfer, rigidity = _transfer(elastic_thickness_m, k4, foundation, scale)
    if cancel is not None and cancel():
        raise InterruptedError("Flexure cancelled")
    displacement = np.fft.ifft2(np.fft.fft2(load) * transfer).real
    if cancel is not None and cancel():
        raise InterruptedError("Flexure cancelled")
    if not np.isfinite(displacement).all():
        raise ValueError("Flexural response overflows; rescale prescribed pressure")
    return {
        "displacement_down_m": displacement,
        "transfer_m_per_pa": transfer,
        "flexural_rigidity_n_m": rigidity,
        "elastic_thickness_m": elastic_thickness_m,
        "spacing_m": ds,
        "boundary": "periodic; no implicit padding/taper/detrend",
        "foundation_stiffness_pa_per_m": foundation,
        "model": "static uniform isotropic elastic thin plate; prescribed net load",
    }


def scan_elastic_thickness(
    load_pa,
    observed_down_m,
    observation_std_m,
    spacing_m,
    *,
    candidate_thicknesses_m,
    young_modulus_pa,
    poisson_ratio,
    restoring_contrast_kg_m3,
    gravity_m_s2=9.80665,
    observation_mask=None,
    max_cells=1_000_000,
    max_work=50_000_000,
    cancel=None,
):
    """Explicit finite thickness scan against DOWN-positive displacement, not gravity.

    Conditional independent Gaussian data errors, fixed load/material/density.
    Returns the full misfit curve, best supplied candidate, ties and edge flags;
    not geological Te uncertainty, continuous optimization or an inferred prior.
    Mask can exclude missing observations, never missing pressure cells. No offset
    is fitted, no mean is removed. A uniform load contains no Te information.
    """
    integer_budget(max_work, "max_work")
    load, ds, k4, foundation, scale = _setup(
        load_pa,
        spacing_m,
        young_modulus_pa,
        poisson_ratio,
        restoring_contrast_kg_m3,
        gravity_m_s2,
        max_cells,
    )
    candidates = as_array(candidate_thicknesses_m, float)
    observed, std = as_array(observed_down_m, float), as_array(observation_std_m, float)
    if (
        candidates.ndim != 1
        or not 2 <= len(candidates) <= 1000
        or not np.isfinite(candidates).all()
        or np.any(candidates < 0)
        or np.any(np.diff(candidates) <= 0)
    ):
        raise ValueError(
            "2..1000 strictly increasing nonnegative candidate thicknesses required"
        )
    if len(candidates) * load.size > max_work:
        raise ValueError("Flexural candidate/cell work budget exceeded")
    if std.ndim == 0:
        std = np.broadcast_to(std, load.shape)
    mask = (
        np.ones(load.shape, bool)
        if observation_mask is None
        else as_array(observation_mask)
    )
    if (
        observed.shape != load.shape
        or std.shape != load.shape
        or mask.shape != load.shape
        or mask.dtype.kind != "b"
        or mask.sum() < 2
    ):
        raise ValueError(
            "Matching observations/errors and boolean observation mask required"
        )
    if (
        not np.isfinite(observed[mask]).all()
        or not np.isfinite(std[mask]).all()
        or np.any(std[mask] <= 0)
    ):
        raise ValueError(
            "Finite observations and positive errors on explicit observation mask required"
        )
    if cancel is not None and cancel():
        raise InterruptedError("Elastic thickness scan cancelled")
    load_fft = np.fft.fft2(load)
    chi_squared = np.empty(len(candidates))
    best_prediction = None
    best_chi = np.inf
    for i, thickness in enumerate(candidates):
        if cancel is not None and cancel():
            raise InterruptedError("Elastic thickness scan cancelled")
        transfer, _ = _transfer(thickness, k4, foundation, scale)
        predicted = np.fft.ifft2(load_fft * transfer).real
        residual = (predicted[mask] - observed[mask]) / std[mask]
        chi_squared[i] = residual @ residual
        if chi_squared[i] < best_chi:
            best_chi, best_prediction = chi_squared[i], predicted
    if not np.isfinite(chi_squared).all():
        raise ValueError("Flexural scan overflows; check load/data/error units")
    if cancel is not None and cancel():
        raise InterruptedError("Elastic thickness scan cancelled")
    best = int(np.argmin(chi_squared))
    ties = np.flatnonzero(
        np.isclose(chi_squared, chi_squared[best], rtol=1e-10, atol=1e-12)
    )
    return {
        "candidate_thicknesses_m": candidates.copy(),
        "chi_squared": chi_squared,
        "best_elastic_thickness_m": float(candidates[best]),
        "best_displacement_down_m": best_prediction,
        "best_on_scan_boundary": best in (0, len(candidates) - 1),
        "indistinguishable_candidate_indices": ties,
        "number_observations": int(mask.sum()),
        "boundary": "periodic; no implicit padding/taper/detrend",
        "uncertainty_note": "Conditional finite-grid misfit, not continuous or geological uncertainty; inspect whole curve and load-domain sensitivity",
    }

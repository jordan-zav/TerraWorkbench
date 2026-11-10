"""Prescribed self-potential currents in a finite heterogeneous 3D conductor.

SimPEG cell-centred finite volumes; -div(sigma grad(phi))=q, q A/m^3.
All exterior faces are insulating. Conductivity is fixed, isotropic, positive
per cell. No air/topography masking, electrokinetic inference or open infinity.
"""

import numpy as np
from scipy.sparse.linalg import splu

from ._array_contract import as_array
from ._calibration import integer_budget
from .inversion_diagnostics import linear_resolution


def _setup(
    mesh_widths,
    mesh_origin,
    conductivity_s_m,
    observation_m,
    reference_m,
    max_cells,
    max_data,
    cancel,
):
    integer_budget(max_cells, "max_cells", 2)
    integer_budget(max_data, "max_data")
    if len(mesh_widths) != 3:
        raise ValueError("Three ENU mesh width vectors required")
    widths = [as_array(a, float) for a in mesh_widths]
    origin = as_array(mesh_origin, float)
    if (
        any(
            a.ndim != 1 or len(a) < 2 or not np.isfinite(a).all() or np.any(a <= 0)
            for a in widths
        )
        or origin.shape != (3,)
        or not np.isfinite(origin).all()
    ):
        raise ValueError(
            "At least two positive finite widths per axis and finite ENU origin required"
        )
    cells = int(np.prod([len(a) for a in widths]))
    if cells > max_cells:
        raise ValueError("SP PDE cell budget exceeded")
    sigma = as_array(conductivity_s_m, float)
    if sigma.shape != (cells,) or not np.isfinite(sigma).all() or np.any(sigma <= 0):
        raise ValueError(
            "Positive finite conductivity per cell in Fortran order required"
        )
    obs, ref = as_array(observation_m, float), as_array(reference_m, float)
    if obs.ndim != 2 or obs.shape[1] != 3 or not 1 <= len(obs) <= max_data:
        raise ValueError("Observation ENU triples within data budget required")
    if ref.shape == (3,):
        ref = np.broadcast_to(ref, obs.shape)
    if (
        ref.shape != obs.shape
        or not np.isfinite(obs).all()
        or not np.isfinite(ref).all()
    ):
        raise ValueError("Finite common or per-observation reference ENU required")
    low = origin + np.array([a[0] / 2 for a in widths])
    high = origin + np.array([a.sum() - a[-1] / 2 for a in widths])
    if any(np.any(p < low) or np.any(p > high) for p in (obs, ref)):
        raise ValueError(
            "Electrodes must lie inside cell-centre bounds; no extrapolation/snapping"
        )
    if cancel is not None and cancel():
        raise InterruptedError("SP PDE cancelled")
    try:
        import simpeg
        from discretize import TensorMesh
        from simpeg.electromagnetics.static.self_potential import (
            Simulation3DCellCentered,
        )
    except ImportError as error:
        raise ImportError("SP PDE requires terraworkbench-core[electrical]") from error
    if not simpeg.__version__.startswith("0.25."):
        raise RuntimeError("SP PDE adapter requires SimPEG 0.25.x")
    mesh = TensorMesh(widths, x0=origin)
    simulation = Simulation3DCellCentered(mesh, sigma=sigma, bc_type="Neumann")
    projection = mesh.get_interpolation_matrix(
        obs, "CC"
    ) - mesh.get_interpolation_matrix(ref, "CC")
    return mesh, simulation, projection, simpeg.__version__


def _sources(values, mesh, max_parameters, max_elements):
    q = as_array(values, float)
    if (
        q.ndim != 2
        or q.shape[0] != mesh.n_cells
        or not 1 <= q.shape[1] <= max_parameters
        or not np.isfinite(q).all()
    ):
        raise ValueError(
            "Finite cell/source-template matrix within parameter budget required"
        )
    if q.size > max_elements:
        raise ValueError("SP source-template element budget exceeded")
    currents = mesh.cell_volumes[:, None] * q
    net = currents.sum(axis=0)
    if not np.isfinite(currents).all() or np.any(
        abs(net) > 1e-10 * np.maximum(abs(currents).sum(axis=0), 1e-30)
    ):
        raise ValueError("Each source must conserve total current in insulating domain")
    return q, currents


def _solve(mesh, simulation, projection, currents, cancel):
    if cancel is not None and cancel():
        raise InterruptedError("SP PDE cancelled")
    # SimPEG pins row zero for Neumann nullspace. Set the matching gauge RHS
    # explicitly to zero; the omitted physical equation follows from neutrality.
    matrix = simulation.getA().tocsc()
    factor = splu(matrix)
    prediction = np.empty((projection.shape[0], currents.shape[1]))
    try:
        for first in range(0, currents.shape[1], 8):
            if cancel is not None and cancel():
                raise InterruptedError("SP PDE cancelled")
            stop = min(currents.shape[1], first + 8)
            rhs = currents[:, first:stop].copy()
            rhs[0] = 0.0
            prediction[:, first:stop] = projection @ factor.solve(rhs)
    finally:
        del factor
    if cancel is not None and cancel():
        raise InterruptedError("SP PDE cancelled")
    if not np.isfinite(prediction).all():
        raise RuntimeError("SP PDE returned nonfinite potentials")
    return prediction


def _metadata(version):
    return {
        "engine": "SimPEG cell-centred finite volumes with SciPy sparse LU",
        "engine_version": version,
        "boundary": "finite box; zero normal current on ALL exterior faces",
        "reference_convention": "V(observation)-V(reference), volts",
        "model": "fixed positive isotropic conductivity, prescribed volumetric current sources",
        "memory_note": "Structural budgets, not a peak sparse-LU RAM guarantee",
    }


def sp_pde_forward(
    mesh_widths,
    mesh_origin,
    conductivity_s_m,
    source_density_a_m3,
    observation_m,
    reference_m,
    *,
    max_cells=10000,
    max_data=100000,
    cancel=None,
):
    """Potential differences from neutral prescribed cell currents in 3D.

    q is A/m^3, conductivity S/m, mesh metres ENU, arrays in discretize Fortran
    cell order. Positive q injects current and increases local potential.
    No Robin/open boundary: all six sides are insulating, not an infinite
    half-space. Check domain sensitivity before interpreting a survey.
    Electrodes must lie within cell-centre bounds, with no implicit snapping.
    """
    setup = _setup(
        mesh_widths,
        mesh_origin,
        conductivity_s_m,
        observation_m,
        reference_m,
        max_cells,
        max_data,
        cancel,
    )
    mesh, simulation, projection, version = setup
    q = as_array(source_density_a_m3, float)
    if q.shape != (mesh.n_cells,):
        raise ValueError("One source density per mesh cell required")
    _, currents = _sources(q[:, None], mesh, 1, max_cells)
    prediction = _solve(mesh, simulation, projection, currents, cancel)[:, 0]
    return {
        "potential_difference_v": prediction,
        "net_current_a": float(currents.sum()),
        **_metadata(version),
    }


def fit_sp_pde_sources(
    mesh_widths,
    mesh_origin,
    conductivity_s_m,
    source_templates_a_m3,
    observation_m,
    reference_m,
    observed_v,
    data_std_v,
    *,
    reference_coefficients,
    beta,
    regularization=None,
    max_cells=10000,
    max_data=100000,
    max_parameters=32,
    max_elements=2_000_000,
    cancel=None,
):
    """Linear Gaussian fit of prescribed neutral source-template amplitudes.

    Conductivity/geometry fixed. Templates are A/m^3 per unit coefficient, each
    individually neutral. beta and reference coefficients mandatory; beta>0,
    L defaults to identity (not spatial smoothing). Signed amplitudes, no bounds.
    One PDE factorization shared by source RHS blocks. Dense sensitivity budgets
    and conditional covariance; NOT inversion of conductivity, hydraulic head,
    coupling coefficients or a unique geological/electrokinetic source model.
    """
    integer_budget(max_parameters, "max_parameters")
    integer_budget(max_elements, "max_elements")
    mesh, simulation, projection, version = _setup(
        mesh_widths,
        mesh_origin,
        conductivity_s_m,
        observation_m,
        reference_m,
        max_cells,
        max_data,
        cancel,
    )
    q, currents = _sources(source_templates_a_m3, mesh, max_parameters, max_elements)
    k = q.shape[1]
    observed, std, prior = [
        as_array(a, float) for a in (observed_v, data_std_v, reference_coefficients)
    ]
    reg = np.eye(k) if regularization is None else as_array(regularization, float)
    if (
        observed.shape != (projection.shape[0],)
        or std.shape != observed.shape
        or prior.shape != (k,)
        or not all(np.isfinite(a).all() for a in (observed, std, prior))
        or np.any(std <= 0)
        or not np.isfinite(beta)
        or beta <= 0
    ):
        raise ValueError(
            "Matching finite observations/positive errors/reference and beta>0 required"
        )
    if reg.ndim != 2 or reg.shape[1] != k or not np.isfinite(reg).all():
        raise ValueError(
            "Explicit finite L operator with one column per source coefficient required"
        )
    if q.size + projection.shape[0] * k + reg.size + 6 * k * k > max_elements:
        raise ValueError("SP source/sensitivity/covariance element budget exceeded")
    sensitivity = _solve(mesh, simulation, projection, currents, cancel)
    audit = linear_resolution(
        sensitivity, std, reg, beta=beta, max_elements=max_elements
    )
    rhs = sensitivity.T @ (observed / std**2) + beta * (reg.T @ reg) @ prior
    coefficients = audit["posterior_covariance"] @ rhs
    predicted = sensitivity @ coefficients
    if cancel is not None and cancel():
        raise InterruptedError("SP PDE source fit cancelled")
    return {
        "source_coefficients": coefficients,
        "source_density_a_m3": q @ coefficients,
        "predicted_v": predicted,
        "sensitivity_v_per_coefficient": sensitivity,
        "data_chi_squared": float(np.sum(((predicted - observed) / std) ** 2)),
        "reference_coefficients": prior.copy(),
        **audit,
        **_metadata(version),
        "uncertainty_note": "Fixed linear Gaussian source coefficients, independent data errors; excludes conductivity/geometry/source-template uncertainty",
    }

"""Optional quasi-static 3D FDEM, tensor meshes, nonmagnetic isotropic media.

Metres ENU, S/m, Hz, magnetic-dipole moment A m^2 and SECONDARY B in teslas.
No displacement current, anisotropy, chargeability or automatic terrain/mesh
design. Small parameterized fits, not industrial matrix-free voxel inversion.
"""

import numpy as np
from scipy import sparse
from scipy.optimize import least_squares

from ._array_contract import as_array
from ._calibration import covariance_array, integer_budget


def _domain(
    mesh_widths,
    mesh_origin,
    active_cells,
    parameter_labels,
    max_cells,
    max_unknowns,
    max_parameters,
):
    for limit in (max_cells, max_unknowns, max_parameters):
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, np.integer))
            or limit < 1
        ):
            raise ValueError("Mesh/system/parameter budgets must be positive integers")
    if len(mesh_widths) != 3:
        raise ValueError("Three tensor-mesh width arrays required")
    widths = [as_array(a, float) for a in mesh_widths]
    origin = as_array(mesh_origin, float)
    if (
        any(
            a.ndim != 1 or not len(a) or not np.isfinite(a).all() or np.any(a <= 0)
            for a in widths
        )
        or origin.shape != (3,)
        or not np.isfinite(origin).all()
    ):
        raise ValueError("Positive finite widths and ENU origin in metres required")
    counts = [len(a) for a in widths]
    cells = int(np.prod(counts))
    edges = sum(
        counts[i] * np.prod([counts[j] + 1 for j in range(3) if j != i])
        for i in range(3)
    )
    if cells > max_cells or edges > max_unknowns:
        raise ValueError("FDEM mesh/edge-unknown budget exceeded")
    active = np.ones(cells, bool) if active_cells is None else as_array(active_cells)
    if active.shape != (cells,) or active.dtype.kind != "b" or not active.any():
        raise ValueError(
            "Nonempty boolean active-cell mask in discretize Fortran order required"
        )
    labels = (
        np.arange(active.sum())
        if parameter_labels is None
        else as_array(parameter_labels)
    )
    if labels.shape != (int(active.sum()),) or labels.dtype.kind not in "iu":
        raise ValueError("Integer parameter label per active cell required")
    unique = np.unique(labels)
    if (
        not np.array_equal(unique, np.arange(len(unique)))
        or len(unique) > max_parameters
    ):
        raise ValueError(
            "Labels must be contiguous from zero and within parameter budget"
        )
    return widths, origin, active, labels, len(unique), int(edges)


def _geometry(
    frequency_hz,
    source_m,
    receiver_m,
    origin,
    widths,
    moment,
    source_axis,
    receiver_axis,
):
    f = as_array(frequency_hz, float)
    tx, rx = as_array(source_m, float), as_array(receiver_m, float)
    if (
        f.ndim != 1
        or not 1 <= f.size <= 64
        or not np.isfinite(f).all()
        or np.any(f <= 0)
    ):
        raise ValueError("1..64 positive frequencies required")
    if tx.shape == (3,):
        tx = np.broadcast_to(tx, (f.size, 3))
    if rx.shape == (3,):
        rx = np.broadcast_to(rx, (f.size, 3))
    if (
        tx.shape != (f.size, 3)
        or rx.shape != tx.shape
        or not np.isfinite(tx).all()
        or not np.isfinite(rx).all()
    ):
        raise ValueError(
            "Source/receiver ENU triples or one triple per frequency row required"
        )
    upper = origin + np.array([a.sum() for a in widths])
    if (
        np.any(tx <= origin)
        or np.any(tx >= upper)
        or np.any(rx <= origin)
        or np.any(rx >= upper)
    ):
        raise ValueError("Source/receiver locations must be strictly inside the mesh")
    if np.any(np.linalg.norm(tx - rx, axis=1) == 0):
        raise ValueError("Coincident dipole/receiver is singular")
    if (
        not np.isfinite(moment)
        or moment <= 0
        or source_axis not in ("x", "y", "z")
        or receiver_axis not in ("x", "y", "z")
    ):
        raise ValueError("Positive dipole moment and explicit x/y/z axes required")
    return f, tx, rx


def fdem_3d_forward(
    mesh_widths,
    mesh_origin,
    frequency_hz,
    conductivity_s_m,
    *,
    source_m,
    receiver_m,
    active_cells=None,
    parameter_labels=None,
    moment_a_m2=1.0,
    source_axis="z",
    receiver_axis="z",
    air_conductivity_s_m=1e-8,
    max_cells=2000,
    max_unknowns=8000,
    max_parameters=2000,
    max_work=500000,
    cancel=None,
):
    """SimPEG electric-field formulation, analytic magnetic-dipole source.

    One transmitter/receiver per frequency row; common triples broadcast.
    Inactive cells are explicit air, active zones may have arbitrary 3D geometry.
    No hidden snapping or primary-field normalization/ppm. Source and receiver
    must stay inside the mesh; boundary distance and discretization convergence
    are caller responsibilities. LU fill-in is NOT bounded by work estimates.
    Cancellation is checked between frequency solves, not inside sparse LU.
    """
    widths, origin, active, labels, n, edges = _domain(
        mesh_widths,
        mesh_origin,
        active_cells,
        parameter_labels,
        max_cells,
        max_unknowns,
        max_parameters,
    )
    sigma = as_array(conductivity_s_m, float)
    if (
        sigma.shape != (n,)
        or not np.isfinite(sigma).all()
        or np.any(sigma <= 0)
        or not np.isfinite(air_conductivity_s_m)
        or air_conductivity_s_m <= 0
    ):
        raise ValueError(
            "Positive conductivity per explicit parameter and air conductivity required"
        )
    f, tx, rx = _geometry(
        frequency_hz,
        source_m,
        receiver_m,
        origin,
        widths,
        moment_a_m2,
        source_axis,
        receiver_axis,
    )
    if (
        isinstance(max_work, bool)
        or not isinstance(max_work, (int, np.integer))
        or max_work < 1
        or edges * len(f) > max_work
    ):
        raise ValueError("FDEM edge/data-row work budget exceeded")
    if cancel is not None and cancel():
        raise InterruptedError("FDEM 3D cancelled")
    try:
        import simpeg
        from discretize import TensorMesh
        from pymatsolver import SolverLU
        from simpeg import maps
        from simpeg.electromagnetics import frequency_domain as fd
    except ImportError as error:
        raise ImportError("FDEM 3D requires terraworkbench-core[em]") from error
    if not simpeg.__version__.startswith("0.25."):
        raise RuntimeError("FDEM 3D adapter requires SimPEG 0.25.x")
    mesh = TensorMesh(widths, x0=origin)
    basis = sparse.csr_matrix(
        (np.ones(len(labels)), (np.arange(len(labels)), labels)), shape=(len(labels), n)
    )
    mapping = (
        maps.InjectActiveCells(mesh, active, air_conductivity_s_m)
        * maps.ExpMap(nP=len(labels))
        * maps.LinearMap(basis)
    )
    prediction = np.empty(f.shape, complex)
    for frequency in np.unique(f):
        if cancel is not None and cancel():
            raise InterruptedError("FDEM 3D cancelled")
        rows = np.flatnonzero(f == frequency)
        sources = []
        for i in rows:
            receivers = [
                fd.receivers.PointMagneticFluxDensitySecondary(
                    rx[i][None, :], orientation=receiver_axis, component=part
                )
                for part in ("real", "imag")
            ]
            sources.append(
                fd.sources.MagDipole(
                    receivers,
                    frequency=float(frequency),
                    location=tx[i],
                    moment=moment_a_m2,
                    orientation=source_axis,
                )
            )
        simulation = fd.Simulation3DElectricField(
            mesh,
            survey=fd.Survey(sources),
            sigmaMap=mapping,
            solver=SolverLU,
            forward_only=False,
        )
        try:
            raw = as_array(simulation.dpred(np.log(sigma))).reshape(len(rows), 2)
            prediction[rows] = raw[:, 0] + 1j * raw[:, 1]
        finally:
            for factor in getattr(simulation, "Ainv", []):
                if factor is not None:
                    factor.clean()
    if cancel is not None and cancel():
        raise InterruptedError("FDEM 3D cancelled")
    if not np.isfinite(prediction).all():
        raise RuntimeError(
            "FDEM 3D returned nonfinite fields; check source singularities/mesh"
        )
    return {
        "secondary_b_t": prediction,
        "frequency_hz": f.copy(),
        "conductivity_s_m": sigma.copy(),
        "source_m": tx.copy(),
        "receiver_m": rx.copy(),
        "source_axis": source_axis,
        "receiver_axis": receiver_axis,
        "moment_a_m2": moment_a_m2,
        "engine": "SimPEG",
        "engine_version": simpeg.__version__,
        "earth_dimension": "3D",
        "formulation": "quasi-static electric-field EB; nonmagnetic isotropic conductivity",
        "solver": "SciPy sparse complex LU",
        "edge_unknowns": edges,
        "frequency_factorizations": len(np.unique(f)),
        "memory_note": "Structural budgets, not a peak sparse-LU RAM guarantee",
    }


def fit_fdem_3d_zones(
    mesh_widths,
    mesh_origin,
    frequency_hz,
    observed_secondary_b_t,
    *,
    real_std_t=None,
    imag_std_t=None,
    data_covariance_t2=None,
    initial_conductivity_s_m,
    reference_conductivity_s_m,
    beta,
    source_m,
    receiver_m,
    active_cells=None,
    parameter_labels=None,
    bounds_s_m=(1e-6, 10.0),
    max_evaluations=20,
    max_forward_evaluations=80,
    max_parameters=16,
    cancel=None,
    **forward_options,
):
    """Bounded local 3D zone fit with explicit log-conductivity L2 prior.

    Finite-difference Jacobian, counted forward-call budget including Jacobian
    evaluations. Not scalable voxel inversion. Supply independent real/imag
    standard errors OR data_covariance_t2 for [real,imag] per record, not both.
    Records are independent: shared-calibration cross-record errors are NOT
    represented by marginal 2x2 covariances. Geometry/source/air are fixed, no mesh
    refinement. beta/reference are mandatory; beta=0 explicitly disables prior.
    """
    integer_budget(max_parameters, "max_parameters")
    obs, initial, reference, limits = [
        as_array(a, dtype)
        for a, dtype in (
            (observed_secondary_b_t, complex),
            (initial_conductivity_s_m, float),
            (reference_conductivity_s_m, float),
            (bounds_s_m, float),
        )
    ]
    f = as_array(frequency_hz, float)
    if obs.ndim != 1 or not len(obs) or obs.shape != f.shape:
        raise ValueError("Matching complex data/frequency vectors required")
    if data_covariance_t2 is None:
        re, im = as_array(real_std_t, float), as_array(imag_std_t, float)
        if (
            re.shape != obs.shape
            or im.shape != obs.shape
            or not np.isfinite(re).all()
            or not np.isfinite(im).all()
            or np.any(re <= 0)
            or np.any(im <= 0)
        ):
            raise ValueError("Positive real/imaginary errors matching data required")
        factor = np.zeros((len(obs), 2, 2))
        factor[:, 0, 0], factor[:, 1, 1] = re, im
        noise_model = "Independent records and real/imaginary errors"
    else:
        if real_std_t is not None or imag_std_t is not None:
            raise ValueError(
                "Choose standard errors OR full real/imaginary covariance, not both"
            )
        factor = np.linalg.cholesky(
            covariance_array(data_covariance_t2, 2, len(obs), strict=True)
        )
        noise_model = (
            "Full within-record real/imaginary covariance; independent records"
        )
    if (
        obs.ndim != 1
        or obs.shape != f.shape
        or initial.ndim != 1
        or not 1 <= initial.size <= max_parameters
        or reference.shape != initial.shape
        or limits.shape != (2,)
        or not all(np.isfinite(a).all() for a in (obs, initial, reference, limits))
        or not 0 < limits[0] < limits[1]
        or np.any(initial <= limits[0])
        or np.any(initial >= limits[1])
        or np.any(reference <= 0)
        or not np.isfinite(beta)
        or beta < 0
    ):
        raise ValueError(
            "Matching complex data/errors, positive interior initial model/reference, beta and bounds required"
        )
    for limit in (max_evaluations, max_forward_evaluations):
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, np.integer))
            or not 1 <= limit <= 1000
        ):
            raise ValueError("Evaluation budgets must be integers in 1..1000")
    calls = 0
    engine_version = None

    def residual(model):
        nonlocal calls, engine_version
        if cancel is not None and cancel():
            raise InterruptedError("FDEM 3D fit cancelled")
        if calls >= max_forward_evaluations:
            raise RuntimeError("FDEM 3D forward-call budget exceeded")
        calls += 1
        result = fdem_3d_forward(
            mesh_widths,
            mesh_origin,
            f,
            np.exp(model),
            source_m=source_m,
            receiver_m=receiver_m,
            active_cells=active_cells,
            parameter_labels=parameter_labels,
            max_parameters=max_parameters,
            cancel=cancel,
            **forward_options,
        )
        engine_version = result["engine_version"]
        delta = result["secondary_b_t"] - obs
        whitened = np.linalg.solve(
            factor, np.column_stack([delta.real, delta.imag])[..., None]
        )[..., 0]
        return np.r_[
            whitened[:, 0],
            whitened[:, 1],
            np.sqrt(beta) * (model - np.log(reference)),
        ]

    fit = least_squares(
        residual, np.log(initial), bounds=np.log(limits), max_nfev=max_evaluations
    )
    ndata = len(obs)
    delta = np.einsum("nij,nj->ni", factor, fit.fun[: 2 * ndata].reshape(2, ndata).T)
    predicted = obs + delta[:, 0] + 1j * delta[:, 1]
    return {
        "conductivity_s_m": np.exp(fit.x),
        "predicted_secondary_b_t": predicted,
        "success": bool(fit.success),
        "message": fit.message,
        "forward_evaluations": calls,
        "optimizer_evaluations": fit.nfev,
        "data_chi_squared": float(np.sum(fit.fun[: 2 * ndata] ** 2)),
        "data_noise_model": noise_model,
        "weighted_log_parameter_jacobian": fit.jac,
        "active_bounds": fit.active_mask,
        "reference_conductivity_s_m": reference.copy(),
        "beta": beta,
        "engine": "SimPEG",
        "engine_version": engine_version,
        "earth_dimension": "3D",
        "warning": "Local parameterized fixed-geometry fit; uniqueness not established",
    }

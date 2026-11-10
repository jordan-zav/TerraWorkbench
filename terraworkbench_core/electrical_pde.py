"""Budgeted SimPEG DC and linearized static IP on 2.5D/3D tensor meshes.

Mesh coordinates: (x,z) for a y=0 survey in 2.5D, (east,north,up) for 3D.
Electrodes always use ENU triples in metres; no snapping/draping occurs.
Conductivity S/m, unit-current DC transfer resistance ohms, IP chargeability
V/V. Active cells represent the supplied terrain; inactive air is 1e-8 S/m.
No automatic CRS/datum conversion, mesh design or geological interpretation.
"""

import numpy as np
from scipy import sparse
from scipy.optimize import least_squares, lsq_linear

from ._array_contract import as_array
from .electrical import validate_abmn


def _setup(
    mesh_widths,
    mesh_origin,
    electrodes,
    abmn,
    *,
    active_cells,
    parameter_labels,
    max_cells,
    max_parameters,
    max_work,
    nky,
):
    if len(mesh_widths) not in (2, 3):
        raise ValueError("Specify tensor-mesh widths for (x,z) or (east,north,up)")
    widths = [as_array(a, float) for a in mesh_widths]
    if any(
        a.ndim != 1 or not len(a) or not np.isfinite(a).all() or np.any(a <= 0)
        for a in widths
    ):
        raise ValueError("Mesh widths must be nonempty positive metre vectors")
    origin = as_array(mesh_origin, float)
    if origin.shape != (len(widths),) or not np.isfinite(origin).all():
        raise ValueError("Mesh origin must match mesh dimension")
    for name, limit in (
        ("max_cells", max_cells),
        ("max_parameters", max_parameters),
        ("max_work", max_work),
    ):
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, np.integer))
            or limit < 1
        ):
            raise ValueError(name + " must be a positive integer")
    cells = int(np.prod([len(a) for a in widths]))
    if cells > max_cells:
        raise ValueError("PDE cell budget exceeded")
    xyz, q = validate_abmn(electrodes, abmn, space="full")
    # space='full' above only disables the planar restriction of the shared
    # index validator. The PDE below is a surface/air model, NOT full-space K.
    if len(widths) == 2 and np.any(abs(xyz[q[q >= 0], 1]) > 1e-8):
        raise ValueError("2.5D electrodes must lie in the y=0 plane")
    coordinates = xyz[:, [0, 2]] if len(widths) == 2 else xyz
    used = np.unique(q[q >= 0])
    upper = origin + np.array([a.sum() for a in widths])
    if np.any(coordinates[used] < origin - 1e-8) or np.any(
        coordinates[used] > upper + 1e-8
    ):
        raise ValueError("Used electrodes must be inside the supplied mesh bounds")
    if (
        isinstance(nky, bool)
        or not isinstance(nky, (int, np.integer))
        or not 5 <= nky <= 31
    ):
        raise ValueError("nky must be an integer in 5..31")
    nodes = int(np.prod([len(a) + 1 for a in widths]))
    work = nodes * len(q) * (nky if len(widths) == 2 else 1)
    if work > max_work:
        raise ValueError("PDE node/source/quadrature work budget exceeded")
    active = (
        np.ones(cells, dtype=bool) if active_cells is None else as_array(active_cells)
    )
    if active.shape != (cells,) or active.dtype.kind != "b" or not active.any():
        raise ValueError(
            "Active cells must be a nonempty boolean mask in discretize Fortran cell order"
        )
    labels = (
        np.arange(active.sum())
        if parameter_labels is None
        else as_array(parameter_labels)
    )
    if labels.shape != (int(active.sum()),) or labels.dtype.kind not in "iu":
        raise ValueError("parameter_labels must be integer per active cell")
    unique = np.unique(labels)
    if not np.array_equal(unique, np.arange(len(unique))):
        raise ValueError("Parameter labels must be contiguous from zero")
    if len(unique) > max_parameters:
        raise ValueError(
            "PDE parameter budget exceeded; use explicit zones or increase budget"
        )
    try:
        import simpeg
        from discretize import TensorMesh
        from pymatsolver import SolverLU
        from simpeg import maps
        from simpeg.electromagnetics.static import resistivity as dc
    except ImportError as error:
        raise ImportError(
            "PDE electrical methods require terraworkbench-core[electrical]"
        ) from error
    if not simpeg.__version__.startswith("0.25."):
        raise RuntimeError("Electrical PDE adapter requires SimPEG 0.25.x")
    mesh = TensorMesh(widths, x0=origin)
    basis = sparse.csr_matrix(
        (np.ones(len(labels)), (np.arange(len(labels)), labels)),
        shape=(len(labels), len(unique)),
    )
    sources = []
    for a, b, m, n in q:
        locations = coordinates[m][None, :]
        rx = (
            dc.receivers.Pole(locations, data_type="volt")
            if n == -1
            else dc.receivers.Dipole(
                locations, coordinates[n][None, :], data_type="volt"
            )
        )
        source = (
            dc.sources.Pole([rx], location=coordinates[a], current=1.0)
            if b == -1
            else dc.sources.Dipole(
                [rx], location_a=coordinates[a], location_b=coordinates[b], current=1.0
            )
        )
        sources.append(source)
    survey = dc.Survey(sources)
    options = dict(solver=SolverLU, storeJ=True)
    if len(widths) == 2:
        options["nky"] = int(nky)
    return dict(
        mesh=mesh,
        active=active,
        basis=basis,
        survey=survey,
        maps=maps,
        dc=dc,
        options=options,
        version=simpeg.__version__,
        n_parameters=len(unique),
        dimension="2.5D" if len(widths) == 2 else "3D",
        estimated_work=work,
    )


def _simulation(setup, *, ip=False, conductivity=None):
    maps, mesh, active, basis = (setup[k] for k in ("maps", "mesh", "active", "basis"))
    parameter_map = maps.LinearMap(basis)
    if ip:
        from simpeg.electromagnetics.static import induced_polarization

        cls = (
            induced_polarization.Simulation2DNodal
            if mesh.dim == 2
            else induced_polarization.Simulation3DNodal
        )
        sigma = np.full(mesh.nC, 1e-8)
        sigma[active] = basis @ conductivity
        eta_map = maps.InjectActiveCells(mesh, active, 0.0) * parameter_map
        # Apparent chargeability is normalized internally by the DC voltage,
        # not by a flat-earth geometric factor on topography.
        for source in setup["survey"].source_list:
            for rx in source.receiver_list:
                rx.data_type = "apparent_chargeability"
        return cls(
            mesh,
            survey=setup["survey"],
            sigma=sigma,
            etaMap=eta_map,
            **setup["options"],
        )
    cls = (
        setup["dc"].Simulation2DNodal
        if mesh.dim == 2
        else setup["dc"].Simulation3DNodal
    )
    sigma_map = (
        maps.InjectActiveCells(mesh, active, 1e-8)
        * maps.ExpMap(nP=int(active.sum()))
        * parameter_map
    )
    return cls(mesh, survey=setup["survey"], sigmaMap=sigma_map, **setup["options"])


def _clean(simulation):
    factors = getattr(simulation, "Ainv", None)
    if factors is not None:
        for factor in factors if isinstance(factors, list) else [factors]:
            if factor is not None:
                factor.clean()


def _values(values, setup, name, *, eta=False):
    value = as_array(values, float)
    if value.shape != (setup["n_parameters"],) or not np.isfinite(value).all():
        raise ValueError(name + " must match explicit parameter count")
    if np.any(value < 0 if eta else value <= 0) or (eta and np.any(value >= 1)):
        raise ValueError(name + " outside physical bounds")
    return value


def _metadata(setup):
    return dict(
        engine="SimPEG",
        engine_version=setup["version"],
        earth_dimension=setup["dimension"],
        solver="SciPy sparse LU via pymatsolver.SolverLU",
        axes="x,z (y=0)" if setup["mesh"].dim == 2 else "east,north,up",
        mesh_cells=setup["mesh"].nC,
        active_cells=setup["active"].copy(),
        estimated_node_source_work=setup["estimated_work"],
        memory_note="Budgets are structural work limits, NOT a peak sparse-LU RAM guarantee",
    )


def electrical_forward(
    mesh_widths,
    mesh_origin,
    electrodes,
    abmn,
    conductivity_s_m,
    *,
    active_cells=None,
    parameter_labels=None,
    chargeability_v_v=None,
    nky=11,
    max_cells=5000,
    max_parameters=5000,
    max_work=20_000_000,
    max_jacobian_elements=2_000_000,
    cancel=None,
):
    """DC resistance or LINEARIZED static apparent IP, tensor-mesh PDE.

    With chargeability_v_v, fixed DC conductivity and small-chargeability
    linearization are used. This is not a full Cole-Cole time/frequency decay.
    Air/topography are supplied by active_cells; mesh design and convergence
    remain caller responsibilities. No data or geometry is silently draped.
    """
    if cancel is not None and cancel():
        raise InterruptedError("Electrical PDE cancelled")
    setup = _setup(
        mesh_widths,
        mesh_origin,
        electrodes,
        abmn,
        active_cells=active_cells,
        parameter_labels=parameter_labels,
        max_cells=max_cells,
        max_parameters=max_parameters,
        max_work=max_work,
        nky=nky,
    )
    conductivity = _values(conductivity_s_m, setup, "conductivity_s_m")
    ip = chargeability_v_v is not None
    if (
        ip
        and len(setup["survey"].source_list) * setup["n_parameters"]
        > max_jacobian_elements
    ):
        raise ValueError("Static IP forward Jacobian budget exceeded")
    model = (
        _values(chargeability_v_v, setup, "chargeability_v_v", eta=True)
        if ip
        else np.log(conductivity)
    )
    simulation = _simulation(setup, ip=ip, conductivity=conductivity)
    try:
        predicted = as_array(simulation.dpred(model))
        if cancel is not None and cancel():
            raise InterruptedError("Electrical PDE cancelled")
        if not np.isfinite(predicted).all():
            raise RuntimeError("Electrical PDE returned nonfinite data")
        return {
            **_metadata(setup),
            "predicted": predicted,
            "quantity": "apparent_chargeability_v_v"
            if ip
            else "transfer_resistance_ohm",
            "conductivity_s_m": conductivity.copy(),
            "chargeability_v_v": model.copy() if ip else None,
            "ip_approximation": "linearized small chargeability" if ip else None,
        }
    finally:
        _clean(simulation)


def ip_sensitivity(mesh_widths, mesh_origin, electrodes, abmn, *, conductivity_s_m,
                   active_cells=None, parameter_labels=None, nky=11, max_cells=5000,
                   max_parameters=32, max_work=20_000_000, max_jacobian_elements=2_000_000,
                   cancel=None):
    """Normalized static-IP sensitivity for quasi-static dispersive-IP models.

    Rows follow ABMN and columns follow prescribed active cells/zones. Fixed
    conductivity/geometry, small-polarization approximation; no EM induction.
    """
    if cancel is not None and cancel():
        raise InterruptedError("IP sensitivity cancelled")
    from ._calibration import integer_budget
    integer_budget(max_jacobian_elements, "max_jacobian_elements")
    setup = _setup(mesh_widths, mesh_origin, electrodes, abmn, active_cells=active_cells,
                   parameter_labels=parameter_labels, max_cells=max_cells,
                   max_parameters=max_parameters, max_work=max_work, nky=nky)
    if len(abmn)*setup["n_parameters"] > max_jacobian_elements:
        raise ValueError("IP sensitivity Jacobian budget exceeded")
    conductivity = _values(conductivity_s_m, setup, "conductivity_s_m")
    simulation = _simulation(setup, ip=True, conductivity=conductivity)
    try:
        jacobian = as_array(simulation.getJ(np.zeros(setup["n_parameters"])))
        sensitivity = simulation._scale[:, None]*jacobian
        if not np.isfinite(sensitivity).all():
            raise RuntimeError("IP sensitivity returned nonfinite values")
        if cancel is not None and cancel():
            raise InterruptedError("IP sensitivity cancelled")
        return {**_metadata(setup), "sensitivity": sensitivity,
                "conductivity_s_m": conductivity.copy(), "units": "apparent V/V per intrinsic V/V",
                "approximation": "linearized small polarization; fixed conductivity and geometry"}
    finally:
        _clean(simulation)


def invert_electrical(
    mesh_widths,
    mesh_origin,
    electrodes,
    abmn,
    observed,
    *,
    data_std,
    initial,
    reference,
    beta,
    kind="dc",
    conductivity_s_m=None,
    active_cells=None,
    parameter_labels=None,
    regularization=None,
    bounds=None,
    nky=11,
    max_cells=5000,
    max_parameters=256,
    max_work=20_000_000,
    max_jacobian_elements=2_000_000,
    max_evaluations=30,
    max_forward_evaluations=100,
    cancel=None,
):
    """Bounded regularized DC log-sigma or static-IP eta inversion.

    DC initial/reference/bounds use S/m; IP uses V/V with supplied fixed
    conductivity_s_m. beta and reference are mandatory. Default regularizer
    is identity in parameter space (NOT spatial smoothing or cell-volume
    weighting); caller may supply a physical prior operator explicitly.
    Optional parameter_labels define contiguous piecewise-constant zones.
    Dense Jacobians are budgeted; this is not an industrial matrix-free solve.
    Sparse LU is deliberate and independent of the potential-field Jacobi
    solver. Cancellation is between PDE solves, not inside native factorization.
    """
    if kind not in ("dc", "ip") or not np.isfinite(beta) or beta < 0:
        raise ValueError("kind must be dc/ip and beta nonnegative")
    if cancel is not None and cancel():
        raise InterruptedError("Electrical inversion cancelled")
    setup = _setup(
        mesh_widths,
        mesh_origin,
        electrodes,
        abmn,
        active_cells=active_cells,
        parameter_labels=parameter_labels,
        max_cells=max_cells,
        max_parameters=max_parameters,
        max_work=max_work,
        nky=nky,
    )
    n = setup["n_parameters"]
    obs, std = as_array(observed, float), as_array(data_std, float)
    if (
        obs.shape != (setup["survey"].nD,)
        or std.shape != obs.shape
        or not np.isfinite(obs).all()
        or not np.isfinite(std).all()
        or np.any(std <= 0)
    ):
        raise ValueError(
            "Finite matching observations and positive independent data errors required"
        )
    if len(obs) * n + 4 * n * n > max_jacobian_elements:
        raise ValueError("Electrical inversion Jacobian/prior budget exceeded")
    for name, limit in (
        ("max_evaluations", max_evaluations),
        ("max_forward_evaluations", max_forward_evaluations),
    ):
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, np.integer))
            or not 1 <= limit <= 1000
        ):
            raise ValueError(name + " must be an integer in 1..1000")
    is_ip = kind == "ip"
    start = _values(initial, setup, "initial", eta=is_ip)
    prior = _values(reference, setup, "reference", eta=is_ip)
    limits = as_array(
        bounds if bounds is not None else ((0.0, 0.5) if is_ip else (1e-6, 10.0)), float
    )
    if (
        limits.shape != (2,)
        or not np.isfinite(limits).all()
        or not limits[0] < limits[1]
    ):
        raise ValueError("Require increasing finite physical bounds")
    if (is_ip and not 0 <= limits[0] < limits[1] < 1) or (not is_ip and limits[0] <= 0):
        raise ValueError("Bounds outside physical parameter domain")
    if np.any(start <= limits[0]) or np.any(start >= limits[1]):
        raise ValueError("Starting model must be strictly inside bounds")
    reg = np.eye(n) if regularization is None else as_array(regularization, float)
    if (
        reg.ndim != 2
        or reg.shape[1] != n
        or reg.size + len(obs) * n > max_jacobian_elements
        or not np.isfinite(reg).all()
    ):
        raise ValueError("Invalid or over-budget prior operator")
    fixed_sigma = (
        _values(conductivity_s_m, setup, "conductivity_s_m") if is_ip else None
    )
    simulation = _simulation(setup, ip=is_ip, conductivity=fixed_sigma)
    calls = 0
    try:
        if is_ip:
            if cancel is not None and cancel():
                raise InterruptedError("Electrical inversion cancelled")
            raw_jacobian = as_array(simulation.getJ(start))
            # getJ is raw IP voltage sensitivity in SimPEG 0.25, whereas
            # Jvec/dpred normalize apparent chargeability by DC voltage.
            jacobian = simulation._scale[:, None] * raw_jacobian
            system = np.vstack([jacobian / std[:, None], np.sqrt(beta) * reg])
            target = np.r_[obs / std, np.sqrt(beta) * (reg @ prior)]
            fitted = lsq_linear(system, target, bounds=limits, max_iter=max_evaluations)
            model = fitted.x
            prediction = jacobian @ model
            calls = 1
        else:
            prior = np.log(prior)
            cache = {}

            def evaluate(model):
                nonlocal calls
                if cancel is not None and cancel():
                    raise InterruptedError("Electrical inversion cancelled")
                if "model" in cache and np.array_equal(cache["model"], model):
                    return cache["prediction"], cache["fields"]
                if calls >= max_forward_evaluations:
                    raise RuntimeError("Electrical PDE forward-call budget exceeded")
                calls += 1
                fields = simulation.fields(model)
                prediction = simulation.dpred(model, f=fields)
                cache.update(model=model.copy(), fields=fields, prediction=prediction)
                return prediction, fields

            def residual(model):
                prediction, _ = evaluate(model)
                return np.r_[
                    (prediction - obs) / std, np.sqrt(beta) * (reg @ (model - prior))
                ]

            def derivative(model):
                _, fields = evaluate(model)
                return np.vstack(
                    [
                        simulation.getJ(model, f=fields) / std[:, None],
                        np.sqrt(beta) * reg,
                    ]
                )

            fitted = least_squares(
                residual,
                np.log(start),
                jac=derivative,
                bounds=np.log(limits),
                max_nfev=max_evaluations,
            )
            model = np.exp(fitted.x)
            prediction = obs + fitted.fun[: len(obs)] * std
        if cancel is not None and cancel():
            raise InterruptedError("Electrical inversion cancelled")
        if not np.isfinite(model).all() or not np.isfinite(prediction).all():
            raise RuntimeError("Electrical inversion returned nonfinite results")
        return {
            **_metadata(setup),
            "model": model,
            "predicted": prediction,
            "kind": kind,
            "model_units": "V/V" if is_ip else "S/m",
            "success": bool(fitted.success),
            "message": str(fitted.message),
            "chi_squared": float(np.sum(((prediction - obs) / std) ** 2)),
            "forward_evaluations": calls,
            "beta": float(beta),
            "regularization": "explicit parameter-space L2",
            "reference": as_array(reference, float),
        }
    finally:
        _clean(simulation)

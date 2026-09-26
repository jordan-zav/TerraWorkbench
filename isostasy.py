"""Cartesian Airy root models with explicit boundaries, independent of QGIS.

Coordinates and heights are metres; density is kg/m3; g_z is downward in mGal.
The caller supplies a complete regional load model independently of stations.
Prisms use a finite domain; the Parker FFT method repeats its input domain.
Neither adds a spherical correction or a fitted offset.
"""

import numpy as np


def airy_prisms(easting, northing, basement, *, reference_depth=30000.,
                density_crust=2670., density_mantle=3070., water_thickness=0.,
                density_water=1040., block_size=1, max_cells=100000):
    """Build root/antiroot prisms, optionally averaging loads in square blocks.

    Water thickness is explicit (including lakes above sea level). NoData in a
    load model is an error, never implicitly zero mass. Block averaging preserves
    integrated compensating mass, but changes geometry: test convergence.
    Axes must be regularly spaced, ascending cell centres, with >=2 values.
    """
    constants = np.array([reference_depth, density_crust, density_mantle,
                          density_water], dtype=float)
    if (not np.isfinite(constants).all() or reference_depth <= 0
            or not 0 < density_crust < density_mantle
            or not 0 <= density_water < density_crust):
        raise ValueError("Invalid reference depth or crust/mantle/water densities.")
    if int(block_size) != block_size or block_size < 1:
        raise ValueError("block_size must be a positive integer.")
    if not np.isfinite(max_cells) or max_cells < 1:
        raise ValueError("max_cells must be finite and positive.")
    block_size = int(block_size)
    axes = [np.asarray(a, dtype=float) for a in (easting, northing)]
    for axis in axes:
        if (axis.ndim != 1 or axis.size < 2 or not np.isfinite(axis).all()
                or axis[1] <= axis[0]
                or not np.allclose(np.diff(axis), axis[1] - axis[0], rtol=1e-9, atol=1e-7)):
            raise ValueError("Model axes must be ascending, regular metric cell centres.")
    x, y = axes
    h = np.asarray(basement, dtype=float)
    if h.shape != (y.size, x.size) or not np.isfinite(h).all():
        raise ValueError("Regional basement must be complete and match model axes; NoData is not zero load.")
    water = np.broadcast_to(np.asarray(water_thickness, dtype=float), h.shape)
    if not np.isfinite(water).all() or np.any(water < 0):
        raise ValueError("Water thickness must be finite and non-negative.")
    load = density_crust * h + density_water * water
    rows, cols = np.arange(0, y.size, block_size), np.arange(0, x.size, block_size)
    if rows.size * cols.size > max_cells:
        raise ValueError("Regional model exceeds max_cells after aggregation; increase block_size or the explicit limit.")
    nr = np.minimum(block_size, y.size - rows)
    nc = np.minimum(block_size, x.size - cols)
    load = np.add.reduceat(np.add.reduceat(load, rows, axis=0), cols, axis=1)
    load /= nr[:, None] * nc[None, :]
    contrast = density_mantle - density_crust
    root = load / contrast
    if np.any(reference_depth + root <= 0):
        raise ValueError("Airy Moho reaches or exceeds the reference sea-level surface.")
    dx, dy = x[1] - x[0], y[1] - y[0]
    west, south = np.meshgrid(x[cols] - dx / 2, y[rows] - dy / 2)
    east, north = np.meshgrid(x[cols] + (nc - .5) * dx, y[rows] + (nr - .5) * dy)
    moho = -reference_depth - root
    prisms = np.column_stack([v.ravel() for v in (
        west, east, south, north,
        np.minimum(moho, -reference_depth), np.maximum(moho, -reference_depth))])
    density = np.where(root.ravel() >= 0, -contrast, contrast)
    active = root.ravel() != 0
    return prisms[active], density[active]


def airy_root_effect(coordinates, prisms, density, *, chunk_size=512,
                     max_interactions=200_000_000, progress=None, cancelled=None,
                     gravity_backend=None):
    """Evaluate finite roots at arbitrary stations, retaining missing stations.

    Bounded chunks allow progress/cancellation. A work limit counts actual
    station/prism pairs instead of restricting raster dimensions. Pass an
    explicit larger limit only after benchmarking. Missing model masses are
    prohibited in airy_prisms; missing station coordinates yield NaN.
    """
    if len(coordinates) != 3:
        raise ValueError("Supply easting, northing and upward observation height.")
    xyz = np.broadcast_arrays(*[np.asarray(a, dtype=float) for a in coordinates])
    if any(np.isinf(a).any() for a in xyz):
        raise ValueError("Observation coordinates cannot contain infinities.")
    if int(chunk_size) != chunk_size or chunk_size < 1:
        raise ValueError("chunk_size must be a positive integer.")
    if not np.isfinite(max_interactions) or max_interactions < 1:
        raise ValueError("max_interactions must be finite and positive.")
    prisms, density = np.asarray(prisms, dtype=float), np.asarray(density, dtype=float)
    if (prisms.ndim != 2 or prisms.shape[1] != 6 or density.shape != (len(prisms),)
            or not np.isfinite(prisms).all() or not np.isfinite(density).all()
            or np.any(prisms[:, ::2] > prisms[:, 1::2])):
        raise ValueError("Invalid prisms or density array.")
    valid = np.logical_and.reduce([np.isfinite(a).ravel() for a in xyz])
    indices = np.flatnonzero(valid)
    if indices.size * len(prisms) > max_interactions:
        raise ValueError("Station/prism work exceeds max_interactions; coarsen the regional model or deliberately raise the work limit.")
    result = np.full(xyz[0].size, np.nan)
    if len(prisms) == 0:
        result[valid] = 0
        return result.reshape(xyz[0].shape)
    if gravity_backend is None:
        from harmonica import prism_gravity
        gravity_backend = prism_gravity
    for start in range(0, indices.size, int(chunk_size)):
        if cancelled is not None and cancelled():
            raise InterruptedError("Isostatic modelling cancelled.")
        selected = indices[start:start + int(chunk_size)]
        result[selected] = gravity_backend(
            tuple(a.ravel()[selected] for a in xyz), prisms, density, field="g_z")
        if progress is not None:
            progress(min(start + int(chunk_size), indices.size) / indices.size)
    return result.reshape(xyz[0].shape)


def airy_root_effect_fft(basement, spacing, *, boundary,
                         reference_depth=30000., density_crust=2670.,
                         density_mantle=3270., water_thickness=0.,
                         density_water=1040., observation_height=0.,
                         tolerance_mgal=1e-5, max_terms=64,
                         max_cells=4_000_000, cancelled=None):
    """Parker-series root gravity at a horizontal observation plane (mGal).

    ``spacing`` is (dx, dy) in metres. Rows/columns and output retain input order.
    ``boundary='periodic'`` is required explicitly: the rectangle repeats to
    infinity, including its mean load. No zero padding, taper, demeaning or
    fitted constant is applied. This is a different physical boundary condition
    from finite prisms, not an acceleration of that same finite model.

    The root extends from depth D to D+t with density -(mantle-crust).
    Its transform is -2*pi*G*contrast*exp(-k*(D+z)) times
    sum[(-k)**(n-1) * FFT(t**n)/n!]. The k=0 term is retained.
    Convergence requires max(abs(t)) < D+z. Three consecutive small terms
    are required; their magnitude is a numerical diagnostic, not a model error.
    Returns (effect, diagnostics). Missing regional load is always rejected.
    """
    from scipy.fft import fftfreq, rfftfreq, rfft2, irfft2

    if boundary != "periodic":
        raise ValueError("FFT Airy requires explicit boundary='periodic'.")
    parameters = np.asarray([reference_depth, density_crust, density_mantle,
                             density_water, observation_height, tolerance_mgal], dtype=float)
    if (not np.isfinite(parameters).all() or reference_depth <= 0
            or not 0 < density_crust < density_mantle
            or not 0 <= density_water < density_crust or tolerance_mgal <= 0):
        raise ValueError("Invalid Airy FFT physical parameters or tolerance.")
    if not np.isfinite(max_terms) or int(max_terms) != max_terms or not 3 <= max_terms <= 256:
        raise ValueError("max_terms must be an integer between 3 and 256.")
    if not np.isfinite(max_cells) or max_cells < 4:
        raise ValueError("max_cells must be finite and at least four.")
    h = np.asarray(basement, dtype=float)
    if (h.ndim != 2 or min(h.shape) < 2 or h.size > max_cells
            or not np.isfinite(h).all()):
        raise ValueError("FFT regional load must be a complete 2D grid within max_cells.")
    spacing = np.asarray(spacing, dtype=float)
    if spacing.shape != (2,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("spacing must be positive finite (dx, dy) in metres.")
    water = np.broadcast_to(np.asarray(water_thickness, dtype=float), h.shape)
    if not np.isfinite(water).all() or np.any(water < 0):
        raise ValueError("Water thickness must be finite and non-negative.")
    contrast = density_mantle - density_crust
    root = (density_crust*h + density_water*water)/contrast
    distance = reference_depth + observation_height
    ratio = float(np.max(np.abs(root)) / distance) if distance > 0 else np.inf
    if np.any(reference_depth + root <= 0) or ratio >= 1:
        raise ValueError("FFT convergence requires max(abs(root)) < reference_depth + observation_height, and positive Moho depth.")
    ky = 2*np.pi*fftfreq(h.shape[0], spacing[1])[:, None]
    kx = 2*np.pi*rfftfreq(h.shape[1], spacing[0])[None, :]
    k = np.hypot(kx, ky)
    scale = distance
    normalized = root/scale
    power = np.ones_like(root)
    transfer = scale*np.exp(-k*distance)
    result = np.zeros_like(root)
    small = 0
    factor = -2*np.pi*6.67430e-6*contrast
    for n in range(1, int(max_terms)+1):
        if cancelled is not None and cancelled():
            raise InterruptedError("Isostatic FFT modelling cancelled.")
        power *= normalized
        term = factor*irfft2(transfer*rfft2(power), s=root.shape)
        result += term
        change = float(np.max(np.abs(term)))
        if not np.isfinite(result).all():
            raise ValueError("Airy FFT series overflowed; revise model geometry.")
        small = small+1 if change <= tolerance_mgal else 0
        if small >= 3:
            return result, dict(
                model="Parker Airy FFT", boundary="periodic", terms=n,
                last_term_max_mgal=change, tolerance_mgal=tolerance_mgal,
                root_distance_ratio=ratio, mean_root_effect_mgal=float(result.mean()),
                reference_depth_m=float(reference_depth), observation_height_m=float(observation_height),
                density_crust=float(density_crust), density_mantle=float(density_mantle),
                density_water=float(density_water), gravitational_constant_si=6.67430e-11,
                dc_term="preserved", fitted_offset_mgal=0., spacing_m=spacing.tolist())
        transfer *= -k*scale/(n+1)
    raise ValueError(f"Airy FFT series did not converge within {max_terms} terms (last term {change:g} mGal).")

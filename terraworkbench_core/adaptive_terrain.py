"""Adaptive finite-DEM gravity at explicit stations, with truncation bounds.

Independent Cartesian tree, signed mass groups and analytic near-field prisms.
The reported error bounds concern monopole truncation only, not DEM/density,
floating-point, datum, curvature or omitted outer-terrain uncertainty.
"""

import hashlib
from importlib.metadata import version
import math
from pathlib import Path

import numpy as np
from scipy.constants import G

from ._array_contract import as_array
from ._calibration import integer_budget
from .terrain_tree_walk import get_builder, get_walker


def terrain_gravity_adaptive(
    easting,
    northing,
    elevation_m,
    observation_xyz,
    *,
    density_crust,
    density_water,
    reference_elevation_m,
    absolute_tolerance_mgal,
    leaf_cells=32,
    max_cells=4_000_000,
    max_points=100_000,
    max_tree_nodes=1_000_000,
    max_node_visits=10_000_000,
    max_prism_evaluations=10_000_000,
    canceled=None,
):
    """Finite DEM density-contrast attraction, downward positive in mGal.

    Increasing uniform east/north axes (cell centres), complete 2-D DEM and
    explicit ENU station positions, all metres. Above the reference plane the
    contrast is crust density; below it water minus crust, no automatic datum.
    Returns attraction only, NOT a complete terrain/Bouguer/tide correction.

    A tree preserves separate positive/negative mass, centroids and second
    central moments J. Far groups use monopoles only when d>R and the summed
    bound 12*G*1e5*J/(d-R)^4 is finite. Largest-bound groups are refined until
    the sum of retained bounds meets the absolute tolerance. This follows the
    second-order Taylor remainder with
    ||Hessian(r_z/r^3)|| <= 24/r^4. The source volume lies in radius R about its
    mass centre. Near leaves use exact Harmonica prism kernels, not point cells.
    Tolerance zero requests all exact prisms. No thin-cell threshold is applied.

    Bounds exclude roundoff and model errors, and are not statistical confidence.
    Work limits cover tree nodes, visits and exact source/station evaluations,
    not wall time or solver RAM. Worst case can still be a dense exact sum.
    """

    def check():
        if canceled is not None and canceled():
            raise RuntimeError("Adaptive terrain canceled")

    for value, name in (
        (leaf_cells, "Leaf cells"),
        (max_cells, "Maximum cells"),
        (max_points, "Maximum stations"),
        (max_tree_nodes, "Maximum tree nodes"),
        (max_node_visits, "Maximum node visits"),
        (max_prism_evaluations, "Maximum prism evaluations"),
    ):
        integer_budget(value, name)
        if value > np.iinfo(np.int64).max:
            raise ValueError(name + " exceeds the native integer range")
    x, y, z, observations = (
        as_array(v, float) for v in (easting, northing, elevation_m, observation_xyz)
    )
    if (
        x.ndim != 1
        or y.ndim != 1
        or min(x.size, y.size) < 2
        or z.shape != (y.size, x.size)
        or z.size > max_cells
        or observations.ndim != 2
        or observations.shape[1] != 3
        or not 1 <= len(observations) <= max_points
    ):
        raise ValueError(
            "Complete DEM axes and ENU station array within cell/point budgets required"
        )
    if not all(np.isfinite(a).all() for a in (x, y, z, observations)):
        raise ValueError("Terrain and stations must be complete and finite")
    for axis in (x, y):
        diff = np.diff(axis)
        if np.any(diff <= 0) or not np.allclose(diff, diff[0], rtol=1e-8, atol=1e-10):
            raise ValueError("Terrain axes must be uniformly spaced and increasing")
    crust, water, reference, tolerance = map(
        float,
        (density_crust, density_water, reference_elevation_m, absolute_tolerance_mgal),
    )
    if (
        not np.isfinite([crust, water, reference, tolerance]).all()
        or not crust > water >= 0
        or tolerance < 0
    ):
        raise ValueError(
            "Require crust > water >= 0, finite reference and nonnegative tolerance"
        )
    check()
    # Local coordinates keep centroid arithmetic independent of UTM offsets.
    origin = np.array([x[0], y[0], reference])
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    x, y, z, observations = (
        x - origin[0],
        y - origin[1],
        z - reference,
        observations - origin,
    )
    if (
        not all(np.isfinite(a).all() for a in (x, y, z, observations))
        or not np.isfinite(dx * dy)
        or dx * dy <= 0
    ):
        raise ValueError("Local geometry exceeds finite range")
    import harmonica

    (
        children,
        masses,
        centres,
        radii,
        moments,
        source_counts,
        offsets,
        sources,
        node_count,
        active_cells,
        status,
    ) = get_builder()(x, y, z, dx, dy, crust, water, leaf_cells, max_tree_nodes)
    check()
    if status:
        raise ValueError(
            "Terrain tree node budget exceeded"
            if status == 1
            else "Terrain mass/moment arithmetic exceeds finite range"
        )
    children, masses, centres, radii, moments, source_counts, offsets = (
        a[:node_count].copy()
        for a in (children, masses, centres, radii, moments, source_counts, offsets)
    )
    sources = sources[:active_cells].copy()
    total_mass = math.fsum(abs(v) for v in masses[0])
    if not np.isfinite(total_mass):
        raise ValueError("Terrain total mass exceeds finite range")
    observations = np.ascontiguousarray(observations)
    walker = get_walker()

    effect, bounds = np.zeros(len(observations)), np.zeros(len(observations))
    exact_counts, point_counts, visit_counts = (
        np.zeros(len(observations), dtype=np.int64) for _ in range(3)
    )
    visits, exact_total = 0, 0
    for index, station in enumerate(observations):
        check()
        estimates, errors, leaves, nvisits, nexact, npoints, status = walker(
            station,
            children,
            masses,
            centres,
            radii,
            moments,
            source_counts,
            tolerance,
            max_node_visits - visits,
            max_prism_evaluations - exact_total,
            G * 1e5,
        )
        check()
        if status:
            raise ValueError(
                {
                    1: "Terrain node visit budget exceeded",
                    2: "Terrain exact prism evaluation budget exceeded",
                    3: "Station distance exceeds finite range",
                }[status]
            )
        visits += nvisits
        exact_total += nexact
        visit_counts[index], exact_counts[index], point_counts[index] = (
            nvisits,
            nexact,
            npoints,
        )
        value = math.fsum(estimates)
        exact = [sources[offsets[i] : offsets[i] + source_counts[i]] for i in leaves]
        if exact:
            indices = np.concatenate(exact)
            rows, columns = np.divmod(indices, z.shape[1])
            heights = z[rows, columns]
            prisms = np.column_stack(
                (
                    x[columns] - dx / 2,
                    x[columns] + dx / 2,
                    y[rows] - dy / 2,
                    y[rows] + dy / 2,
                    np.minimum(heights, 0.0),
                    np.maximum(heights, 0.0),
                )
            )
            density = np.where(heights > 0, crust, water - crust)
            check()
            value += float(
                harmonica.prism_gravity(
                    tuple(station), prisms, density, field="g_z", parallel=False
                )
            )
        effect[index], bounds[index] = value, math.fsum(errors)
    check()
    if (
        not np.isfinite(effect).all()
        or not np.isfinite(bounds).all()
        or np.any(bounds > tolerance * (1 + 1e-12))
    ):
        raise ValueError("Terrain output/bound arithmetic exceeds its finite tolerance")
    return dict(
        engine="harmonica",
        engine_version=version("harmonica"),
        prism_effect_mgal=effect,
        truncation_bound_mgal=bounds,
        exact_prism_count=exact_counts,
        monopole_count=point_counts,
        node_visit_count=visit_counts,
        recipe=dict(
            method="adaptive-signed-mass-tree-with-exact-prism-near-field",
            units="mGal",
            gravity_positive="down",
            axes="east,north,up; projected Cartesian metres",
            density_crust=crust,
            density_water=water,
            reference_elevation_m=reference,
            absolute_tolerance_mgal=tolerance,
            leaf_cells=leaf_cells,
            tree_nodes=node_count,
            active_source_cells=active_cells,
            total_absolute_mass_kg=total_mass,
            dense_interactions=active_cells * len(observations),
            exact_prism_evaluations=exact_total,
            monopole_evaluations=int(point_counts.sum()),
            node_visits=visits,
            coordinate_origin_m=origin.tolist(),
            gravitational_constant_si=float(G),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            tree_walk_sha256=hashlib.sha256(
                Path(__file__).with_name("terrain_tree_walk.py").read_bytes()
            ).hexdigest(),
            libraries={
                "numpy": np.__version__,
                "harmonica": version("harmonica"),
                "numba": version("numba"),
            },
            approximation="Separate signed monopoles preserving mass, centroid and second central moment",
            bound_scope="Analytic monopole truncation only; excludes roundoff, DEM/density/datum/curvature and omitted outer terrain",
            correction_scope="DEM contrast attraction only; not a complete terrain, Bouguer or tide correction",
        ),
    )

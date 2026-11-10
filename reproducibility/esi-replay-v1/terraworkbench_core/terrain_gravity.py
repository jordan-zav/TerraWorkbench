"""Finite DEM rectangular-prism terrain term; optional Harmonica engine."""

import numpy as np
from importlib.metadata import version

from ._array_contract import as_array
from ._calibration import integer_budget


def terrain_correction_prisms(
    easting,
    northing,
    elevation_m,
    *,
    density_crust,
    density_water,
    clearance_m,
    max_cells=10_000,
    max_interactions=100_000_000,
    block_size=256,
    canceled=None,
):
    """Return plate minus finite DEM attraction in mGal, on the DEM grid.

    ENU projected metre coordinates, uniformly spaced increasing 1-D axes and
    a complete (northing,easting) elevation array relative to the reference
    plane z=0. Densities kg/m3; g_z is downward. Stations lie at DEM+clearance.
    Bathymetry uses water-minus-crust density. No outer terrain is invented.
    Observation blocks reduce temporary work and allow cancellation; total
    computation remains O(cells squared), not an adaptive far-field solver.
    """
    for value, name in (
        (max_cells, "Maximum cells"),
        (max_interactions, "Maximum interactions"),
        (block_size, "Block size"),
    ):
        integer_budget(value, name)
    x, y, z = (as_array(value, float) for value in (easting, northing, elevation_m))
    if (
        x.ndim != 1
        or y.ndim != 1
        or min(x.size, y.size) < 2
        or z.shape != (y.size, x.size)
    ):
        raise ValueError(
            "Terrain requires 1-D easting/northing axes and a matching 2-D DEM"
        )
    if z.size > max_cells or z.size**2 > max_interactions:
        raise ValueError("Terrain cell or interaction budget exceeded")
    if not all(np.isfinite(a).all() for a in (x, y, z)):
        raise ValueError("Terrain coordinates and DEM must be complete and finite")
    for axis in (x, y):
        spacing = np.diff(axis)
        if np.any(spacing <= 0) or not np.allclose(
            spacing, spacing[0], rtol=1e-8, atol=1e-10
        ):
            raise ValueError("Terrain axes must be uniformly spaced and increasing")
    crust, water, clearance = (
        float(density_crust),
        float(density_water),
        float(clearance_m),
    )
    if (
        not np.isfinite([crust, water, clearance]).all()
        or not crust > water >= 0
        or clearance <= 0
    ):
        raise ValueError(
            "Require crust > water >= 0 kg/m3 and positive clearance in metres"
        )
    if canceled is not None and canceled():
        raise RuntimeError("Terrain correction canceled")
    import harmonica

    density = np.where(z >= 0, crust, water - crust)
    layer = harmonica.prism_layer(
        (x, y), z, reference=0.0, properties={"density": density}
    )
    east, north = np.meshgrid(x, y)
    upward = z + clearance
    effect = np.empty(z.size)
    for first in range(0, z.size, block_size):
        if canceled is not None and canceled():
            raise RuntimeError("Terrain correction canceled")
        last = min(first + block_size, z.size)
        effect[first:last] = layer.prism_layer.gravity(
            (
                east.ravel()[first:last],
                north.ravel()[first:last],
                upward.ravel()[first:last],
            ),
            field="g_z",
            thickness_threshold=0.001,
        )
    if canceled is not None and canceled():
        raise RuntimeError("Terrain correction canceled")
    effect = effect.reshape(z.shape)
    plate = np.asarray(
        harmonica.bouguer_correction(z, density_crust=crust, density_water=water)
    )
    if not np.isfinite(effect).all() or not np.isfinite(plate).all():
        raise ValueError("Terrain engine returned nonfinite attraction")
    return dict(
        engine="harmonica",
        engine_version=version("harmonica"),
        terrain_mgal=plate - effect,
        plate_mgal=plate,
        prism_effect_mgal=effect,
        recipe=dict(
            method="finite-dem-prisms",
            axes="east,north,up",
            gravity_positive="down",
            units="mGal",
            reference_plane_m=0.0,
            density_crust=crust,
            density_water=water,
            clearance_m=clearance,
            block_size=block_size,
            interactions=int(z.size**2),
            extent_scope="Supplied DEM only; inspect outer truncation and edge effects",
        ),
    )

"""Numerical building blocks for land gravity reductions.

The functions in this module are independent from QGIS so their sign conventions
and formulas can be tested without a QGIS runtime.
"""

from __future__ import annotations

import numpy as np


GRS80_EQUATOR_GRAVITY = 9.7803267715  # m/s2
GRS80_K = 0.00193185138639
GRS80_ECCENTRICITY_SQUARED = 0.00669438002290
MGAL_PER_MS2 = 100000.0


def normal_gravity_grs80(latitude_degrees):
    """Normal gravity on the GRS80 ellipsoid in mGal (Somigliana formula)."""
    return normal_gravity_somigliana(latitude_degrees)


def normal_gravity_somigliana(
    latitude_degrees, *, equator_mgal=GRS80_EQUATOR_GRAVITY * MGAL_PER_MS2,
    k=GRS80_K, eccentricity_squared=GRS80_ECCENTRICITY_SQUARED,
):
    """Normal gravity with explicit constants; custom values are not GRS80.

    NaN observations remain missing. Infinite/out-of-range latitude and invalid
    constants are rejected rather than silently folded through trigonometry.
    """
    constants = np.asarray([equator_mgal, k, eccentricity_squared], dtype=float)
    if not np.isfinite(constants).all() or equator_mgal <= 0 or k <= -1 or not 0 <= eccentricity_squared < 1:
        raise ValueError("Invalid Somigliana constants.")
    degrees = np.asarray(latitude_degrees, dtype=np.float64)
    if np.isinf(degrees).any() or np.any(np.abs(degrees[np.isfinite(degrees)]) > 90):
        raise ValueError("Latitude must be within [-90, 90] degrees or NaN.")
    latitude = np.deg2rad(np.asarray(latitude_degrees, dtype=np.float64))
    sin_squared = np.sin(latitude) ** 2
    gravity = equator_mgal * (
        (1.0 + k * sin_squared)
        / np.sqrt(1.0 - eccentricity_squared * sin_squared)
    )
    return gravity


def land_gravity_reduction(
    observed_mgal, latitude_degrees, observation_height_m, terrain_height_m, *,
    height_reference, density_kg_m3, slab_coefficient,
    equator_mgal=GRS80_EQUATOR_GRAVITY * MGAL_PER_MS2,
    k=GRS80_K, eccentricity_squared=GRS80_ECCENTRICITY_SQUARED,
    vertical_gradient=0.3086,
):
    """Explicit land reduction and serializable numerical provenance.

    Input gravity must already have instrument/motion corrections applied.
    Observation height is used for free air; ground height for the slab.
    slab_coefficient is mGal/(g/cm3*m), density is kg/m3. No datum conversion,
    terrain correction, curvature, static adjustment or leveling is inferred.
    """
    if height_reference not in ("MSL", "ellipsoid"):
        raise ValueError("Declare MSL or ellipsoid height reference explicitly.")
    if not np.isfinite([density_kg_m3, slab_coefficient, vertical_gradient]).all() or min(density_kg_m3, slab_coefficient, vertical_gradient) <= 0:
        raise ValueError("Density, slab coefficient and free-air gradient must be positive and finite.")
    arrays = [np.asarray(v, dtype=float) for v in
              (observed_mgal, latitude_degrees, observation_height_m, terrain_height_m)]
    if any(a.shape != arrays[0].shape or np.isinf(a).any() for a in arrays):
        raise ValueError("Input channels must have identical shapes and no infinities.")
    observed, latitude, height, terrain = arrays
    if np.any(terrain < 0):
        raise ValueError("Land slab reduction does not support negative terrain heights.")
    normal = normal_gravity_somigliana(latitude, equator_mgal=equator_mgal,
                                      k=k, eccentricity_squared=eccentricity_squared)
    free_air = free_air_correction(height, vertical_gradient)
    slab = slab_coefficient * (density_kg_m3 / 1000.) * terrain
    faa = observed - normal + free_air
    products = {"normal_gravity": normal, "free_air_correction": free_air,
                "bouguer_slab": slab, "free_air_anomaly": faa,
                "simple_bouguer_anomaly": faa - slab}
    recipe = {"operation": "land_gravity_reduction", "version": 1,
              "height_reference": height_reference, "equator_mgal": float(equator_mgal),
              "k": float(k), "eccentricity_squared": float(eccentricity_squared),
              "density_kg_m3": float(density_kg_m3), "slab_coefficient": float(slab_coefficient),
              "slab_coefficient_unit": "mGal/(g/cm3*m)", "vertical_gradient": float(vertical_gradient),
              "numpy": np.__version__, "output_unit": "mGal",
              "height_conversion": "none", "input_requirement": "instrument/motion corrected gravity",
              "formula": "observed - normal + free_air - slab"}
    return products, recipe


def free_air_correction(height_m, vertical_gradient=0.3086):
    """Positive-upward linear free-air correction in mGal."""
    return np.asarray(height_m, dtype=np.float64) * float(vertical_gradient)


def curvature_correction(height_m, density=2670.0):
    """Bullard-B spherical-cap correction in mGal for land elevations.

    The polynomial is the commonly used Lambert/USGS form after converting its
    original elevation argument from feet to metres. It is scaled linearly from
    the reference reduction density of 2670 kg/m3. Bathymetric cells are set to
    zero because this land reduction is not an offshore Bullard-B model.
    """
    height = np.maximum(np.asarray(height_m, dtype=np.float64), 0.0)
    reference = (
        1.4633e-3 * height
        - 3.533e-7 * height**2
        + 4.5e-14 * height**3
    )
    return reference * (float(density) / 2670.0)


def gravity_disturbance(observed_mgal, normal_mgal):
    """Observed gravity minus ellipsoidal normal gravity."""
    return np.asarray(observed_mgal) - np.asarray(normal_mgal)


def free_air_anomaly(observed_mgal, normal_mgal, height_m, vertical_gradient=0.3086):
    """Free-air anomaly in mGal."""
    return gravity_disturbance(observed_mgal, normal_mgal) + free_air_correction(
        height_m, vertical_gradient
    )


def simple_bouguer_anomaly(
    observed_mgal,
    normal_mgal,
    height_m,
    bouguer_effect_mgal,
    vertical_gradient=0.3086,
):
    """Simple Bouguer anomaly: FAA minus the infinite-plate effect."""
    return free_air_anomaly(
        observed_mgal, normal_mgal, height_m, vertical_gradient
    ) - np.asarray(bouguer_effect_mgal)


def complete_bouguer_anomaly(
    observed_mgal,
    normal_mgal,
    height_m,
    bouguer_effect_mgal,
    terrain_mgal,
    curvature_mgal,
    vertical_gradient=0.3086,
):
    """Complete land Bouguer anomaly: SBA + terrain - Bullard B."""
    simple = simple_bouguer_anomaly(
        observed_mgal,
        normal_mgal,
        height_m,
        bouguer_effect_mgal,
        vertical_gradient,
    )
    return simple + np.asarray(terrain_mgal) - np.asarray(curvature_mgal)


def airy_root_thickness(height_m, density_crust=2670.0, density_mantle=3070.0):
    """Local Airy root thickness in metres relative to a reference Moho."""
    density_contrast = float(density_mantle) - float(density_crust)
    if density_contrast <= 0.0:
        raise ValueError("Mantle density must exceed crust density")
    return (
        float(density_crust)
        / density_contrast
        * np.asarray(height_m, dtype=np.float64)
    )


def airy_moho_depth(
    height_m,
    reference_depth=25000.0,
    density_crust=2670.0,
    density_mantle=3070.0,
):
    """Depth-positive Airy Moho in metres."""
    return float(reference_depth) + airy_root_thickness(
        height_m, density_crust, density_mantle
    )

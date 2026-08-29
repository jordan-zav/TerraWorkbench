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
    latitude = np.deg2rad(np.asarray(latitude_degrees, dtype=np.float64))
    sin_squared = np.sin(latitude) ** 2
    gravity = GRS80_EQUATOR_GRAVITY * (
        (1.0 + GRS80_K * sin_squared)
        / np.sqrt(1.0 - GRS80_ECCENTRICITY_SQUARED * sin_squared)
    )
    return gravity * MGAL_PER_MS2


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

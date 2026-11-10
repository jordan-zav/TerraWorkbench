# 11. Land gravity, networks and 2D models

[English](../en/11_gravimetria.md) · [Español](../es/11_gravimetria.md) · [Português](../pt/11_gravimetria.md)

## From instrument readings to an anomaly

Begin a reduction by identifying the input: relative reading, calibrated observed gravity, disturbance, free-air anomaly or Bouguer anomaly. Resolve instrument and motion corrections before interpreting an anomaly as a subsurface effect. Do not infer processing status from a filename.

normal_gravity_grs80 returns normal gravity on the GRS80 ellipsoid in mGal using Somigliana. normal_gravity_somigliana accepts explicit constants; changing them means the result must not automatically be labelled GRS80. Receiver elevation and terrain elevation enter different terms.

## Reduction scheme

Under a common land convention, simple Bouguer anomaly combines observed and normal gravity, free-air correction and slab attraction:

    g_B_simple = g_observed − γ + C_free_air − C_slab

The slab term depends on density and terrain height; free air depends on observation height. Keep slab coefficient, units and height reference explicit. land_gravity_reduction requests these in its contract and produces numerical provenance.

Complete anomaly adds terrain and, depending on the recipe, curvature or other reductions. Verify the sign and definition of an incoming attraction or correction. A gravity disturbance formed using normal gravity at the relevant elevation is not identical to every free-air-anomaly definition.

## Networks and drift

adjust_gravity_network estimates a network using stations, instruments, times and references. Anchors set the datum; uncertain anchors must not later be treated as exact, and their common covariance must be retained. Estimated drift does not automatically correct unsupplied tides or loading.

fit_bouguer_density explores density under a declared statistical relationship. Anomaly–topography association can reflect geology as well as reduction density. Examine ranges, residuals and sensitivity before adopting one value across an area.

## Polygon profiles

polygon_gravity_2d uses X/upward-Z sections, kg/m³ density and infinite extent normal to the section. Its vertical component is downward-positive in mGal. fit_polygon_densities fits properties with fixed geometry; it does not automatically recover vertices or finite lateral extent.

## Acceptance checks

Verify latitude, horizontal datum, heights, instrument scale, repeat bases, drift, free-air term, density and topography. Inspect corrections separately. Before inversion, confirm whether observations are upward- or downward-positive and whether they are contrasts relative to a regional.

See [reductions and conventions](../../development/standalone_acquisition.md), [networks and profiles](../../validation/reports/2d_extensions.md) and [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html). Function defaults do not replace survey metadata.

## Related implementation

[gravity_corrections](../../../terraworkbench_core/gravity_corrections.py), [gravity_network](../../../terraworkbench_core/gravity_network.py), [gravity_profiles](../../../terraworkbench_core/gravity_profiles.py)

---

[Contents](README.md) · [Previous](10_magnetometria.md) · [Next](12_terreno_isostasia.md)

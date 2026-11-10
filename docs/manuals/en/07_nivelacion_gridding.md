# 7. Crossovers, levelling and interpolation

[English](../en/07_nivelacion_gridding.md) · [Español](../es/07_nivelacion_gridding.md) · [Português](../pt/07_nivelacion_gridding.md)

## Processing order

Levelling seeks to reduce discrepancies between lines after temporal and acquisition corrections. Gridding estimates a field on a lattice; it does not itself fix lag, base-station or height errors. Review line geometry, crossover quality and network connectivity first.

A crossover difference between comparable observations constrains relative corrections. A disconnected or unanchored network does not determine an absolute datum. Robust constant or polynomial fits reduce the influence of some residuals, but degree and accepted lines remain user choices. Record rejected crossovers, fitted corrections and residuals per line.

## Choosing an interpolator

| Method | Main controls | Precaution |
| --- | --- | --- |
| Nearest neighbour | Point distribution | Discontinuities between neighbour regions |
| IDW | Power, neighbours, radius | Dense lines may dominate |
| Global TPS | Smoothness and full support | Dense-system cost |
| Local TPS | Neighbourhood and smoothness | Not equivalent to the global fit |
| Experimental minimum curvature | Grid, iterations and convergence | Check residuals and limits; do not assume proprietary equivalence |
| Sinc | Sampling and support | Cannot recover unmeasured detail |
| Ordinary kriging | Variogram, neighbours, nugget | Statistical model needs justification |
| Equivalent sources | Source depth and damping | Regularised physical problem, not neutral interpolation |

Smaller cells may improve display without increasing physical resolution. Fix extent, origin and cell size before comparing products. Numerical comparisons require the same lattice or documented resampling.

## Spatial validation

Reserve blocks or lines before selecting interpolator parameters. Measure errors at unused points and examine their locations; a global RMS can conceal poor edge extrapolation. Random validation between nearby points on one line can be overly favourable.

An empirical variogram depends on distance, bins, trend, available pairs and anisotropy. Its model does not make kriging variance the total acquisition or interpretation uncertainty. Equivalent sources require separation from receivers, explicit units and a defined prediction surface.

## Microlevelling

Use it after primary corrections and crossover levelling to treat residual directional corrugation. Compare the removed correction with the amplitude and orientation of real structures. Changing azimuth, cutoff or mask can alter geological signal, particularly along flight-parallel structures.

Preserve line corrections, the applied surface and final product separately. A smoother appearance is not a sufficient acceptance criterion.

Details: [interpolation](../../reference/methods/interpolation_methods.md), [basic pipeline](../../guides/basic_processing_migration.md), [equivalent sources and methods](../../research/core_expansion_implementation.md) and [geostatistical extensions](../../validation/reports/2d_extensions.md).

## Related implementation

[line_processing](../../../terraworkbench_core/line_processing.py), [gridding_methods](../../../terraworkbench_core/gridding_methods.py), [survey_processing](../../../terraworkbench_core/survey_processing.py), [survey_grid_pipeline](../../../terraworkbench_core/survey_grid_pipeline.py), [equivalent_sources](../../../terraworkbench_core/equivalent_sources.py), [geostatistics](../../../terraworkbench_core/geostatistics.py)

---

[Contents](README.md) · [Previous](06_perfiles_qc.md) · [Next](08_filtros_espaciales.md)

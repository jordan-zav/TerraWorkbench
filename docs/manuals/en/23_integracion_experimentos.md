# 23. Multisource integration and experimental methods

[English](../en/23_integracion_experimentos.md) · [Español](../es/23_integracion_experimentos.md) · [Português](../pt/23_integracion_experimentos.md)

## Align before combining

stack_layers, rgb_composite, pca_fusion and anomaly_coincidence stack or compare products. They need compatible CRS, lattice, scale, mask and units. Normalisation changes relative contributions: PCA on nT and mGal without a justified scaling rule may mainly reflect the largest numerical variance.

shift_without_wrap shifts an array without bringing values back through the opposite edge. It is not reprojection, trajectory correction or uncertainty-aware subpixel registration. Validate a shift search with independent points/features.

multisensor_project coordinates operations/publication; terrain_analysis produces relief attributes. vector_grid_audit compares polygon/grid support. Ensure zonal statistics do not mix masks, units or edge pixels differently between products.

## Anomaly catalogues

archaeology provides multiscale exploration, connected regions and feature retention. Outputs are thresholded field regions, not archaeological classifications, ages or UXO identifications. Higher retention relative to an initial selection can preserve noise if that selection lacks an independent reference.

process_effect compares GeoTIFF products. Define common support, masks, transforms and amplitude differences before interpreting a metric. Visual similarity alone cannot decide which filter best retains the desired signal.

## Height pairs and directional fusion

paired_flights differences fields on shared surfaces and normalises by vertical separation. Conceptually:

    G_apparent = (T_high − T_low) / (z_high − z_low)

It needs compatible heights, field baselines, horizontal support and separation gates. Separately background-corrected flights can yield a local-anomaly pseudogradient rather than an absolutely calibrated vertical gradient.

fuse_directions distinguishes common support from available coverage. Averaging two directions where both exist and retaining one elsewhere creates different support; retain contribution count and source. These Core capabilities are not recommended here as mandatory basic-processing steps.

No private acquisition heights, separations, sensors, sites or parameters are supplied. Historical experiments remain separate from generic recipes and need use-specific validation before scientific publication.

See [complete API](../../reference/api/en.md), [processing boundaries](../../validation/reports/processing_overlap_audit.md) and [integration references](../../research/core_expansion_implementation.md).

## Related implementation

[multisensor_fusion](../../../terraworkbench_core/multisensor_fusion.py), [multisensor_project](../../../terraworkbench_core/multisensor_project.py), [terrain_analysis](../../../terraworkbench_core/terrain_analysis.py), [vector_grid_audit](../../../terraworkbench_core/vector_grid_audit.py), [process_effect](../../../terraworkbench_core/process_effect.py), [archaeology](../../../terraworkbench_core/archaeology.py), [paired_flights](../../../terraworkbench_core/paired_flights.py), [crossovers](../../../terraworkbench_core/crossovers.py)

---

[Contents](README.md) · [Previous](22_ondas_sondeos.md) · [Next](24_gui_qgis.md)

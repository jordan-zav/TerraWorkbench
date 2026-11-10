# Documentation index

Read the complete 28-chapter manual in [English](manuals/en/README.md), [Español](manuals/es/README.md) or [Português](manuals/pt/README.md). It covers import, processing, inversion, uncertainty, GUI and APIs with figures and source-derived references. The [practical handbook](handbook/README.md) provides shorter trilingual method cards.


Documentation is separated by purpose:

- [Guides](guides/README.md): operational workflows and interface usage.
- [Reference](reference/README.md): method contracts, generated APIs and QGIS catalogues.
- [Development](development/README.md): architecture, ownership and standalone environments.
- [Validation](validation/README.md): reports and machine-readable public summaries and permitted campaign records.
- [Research](research/README.md): proposals and experimental scope, distinct from validated capabilities.
- [Legal](legal/README.md): third-party notices.

The [path migration map](path_migrations.json) records the former locations. Reports retain their historical language and stated scope. Test counts are snapshots, not current release certificates.

| Area | Entry points |
| --- | --- |
| Repository and contribution boundaries | [Repository structure](development/repository_structure.md) |
| Independent engine and API | [Scientific Core](development/scientific_core.md), [Core implementation scope](research/core_expansion_implementation.md), [typed workflows](guides/core_workflows.md), [standalone acquisition](development/standalone_acquisition.md) |
| Survey data and import | [Workspaces](guides/survey_workspaces.md), [survey explorer](guides/survey_explorer.md), [basic processing](guides/basic_processing_migration.md), [interpolation](reference/methods/interpolation_methods.md) |
| QGIS interface | [Workbench](guides/geophysical_workbench_gui.md), [localization](guides/localization.md), [Python API captures and evidence](guides/api_evidence.md) |
| Potential fields | [Magnetic components](reference/methods/magnetic_component_api.md), [compact sources](reference/methods/compact_magnetics.md), [apparent properties](reference/methods/apparent_properties.md), [terrain](reference/methods/adaptive_terrain.md), [isostasy](reference/methods/isostasy.md) |
| Calibrated radiometry, profile gravity and geostatistics | [2D extensions, contracts and validation](validation/reports/2d_extensions.md) |
| 3D inversion expansion | [Matrix-free storage, joint artifacts and linear uncertainty](validation/reports/inversion3d_extensions.md) |
| MVI evidence map (start here) | [Reading order and the operator, optimization, identifiability and geological questions](validation/mvi_evidence_map.md) |
| MVI independent references | [Public sources, native comparison and recovery controls](validation/reports/mvi_reference_validation.md) |
| Spherical MVI | [Staged API, angle conventions, storage and validation](reference/methods/spherical_mvi.md) |
| MVI causal audit | [Fixed-objective verification, null-space evidence and unresolved nonlinear fits](validation/reports/mvi_causal_diagnosis.md) |
| MVI numerical stability | [Stopping, zero-amplitude charts and failed angular searches](validation/reports/mvi_stability.md) |
| MVI IRLS strategies | [Adaptive default, frozen diagnostics, mixed-unit CG and chart safeguards](validation/reports/lagged_irls.md) |
| MVI outer budgets and prior sensitivity | [Adaptive continuation, frozen weights and beta controls](validation/reports/mvi_outer_sensitivity.md) |
| MVI acceptance and downloaded data | [Three geometries, public prediction references and field-format correction](validation/reports/mvi_acceptance.md) |
| Geological recovery validation | [Explicit spatial priors, body metrics and frozen multi-geometry campaign](validation/reports/voxel_recovery_validation.md) |
| Regularization recipe compatibility | [Physical gradients and normalized cell differences](reference/methods/regularization_conventions.md) |
| Structural interpretation | [Attributes](reference/methods/structural_attributes.md), [source depth](reference/methods/source_depth.md) |
| Inversion | [Standalone controls](development/standalone_inversion.md), [validation](validation/reports/inversion_validation.md), [public benchmark](validation/reports/public_inversion_benchmark.md), [resolution](validation/reports/inversion_convergence_resolution.md), [other methods](validation/reports/inversion_methods_validation.md) |
| Dispersive and stacked IP | [Cole-Cole and MVI controls](reference/methods/dispersive_ip_mvi.md), [current histories](reference/methods/ip_current_history.md), [explicit stacking](reference/methods/ip_stacking.md) |
| QA and research backlog | [Public processing campaign](validation/reports/public_processing_benchmark.md), [numerical/capacity checks](validation/reports/numerical_capacity_validation.md), [processing overlap audit](validation/reports/processing_overlap_audit.md), [research scope](research/geophysics_expansion.md), [candidate catalogue](research/geophysics_backlog.json) |

The handbook source and citation manifest are documented in
[the knowledge-base index](handbook/README.md). Original report evidence
remains in its recorded location; these documents do not embed private surveys.

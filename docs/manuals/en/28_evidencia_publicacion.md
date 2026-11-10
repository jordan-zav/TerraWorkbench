# 28. Scientific evidence, results chapters and publication

[English](../en/28_evidencia_publicacion.md) · [Español](../es/28_evidencia_publicacion.md) · [Português](../pt/28_evidencia_publicacion.md)

## Write verifiable results

An article should describe observations, metadata, transformations, parameters, uncertainty sources and acceptance criteria. Retain quantity names, units, signs, coefficient sources and model bounds. Citing a library identifies a component; it does not demonstrate correct local integration.

Recommended structure is abstract, introduction, data/methods, results, discussion, conclusions, availability and references. Manual chapters have objectives/procedures; a study must turn these into the recipe actually executed.

## Counts and partitioning

Report available, valid, selected, fitted and reserved rows separately. Importing a large database does not mean every point was inverted. Reserve lines/regions before selecting regularisation and mesh. A comparison reusing the same forward operator is not independent physics validation.

## Existing project evidence

The repository preserves public processing, inversion, extension and recovery campaigns. Check each date, source hash, dataset and criterion. Radon tests retain calibration/residual problems; some free-voxel geometries retain large model errors. Failures belong in evidence, not rows discarded to improve a summary.

| Question | Starting document |
| --- | --- |
| External-data processing | [Public campaign](../../validation/reports/public_processing_benchmark.md) |
| Public inversion replay | [Inversion benchmark](../../validation/reports/public_inversion_benchmark.md) |
| Solver and non-uniqueness | [Convergence](../../validation/reports/inversion_convergence_resolution.md) |
| Conditional/free recovery | [Voxel protocol](../../validation/reports/voxel_recovery_validation.md) |
| Electrical, EM and SP | [Method validation](../../validation/reports/inversion_methods_validation.md) |
| MVI and directions | [References](../../validation/reports/mvi_reference_validation.md), [acceptance](../../validation/reports/mvi_acceptance.md) |
| Metric files | [Benchmark index](../../validation/records/README.md) |

## Figures and tables

Generate figures from saved artefacts, retain the script and declare artificial-data seeds. Distinguish point maps, interpolated grids, model sections, conceptual diagrams and GUI captures. Every figure needs legend, units and support. Disclose clipped colour scales: clipped residuals may hide extremes.

Articles use Markdown, linked images and parameter/metric tables. Do not automatically generate PDFs. Check links, sources and that captures belong to an actual execution.

## Licences, data and responsibility

Software licensing does not grant rights over third-party datasets/reports. Public downloads may have their own terms. Before publishing, review licence, attribution, identifiers, integrity and whether bytes or only a download recipe may be redistributed.

Keep private acquisition data, personal paths, credentials, internal reports and site images outside public source distribution. These interface captures use artificial CC0 data; future real-data images require separately reviewed publication rights. Authorship, affiliation, funding and conflicts belong to the publishing authors and must be confirmed, not inferred from a Git username.

Future capabilities/benchmarks remain pending until executed. A backlog proposes work; it is not a completed-feature list. See [historical coverage](../../handbook/roadmap_cobertura.md), [licences](../../legal/THIRD_PARTY_LICENSES.md) and [manual sources](../es/fuentes.md).

---

[Contents](README.md) · [Previous](27_tutoriales.md)

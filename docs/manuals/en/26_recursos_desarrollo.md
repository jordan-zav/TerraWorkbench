# 26. Resources, tests, packaging and maintenance

[English](../en/26_recursos_desarrollo.md) · [Español](../es/26_recursos_desarrollo.md) · [Português](../pt/26_recursos_desarrollo.md)

## Avoid misleading estimates

N rows and M float64 channels need at least 8NM bytes in dense arrays before masks, copies, indices and buffers. Sensitivity memory also depends on observations and parameters. A file/matrix/interaction budget is not total process memory or a runtime guarantee.

Use column-selective reads, batches, bounded grids and explicit budgets. Storage capacity differs from a kernel's whole-array capacity. Some exploration, FFT and spectral modules need complete grids even when the source database is batch-readable.

## Reproducible environment

Record Python, platform, versions, executable and extras used. Reuse compatible native libraries. Separate shared caches from per-project/run temporaries. Local development uses launchers and workspace locks; avoid simultaneous writers to one catalogue/package.

Do not routinely delete partials/caches while processes or references depend on them. Retain originals, recipe backups and failure artefacts needed for diagnosis. Folder synchronisation is not a transactional SQLite/Parquet backup.

## Repository checks

| Check | Purpose |
| --- | --- |
| pytest | Contracts and regressions defined by individual tests |
| Ruff | Configured static error/style checks |
| check_core_install.py | Wheel installation and operation without checkout/host |
| check_localization.py | Authored three-language catalogues/text |
| export_handbook.py --check | Practical handbook consistent with GUI source |
| build_manual_reference.py --check | Chapter coverage and current AST inventory |
| check_manual.py | Links, images, format and evidence separation |
| package_plugin.py | ZIP metadata and allowed contents |
| qgis_*.py tests | Actual QGIS offscreen integration |

Passing a check means its criteria were met in that environment. Historical dates/test counts do not certify a different current version. Captures must correspond to declared source/data, not a drawing presented as execution.

## Contributing without duplicating engines

Numerical kernels belong in terraworkbench_core, widgets in ui and host adapters in qgis_plugin/algorithms. Preserve historical imports through compat rather than implementation copies. Assign new modules to chapters and update inventory, dependencies and relevant tests.

Plugin packaging uses allowlists. New documents/images need inclusion and size checks without adding datasets, credentials or internal reports. The standalone distribution contains the scientific package rather than the full interface.

See [organisation](../../development/repository_structure.md), [Core ownership](../../validation/README.md), [quality configuration](../../validation/README.md) and [packaging](../../../scripts/package_plugin.py).

## Related implementation

[_array_contract](../../../terraworkbench_core/_array_contract.py)

---

[Contents](README.md) · [Previous](25_api_workflows.md) · [Next](27_tutoriales.md)

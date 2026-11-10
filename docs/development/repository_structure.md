# Repository structure

The repository provides a QGIS plugin and the independent terraworkbench-core package. The root contains metadata, README files, license, public_manifest.txt and the QGIS bootstrap.

| Location | Responsibility |
| --- | --- |
| terraworkbench_core | Numerical kernels and data contracts, independent of QGIS and Qt |
| qgis_plugin | QGIS lifecycle, provider, raster and coordinate adapters |
| algorithms | Processing adapters delegating to Core |
| ui | Widgets, translated presentation and installed resource lookup |
| compat | Lazy historical imports; explicitly enable standalone aliases when needed |
| requirements | Runtime and optional scientific dependencies |
| assets | Runtime PNG branding and historical icons |
| embedded_qpip | GPL dependency-management integration with upstream notices |
| sample_data/synthetic | CC0 artificial examples |
| docs | Public methods, manuals, references and scoped validation summaries |
| scripts | Development, packaging, export and reproducible benchmarks |
| tests | Scientific regressions, manifest guards and explicit QGIS smoke scripts |

Use canonical terraworkbench_core imports for independent applications. UI resources resolve through ui/_paths.py. QGIS loads classFactory from the root __init__.py; legacy qualified imports remain lazy aliases to canonical modules.

Use any suitable isolated Python environment. Supply caches, outputs and profiles as command arguments or documented environment variables. The Core remains version 0.1.0 independently of plugin metadata. No workstation-specific launcher is needed.

The public manifest is the explicit source allowlist; the packager only includes its declared public runtime subset. The exporter creates a new directory and validates links, imports, privacy, tests and the extracted ZIP. The development archive keeps editorial documents, original execution records, third-party data and private workflows outside that boundary. See [the documentation index](../README.md), [scripts](../../scripts/README.md) and [tests](../../tests/README.md).

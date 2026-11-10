# Sources, versions and citation policy

[English](../en/fuentes.md) · [Español](../es/fuentes.md) · [Português](../pt/fuentes.md)

[Manual contents](../es/README.md)

## Source priority

TerraWorkbench capability descriptions are checked first against implementation and contracts. Method references explain context; linked campaigns document what was tested. External-engine capabilities are not automatically attributed to Core, and general references are not treated as independent code validation.

Signatures come from Python modules and Core IDs from the registry. Source hashes are LF-normalised for Windows/Linux verification. The QGIS catalogue comes from an actual registered provider and declares its runtime version.

Definitions without docstrings have separate authored notes. The reference also shows annotated option-class fields. SVG integrity uses LF-normalised text; PNG integrity uses exact bytes, avoiding confusion between Git line-ending changes and graphic alteration. Source docstrings and technical identifiers retain their original language; editorial navigation and supplemental notes follow the selected manual language.

## Primary references consulted for this edition

Documentary review: 6 November 2026. Latest/stable pages may change; actual dependency versions in execution records are also required for reproduction.

| Reference | Manual use | Scope |
| --- | --- | --- |
| [GDAL: raster data model](https://gdal.org/en/stable/user/raster_data_model.html) | Georeferencing, bands and masks | Raster contract, not complete local-importer validation |
| [PROJ: geodetic transformation](https://proj.org/en/stable/usage/transformation.html) | Projection versus datum transformation | Geodetic context, not certification of private heights |
| [SciPy: sosfiltfilt](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html) | Forward/backward filtering and edges | Library operator, not scientific cutoff selection |
| [Harmonica: prism_gravity](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html) | Prisms, components and units | Physical-engine contract |
| [IAGA / NOAA: IGRF](https://www.ncei.noaa.gov/products/international-geomagnetic-reference-field) | Main field and coefficients | Main-field model, not local anomalies |
| [SimPEG](https://simpeg.xyz/) | Simulation/inversion framework | Library capabilities differ from TerraWorkbench adapters |
| [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf) | Gamma spectrometry/calibration context | Method guidance, not universal instrument calibration |

Specific Euler, Werner, SPI, microlevelling, flexure, phase, log and IP-waveform bibliography remains in the specialised guides linked by each chapter. The [practical-handbook manifest](../../handbook/handbook_sources.json) connects its entries with sources. Historical entries are not presented as a new audit of every reference or licence.

## Evidence and results

Conceptual figures, artificial controls, synthetic-data GUI captures, contract tests and physical benchmarks are identified separately. Each scientific metric should lead to its result file and acceptance criterion. The public manual captures render actual widgets with bundled CC0 synthetic values, not a field survey, geological validation or a new inversion campaign.

The [benchmark archive](../../validation/records/README.md) retains achievements and limitations. Before citing a result, read protocol, date, source hash, error definition and whether geometry was fixed. Solver accuracy, data fit and recovery answer different questions.

## Maintaining the documentation

A new module needs a chapter assignment and regenerated reference. Signature/registry changes must fail the freshness check. Update affected examples and declare what was rerun; never rewrite historical campaign counts as if recalculated with new source.

The complete manual does not automatically alter the short GUI handbook. Its source remains ui/knowledge_content.py with a separate parity exporter. Scientific changes intended for that interface also need EN/ES/PT texts and matching contracts. Translated chapters share IDs and a source-revision manifest; structural parity is a maintenance check, not certification by an independent scientific translator.

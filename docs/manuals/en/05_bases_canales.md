# 5. Workspaces, channels, versions and lineage

[English](../en/05_bases_canales.md) · [Español](../es/05_bases_canales.md) · [Português](../pt/05_bases_canales.md)

## Storage model

SurveyStore combines a SQLite catalogue and immutable Parquet files. The catalogue identifies databases, channels, versions and events. Parquet supports column and batch reads, so processing one variable need not load every channel. A workspace is a working unit, not a proprietary GDB file.

A database preserves row alignment. Column selection leaves that alignment intact. A mask or view filter restricts a query; it does not automatically reorder acquisition. Stored geometry identifies XY channels and CRS without transforming coordinates.

## Your first database in the interface

Open the explorer, choose New project and an empty folder, then Import text / Parquet. Review the wizard before accepting the import. Select a database on the left and only the channels needed; Load selection displays a page rather than dumping all rows into the table. Channel actions prepare derived variables and expose their pipeline. Save important products outside session temporaries and retain the complete workspace folder.

![Channel versions](../assets/en/linaje.svg)

Figure 2. Conceptual sources and derived channels. The input version, in addition to its name, determines the content processed.

## Creating a derived variable

Name the quantity and unit first: mag_anomaly_nt, gravity_complete_bouguer_mgal or sensor_height_m. Add the distinguishing step when alternatives are needed, such as mag_anomaly_lowpass_nt. A label does not replace recorded parameters.

Formula expressions use a restricted arithmetic language. For example, c("field_nt") − c("main_field_nt") subtracts aligned channels. This is not a general Python interpreter and must not be used for imports or external instructions.

Derivation retains input versions. If content changed after recipe review, stop and review again. Duplicating a channel can alias the same immutable version without copying its full bytes; later versions evolve independently.

## Publishing external calculations

publish_channels receives arrays matching database row count, a unit per output, exact versions of the channels used and provenance naming the operation. Output names must be new. Outputs publish together transactionally; NaN becomes null, while infinity or incompatible lengths are rejected.

Recording parameters, libraries and engine makes them visible in the lineage inspector. Include topography, inducing-field and selection channels if they contributed, even when they do not appear directly in the final formula.

## Capacity and safe work

Total database capacity differs from a filter's per-run limit. Channel filtering supports up to three million samples per continuous run, subject to other budgets. A multi-line database can contain more rows. Do not concatenate lines to bypass continuity controls.

The published-array budget bounds their combined float64 size; it is not a process RAM limit and excludes engine buffers. Keep originals separate from derived files and back up catalogue and Parquet coherently.

See [workspaces](../../guides/survey_workspaces.md), [explorer](../../guides/survey_explorer.md) and [evidence contracts](../../guides/api_evidence.md).

## Related implementation

[survey_store](../../../terraworkbench_core/survey_store.py), [survey_explorer](../../../terraworkbench_core/survey_explorer.py), [survey_recipes](../../../terraworkbench_core/survey_recipes.py)

---

[Contents](README.md) · [Previous](04_importacion.md) · [Next](06_perfiles_qc.md)

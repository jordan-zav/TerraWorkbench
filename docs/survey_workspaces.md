# Survey workspaces

Open **Raster → TerraWorkbench → Survey databases…**. Create a project in a
new empty folder, or open an existing project. The most recent folder is
remembered; source surveys are never imported automatically.

```
project/
  catalog.sqlite       database/channel names, units, versions and operations
  databases/           immutable Zstandard-compressed Parquet files
  grids/               reserved for analysis grids
  results/             selected-channel CSV exports and QGIS point snapshots
  recipes/             reserved for saved processing recipes
```

## Working with channels

- Import text (CSV/TSV/TXT/ASC/DAT/XYZ) through the review wizard, or flat
  Parquet directly. Each input becomes a separate database. Multiple databases
  can be selected; the manager displays common channel names without merging rows.
- Text import suggests encoding, delimiter, header and first data line from a
  bounded sample. **Review each file**; guesses are not applied without approval.
  The numbered source, channel settings and parsed preview are separate tabs.
  Changing a setting invalidates approval: inspect the refreshed preview before
  confirming again. The source size/mtime is checked before full import.
- The wizard supports comma, semicolon, tab and pipe delimiters; whitespace
  tokenization (including quoted fields); and manually configured fixed widths
  in characters. CSV supports quoted separators and multiline quoted fields.
  Fixed widths reject nonblank trailing text rather than truncating it.
- Header and data rows are **physical one-based line numbers**, not observation
  indices. Header `0` means no header; names such as `channel_1` are generated.
  Choose the first data row to skip metadata/unit rows. Blank lines and configured
  whole-line comments are skipped. Comments inside quoted CSV values are retained.
- UTF-8/BOM, UTF-16/BOM and UTF-32/BOM are recognized. Windows-1252 is a tentative
  fallback, not a reliable universal encoding detector. Select Latin-1, CP850,
  endian-specific Unicode or another Python codec manually when necessary.
- Names, text/int64/float64 types, units and X/Y/time/line/sensor roles are editable.
  Type suggestions sample up to 100 records; leading-zero identifiers such as
  `001`, line/sensor IDs and time fields remain text by default. Ambiguous roles
  are left unassigned. Units in terminal brackets/parentheses are suggested.
  Time values are not parsed into a timezone; CRS is never inferred from names.
- Decimal dot/comma and explicit null tokens are configurable. Empty fields are
  null. Thousands separators are not interpreted; mark sentinels explicitly.
  Header duplicates/blanks receive editable generated-name suggestions.
- Preview and import share the same parser. Full import validates every row:
  wrong field counts, decoding failures, overflow or invalid typed values abort
  the database, reporting the physical line/channel where applicable. Values
  are not silently dropped or coerced to fit a sample-based guess.
- The original source is never modified. Accepted layout/type/role options are
  recorded with the import, and selected units enter the channel catalogue.
  Roles reference stable channel IDs, surviving later renames; they preselect
  X/Y in the QGIS export dialog, while CRS still requires explicit confirmation.
  The legacy programmatic `import_file` call without `text_options` retains its
  UTF-8/header/string-column behavior. Parquet retains its input types.
- Select channels for a read-only preview of up to 100 rows. Optional membership
  filters select lines, sensors or other channel values for preview/export.
- Calculate with `c("mag") - c("base")`, arithmetic `+ - * / **`, and
  `abs`, `sqrt`, `log10`. Powers require a constant from 0 to 16. The parser
  does not execute Python, access files or import modules. Non-finite results
  become null and their count is reported.
- Calculations apply to every row, not the preview filter. Multiple selected
  databases run sequentially. Each database commits independently; an error
  reports how many finished. Earlier completed results remain available.
- Imported channels cannot be overwritten by calculations. Reusing a derived
  channel name creates a new immutable version. Input version IDs are recorded.
  The current manager shows the latest version; old files and catalogue rows
  remain available, but a version-restoration GUI is not implemented yet.
- Duplicate creates a zero-copy reference to a fixed channel version. Rename
  and unit edits change catalogue metadata, not observations. There is no
  destructive delete or in-place cell editor in this release.
- Export reads only selected/filter channels and writes a new CSV under
  `results/`. **To QGIS points…** asks explicitly for X/Y and CRS, then adds a
  selected-channel CSV snapshot to QGIS. That layer can feed the existing survey
  gridding tool. This is a snapshot/export bridge, not a live Parquet QGIS provider.

## Performance and durability

### Coordinates and CRS

Select one database and open **Coordinates and CRS…** (no channel selection
required). The independent panel has two explicit modes:

- **Assign CRS** selects X/Y and a searchable QGIS CRS. It records metadata only;
  values and source files remain unchanged. Assignment is a declaration by the
  user, not proof that the chosen CRS matches the survey.
- **Reproject** selects source X/Y/CRS, target CRS and two unused output names.
  It transforms the entire database, ignoring preview filters. Both float64
  channels and their active geometry are published in one catalogue transaction.
  Existing channels remain unchanged. Any null input coordinate makes both
  output coordinates null; malformed, nonfinite or failed transformations abort.

The panel's information button identifies QGIS/PROJ and PyArrow/SQLite. The
worker disables approximate fallback transformations, records input versions,
CRS WKT, the instantiated PROJ operation and QGIS version, and supports
cancellation. Transformation accuracy still depends on the CRS, selected datum
operation and available grids. This is horizontal XY only, not a vertical-datum
or coordinate-epoch transformation. Geographic XY means longitude/latitude.
No area-of-use certification or field-scale throughput claim is made.

**To QGIS points…** reuses the saved active pair and CRS. Change them in the
coordinate panel. Existing map layers are snapshots and are not updated when
database coordinates change. With no saved geometry, the legacy explicit XY/CRS
prompts remain available. Channel renames preserve coordinate references by ID.

`tests/qgis_coordinates_smoke.py` checks all three UI languages, a known UTM
reference, reverse transformation and null preservation in real QGIS.

Original imports share a columnar Parquet file. A calculated channel writes only
one additional column, avoiding full-database rewrites. Blocks contain at most
65,536 rows. The configurable text parser flushes earlier at an estimated 8 MiB
of buffered Python values; legacy CSV parsing uses Arrow input blocks. Detection
reads at most 256 KiB and 500 sample lines; source display shows up to 80 lines
and the parsed preview up to 30 observations. Python's CSV field-size limit and
an explicit 4 MiB physical-line character limit reject excessively large records.
Preview, calculation and export use background workers with cooperative
cancellation between batches. Only selected columns and filter columns are
decoded. Line/sensor filtering still scans those columns: there is no spatial
index or partition-pruning guarantee in this first version. Memory also depends
on selected channel count and individual string lengths.

SQLite uses short transactions, foreign keys and a lock timeout. Files are
closed before their versions are published in the catalogue. A canceled or
failed operation removes its own unpublished files. A process/power failure
can leave orphan files; automatic orphan cleanup is deliberately not provided.
The design is a local single-user project store, not a multi-user server.
Use a local disk for active work; copying the whole closed project folder is
the backup/transfer mechanism. Do not synchronize or edit its internal files
while jobs are running. Catalogue-level visibility is transactional, but this
is not a claim of power-loss durability across SQLite and Parquet together.

The raster Filter Stack still has its own output-folder setting. `grids/` and
`recipes/` are reserved locations, not an automatic migration of existing paths.
GeoTIFF processing algorithms may still require whole rasters or point arrays;
columnar storage does not make all numerical algorithms out-of-core.

## Dependencies and verification

### 1D channel filters and per-channel pipelines

**Filter channel…** works on one channel in one database per run, without
gridding. Select line and sensor channels or explicitly declare a single series.
Choose sample order, numeric time in seconds, or cumulative distance in metres.
Distance must be an existing increasing distance channel, not an X/Y coordinate;
timestamps must first be converted to numeric seconds. Original row order is
preserved. Group transitions, missing signal/axis/group values and axis gaps
above the user threshold split the signal into independent contiguous runs.
Repeated or decreasing axes within a run abort; the tool never sorts, joins
interleaved runs, interpolates holes or resamples silently.

Available operations:

- Centered moving mean and median with an odd sample-count window. Only complete
  windows are calculated; incomplete edges are null, without artificial padding.
- Hampel despiking: local median and median absolute deviation, scaled by 1.4826.
  Values beyond the selected robust-sigma threshold are replaced by the median.
  When MAD is zero, nonzero deviations are flagged; constant values are retained.
- Least-squares linear detrend using the actual axis coordinates, not row index
  when time/distance is selected. Both offset and slope are removed per run.
- Butterworth low-pass, high-pass and band-pass using SciPy `butter` with SOS and
  `sosfiltfilt`. The implementation uses forward/backward zero-phase filtering and
  odd endpoint padding. The amplitude response is squared and the effective order
  doubles; supplied cutoffs are single-pass design frequencies, not compensated
  final -3 dB frequencies. Cutoffs are cycles/sample, Hz or cycles/metre. Sampling
  must be regular within the explicit tolerance (default 1%); cutoffs must be below
  the run's Nyquist frequency. No automatic resampling is provided.

Short runs produce nulls, with counts in the result and provenance. If no valid
output remains, the operation fails without publishing a channel. Invalid text,
infinite values, cancellation or a later-run failure rolls back the whole output.
The full database is processed, not the preview/export subset. Only signal,
axis and grouping columns are read. Runs cross storage-batch boundaries; each
finite run is held in memory with a hard limit of three million observations.
This is a per-contiguous-transect/sensor-segment limit, not a database row limit;
larger databases are processed as separate runs when the line/sensor grouping
is selected correctly. Raising this limit increases peak memory requirements.
Window work arrays are bounded. This is not a guarantee of arbitrary-size
out-of-core filtering or field-scale performance.

Suggested names encode source, method, principal settings and axis domain, e.g.
`mag_corrected__median_w5_time` or `mag__lowpass_n4_f0.1_distance`. Names are editable
and collisions get a suggested suffix; existing channels are never overwritten
or automatically renamed. Output units are inherited from the signal channel.

**Channel pipeline…** opens a native flow graph for one selected channel. It
resolves exact input versions recursively, including imports, formula branches,
duplicates, coordinate reprojections and channel filters. Renames change display
labels but do not change version links. Each node exposes its recorded provenance,
parameters, source versions and available library information. Filter provenance
also records library versions, grouping, missing-output counts and spike counts.
Historical operations display the metadata they actually recorded; unknown
details are not reconstructed. The diagram supports zoom, fit, node selection
and copying the entire pipeline as JSON. It is an inspector, not an editable or
executable pipeline designer. Graphs are limited to 200 version nodes.

Algorithm definitions and dependencies are available via the process's **i**
button. No Oasis algorithm equivalence is claimed. Reference API:
[SciPy forward/backward SOS filtering](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html).
Tests include analytical frequency separation, Hampel/median/mean/detrend,
cross-batch run isolation, nulls, invalid sampling, cancellation and rollback,
versioned branching lineage, and real QGIS UI/worker/graph checks in EN/ES/PT.

SQLite is provided by Python; PyArrow is an explicit runtime dependency and
uses the Apache-2.0 license. No GDB or Oasis runtime is required for this store.
[Arrow Parquet documentation](https://arrow.apache.org/docs/python/parquet.html)
and [batch-reading API](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetFile.html).

Tests cover selected columns, identifiers, filters, multiple batches, derived
versions, duplicate references, renaming, null arithmetic, cancellation,
name conflicts, safe formulas and export overwrite protection. No user survey
files are changed by tests. Field-scale performance and concurrent network-share
access are not certified.

## Connected magnetic backend

`SurveyStore.level_lines()` accepts explicit crossover tuples `(traverse, tie,
residual)` from the crossover backend. It solves robust constant corrections and
atomically publishes two new channels: correction and corrected signal. It reads
only the signal and line columns in batches, preserves null signal values, and
rejects unconstrained lines instead of assuming a zero correction. Provenance
includes exact input versions, crossover hash, constants, quality statistics and
NumPy version. Original channels remain untouched.

`SurveyStore.magnetic_grid_pipeline()` connects a correction channel to an
existing magnetic template. This is **not raw-point gridding**: it rasterizes
distance-sampled line corrections, nearest-fills that correction surface, applies
Gaussian smoothing, and adds it to the original template. Rows must be ordered
and contiguous per line. Database XY and template must share a projected metre
CRS; reprojection is explicit, never guessed. The template's support is retained.

`MagneticPipelineOptions` makes horizontal derivatives (`fft` or
`finite_difference`), angle units (`radians` or `degrees`), declination frame,
continuation height, detrending, taper and per-axis cell padding explicit.
True-north angles require caller-supplied grid convergence. The pipeline fills
NoData only in the FFT workspace, pads once, and retains padded RTP through all
derivatives and continuation. Only final products are cropped and masked.
Temporary filling can influence values near holes; it does not create observed
data or certify edge quality. Existing individual composite algorithm defaults
remain unchanged for compatibility with saved recipes.

Outputs: RMI, RTP, DX, DY, DZ_1VD, DZ2_2VD, THDR, AS, 45HG, Tilt, TDX, Theta,
upward continuation, residual and correction surface. Each immutable grid job
contains GeoTIFF units/NoData metadata and `recipe.json` with input version IDs,
template SHA256, parameters and NumPy/SciPy/GDAL versions. Partial outputs are
removed on cancellation or failure; successful jobs are recorded in the catalog.
NumPy supplies FFTs and algebra, SciPy supplies nearest fill/Gaussian smoothing,
PyArrow supplies columnar channels, and GDAL supplies GeoTIFF/CRS I/O.

This API is backend-only; no new GUI controls are added. The reproducible
`scripts/validate_hydraulic_connected.py` compares 14 products with the historical
Hydraulic reference using an existing finite-observation extraction and native
crossover results. It is not validation of the GDB reader, new interpolation,
inversion, eight-million-record capacity or all archaeology workflows.

`tests/test_text_import.py` covers separator/header inference, preambles, decimal
comma, encoding, quoted values, fixed widths, type overrides, leading-zero IDs,
out-of-preview errors, renamed role channels, block limits and cancellation.
`tests/qgis_text_import_smoke.py` exercises the ES/EN/PT wizard and mixed-format
multi-file import through the workspace action.

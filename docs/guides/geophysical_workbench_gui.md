# Geophysical workbench

TerraWorkbench is a general geophysical engine and QGIS workbench. ARCHIE is a
reference for interaction detail, not a restriction to archaeology or a second
numerical engine. This interface update does not copy acquisition parameters,
private surveys or experimental archaeological workflows into the repository.

## Entry points and scope

Raster → TerraWorkbench → Geophysical processes opens the complete registered
QGIS provider and the curated Core operation registry. The survey workspace
also has an All geophysical processes button. The current snapshot contains
95 QGIS forms and 120 Core entries in the 6 November 2026 inventory; see the
[actual QGIS catalogue](../reference/catalogues/qgis.md) and the
[source-derived Core reference](../reference/api/es.md). Entries can wrap related kernels; these counts are not counts of
independent methods or proof of complete geophysical coverage.

QGIS forms are listed first, grouped by their actual Processing categories.
The catalogue searches names, groups, numerical domains and exact identifiers.
Each entry explains its contract, inputs, implementation libraries and available
limitations. Optional packages are declared by the Core extras; discovery does
not install them. Opening a form does not execute a calculation.

Magnetic/gravity grids, corrections, radiometry, survey preparation, gridding,
leveling and potential-field inversion retain the existing QGIS forms. The Core
registry additionally includes electrical/IP, FDEM/TEM/MT, self potential,
waveforms, GPR, passive seismic, borehole, spectral and uncertainty primitives.
It is curated, not an exhaustive list of every historical Python utility.

## GRD filter workflows

Import survey grid accepts Geosoft binary GRD through Harmonica and saves a
GeoTIFF at a user-selected destination; this import is not automatically
temporary. The original GRD is unchanged and the new layer becomes the workflow
input, even when another raster was already selected. Other GRD variants are
not certified by the Geosoft binary import test.

Select a workflow step and use Parameters to reopen its inspector. Numeric
filter parameters include cutoff wavelength, order and FFT preprocessing where
applicable; invalid values block execution. The inspector labels in this tested
workflow support English, Spanish and Portuguese. This does not certify every
advanced Core docstring or API identifier as translated.

An empty workflow output folder uses temporary processing rasters. Selecting an
output folder creates a separate run directory with a recipe and optional
intermediate GeoTIFFs. The importer and workflow do not export Geosoft GRD.

The offscreen test tests/qgis_grd_workflow_smoke.py imports the bundled public
magnetic GRD, compares converted values with the source reader, runs Butterworth
and nine-point smoothing at two cutoffs, and checks geometry, masks, unchanged
source SHA256 and identical numerical results across the three UI languages.

## Advanced Core console

Core entries open an argument-by-argument form generated from the real function
signature, with authored labels, declared units, native choices, typed validation,
required arguments and documented API defaults. No physical values are invented
for required fields. Verified Euler quality and layered-EM geometry forwarding is
exposed in the form. Other forwarded keyword arguments retain an expandable JSON
object editor. NPZ selectors display bounded header metadata without loading array
payloads. Advanced JSON remains available. Read the function
contract for units, coordinate conventions, shapes and source-model assumptions.

An attached NPZ supplies named arrays through @array_name in the argument form,
or a one-key object with $array in JSON. Loading settings restores parameters,
not a certified identical-data replay; input arrays must be reattached and
reviewed. NPZ supports real and complex arrays without pickle. Object arrays,
duplicate JSON keys, oversized headers/allocations and unsupported archive
members are rejected. JSON input is limited to 1 MiB; NPZ input arrays to
256 MiB; result arrays to 128 MiB and 256 arrays. Typed result metadata is
limited to 4 MiB and 100000 descriptor elements. These are I/O budgets, not
guarantees about solver working memory or execution time.

Run is an explicit user action. The console executes only registered functions;
it never evaluates Python source. Each successful publication creates a unique
subfolder containing arrays.npz and manifest.json. The manifest retains the
typed result structure, masks, complex phase, explicit parameters, input/source
hashes, package versions, UTC and solver status. Checksums identify content and
detect accidental alteration; they are not signatures proving authenticity.
load_core_job verifies and reconstructs the typed artifact without executing a
method. The GUI shows bounded numerical/structural previews, not full array dumps.

Nonconvergence remains not_converged and pauses subsequent jobs. A completed
operation is not necessarily a converged inversion, an accepted source-depth
solution or a valid geological interpretation. Source-depth catalogues must be
checked for accepted/rejected solutions and their quality controls.

## Loading parameter recipes

Recipe-file loading reads at most 6 MiB plus one sentinel byte and limits the
displayed parameter JSON to 1 MiB. Duplicate keys, nonfinite parameter values,
wrong-operation manifests and invalid UTF-8/JSON are rejected before replacing
the current edits. Field values are preflighted before form updates. A successful
load clears NPZ metadata/selectors and requires input arrays to be attached again;
a failed load retains existing form/JSON edits, paths and array selections.

## Source-depth method controls

The grid source-depth console has separate grid-input and method-control tabs.
Euler exposes its structural index and quality controls; Werner exposes window
and interference settings; SPI exposes its source model and peak controls.
Switching methods retains separate drafts but only the active method is sent
to the engine. Loading a recipe resets inactive drafts. Elevation and derivative
arguments supplied internally by the grid facade cannot be overridden by method
options. Saved parameter JSON uses the unchanged flat execution contract.

## Task queue

The Core console can queue at most 20 parameter snapshots. Reorder or cancel
pending jobs, or pause subsequent jobs. The current kernel is not paused by
that control. Jobs run sequentially; internal recipe steps retain their order.
Queued NPZ files must remain unchanged: a changed file identity/size/timestamp
is rejected before execution, and reads check for concurrent file changes.

Cancellation is cooperative only where the engine exposes a checkpoint callback.
Other kernels finish computing before the request is acknowledged; unacknowledged
requests are never labelled cancelled. A failure, cancellation or nonconvergence
pauses following jobs for review. Closing cancels pending jobs and waits for an
active worker to acknowledge cancellation/finish. This is a session queue, not a
restartable distributed scheduler, dependency-DAG manager or pause/resume solver.
Partial publication folders are retained on failure/cancellation for diagnosis;
source files and existing result folders are not overwritten or cleaned up.

## Database and channel review

The database explorer provides column-selective paginated tables, bounded
transect/sensor discovery, CSV-compatible filters and read-only profiles.
Profiles support physical distance from saved XY/CRS, zoom/pan/fit, cursor
coordinates, PNG view export, A/B overlays and paired B-minus-A statistics.
Identical explicitly declared units are required; there is no automatic matching
of samples or conversion of units. Display envelopes never replace source values
or full-selection statistics. See [database explorer](survey_explorer.md).

Physical distance uses the optional coordinates extra (PyProj), declared in
the QGIS requirements as well. It is imported only when distance is requested.

The channel pipeline provides an immutable-version graph, readable inspector,
technical JSON and navigation to parent versions. Formula/filter steps can be
edited and run as new channels, rejecting silently substituted newer upstream
versions. Reuse is one step, not automatic replay of all ancestors. The raster
stack retains save/load/edit/rerun of its ordered recipe. Its GUI creates a
unique run subfolder instead of overwriting a previous run in the selected
output folder, and saves a compatible recipe beside the result. Source file
metadata is recorded as metadata, not falsely labelled a content snapshot;
implementation hashes cover the selected algorithm modules, not all dependencies.

## Raster stages

Review last run stages opens native QGIS A/B map canvases and the exact saved
step settings. Pan/zoom and linked extents use the host map engine. Preview
diagnostics read at most 512 by 512 nearest-sampled pixels per grid, retain
NoData masks, and apply recorded GDAL band scale/offset explicitly. The original
grid geometry, CRS, band, declared unit and sampled flag remain visible.

B-minus-A diagnostics and a shared display stretch require compatible full-grid
geometry and CRS, and identical declared units. Missing unit metadata requires
an explicit reviewer declaration, which does not modify the raster. Different
units or geometry are refused rather than silently transformed. Statistics are
for preview cells; large-grid results are not full-grid statistical audits.
Map views do not rewrite source values. Temporary stages may cease to exist
after the host session; save intermediates when persistent review is required.

## Verification and remaining boundaries

Tests use synthetic inputs and real offscreen QGIS in English, Spanish and
Portuguese. They cover catalogue discovery, actual form construction, Core
execution/artifacts, task states and queue ordering, pagination, profile distance
and comparison, immutable source/history, recipe reuse, native map canvases,
NoData/geometry/unit guards and plugin packaging. They do not establish field
validation of every registered algorithm or equivalence to proprietary software.

Specialised guided forms, plotting and acquisition-format importers are not
implied for every experimental Core entry. Core JSON/NPZ jobs do not automatically
become spatial database channels or georeferenced grids. Scientific validation,
field-survey acceptance and formal publication remain separate work.

# Evidence through the Python API

Numerical processing runs through terraworkbench_core without launching QGIS.
Rendering existing QGIS widgets requires the QGIS Python runtime, with Qt set
to the offscreen platform before application initialization. This is a widget
render, not a capture of the user's desktop. No REST server is required.

## Numerical and channel contracts

SurveyStore.publish_channels accepts row-aligned numeric arrays, an explicit
unit for each output, exact input channel version IDs and a provenance object
with an operation name. Output names must be new. NaN becomes a null value;
infinity and mismatched row counts are rejected. The catalogue transaction
rechecks inputs and publishes all output channels together. It refuses stale
input versions and never replaces a source channel. A byte budget bounds the
combined float64 output size, excluding caller-owned input arrays and library
overhead. Supply parameters, libraries and engine in provenance to make them
visible in the existing channel pipeline inspector.

The inversion_evidence module supplies spatial_holdout, training_plane and
predict_susceptibility. The first selects actual observations nearest occupied
bin centers and reserves every nth bin before fitting. The plane uses only
training values. The forward predictor requires an explicit inducing field;
its declination is clockwise from mesh positive Y. True-north declinations
must be converted when a projected grid has meridian convergence.

run_inversion_workflow remains the numerical entry point and saves the model,
VTK, data CSV and run manifest. Freeze the recipe before fitting, retain source
hashes and report training and reserved-point errors separately. Reserved
locations from the same survey are not independent geological ground truth.

## Offscreen UI API

Initialize QgsApplication with an isolated profile directory, set the Qt
settings location and organization before constructing any widget, and set
QT_QPA_PLATFORM to offscreen. Reuse the installed QGIS runtime. The caller
owns application lifetime and must keep it alive until workers have finished.

ui.evidence_api.capture_widget takes a widget and a new PNG destination, with
bounded width and height. It refuses overwrites and any non-offscreen Qt
platform. It renders the actual widget after processing pending events.

ui.evidence_api.capture_workspace takes a workspace path, database ID, selected
channel names and a new PNG destination. It opens the existing workspace,
loads its real paginated preview, waits for the worker and captures the result.
The optional workspace_label changes only the displayed path label, allowing public screenshots to use a dataset title without exposing workstation paths. It does not rename or modify the database.

scripts/capture_documentation.py exposes this API through the QGIS Python launcher. Required flags are --workspace, --output and --profile-dir; choose --database-id, --channels, --language and --dataset-label for a real survey. Optional --filter-channel and --filter-values constrain the preview. --manual-output captures the actual 28-chapter reader, and --catalog-dir exports the registered provider catalogue. New PNG destinations and isolated profile directories preserve prior evidence and user settings. scripts/capture_manual_ui.py retains the earlier command entry point.
Optional filter_channel and filter_values configure a real read-only view
filter. ChannelPipelineDialog can be passed directly to capture_widget using
the graph returned by SurveyStore.channel_pipeline. CoreParameterForm can be
populated from the persisted executed recipe; verify parameters() round-trips
the values before capturing it in each language.

## Report and privacy boundaries

Write scientific evidence as a Markdown article with a summary, introduction,
methods, results, discussion, conclusions, references and linked PNG figures.
State imported, fitted and held-out observation counts in the summary. Separate
completed experiments from proposed validation. Use tables for the actual
executed parameters and metrics, and give every figure a numbered caption.
Keep image paths relative so the article and its existing image folders can be
shared together. Do not generate PDFs unless explicitly requested.

Generate scientific figures from persisted arrays, label widget renders and
result figures distinctly, and visually inspect the linked images. Record
the actual numerical source hash and dependency versions in execution
manifests. State assumptions about CRS, vertical frame, sensor geometry,
uncertainty, regional separation, sampling and induced versus remanent fields.

Keep private reports, survey metadata, captures, workspaces and reproducibility
runners outside Git. A local field run establishes only its stated execution
and predictive-validation scope; it does not certify all methods or establish
voxel recovery. Public benchmarks require redistributable inputs and their
own provenance and acceptance criteria.

Public manual captures use <code>python scripts/capture_manual_ui.py --synthetic --language en --output NEW_FOLDER --profile-dir NEW_PROFILE</code>. Repeat with es and pt. The command imports the bundled CC0 sample CSV, renders the actual widgets and preserves original inputs; it does not invert a survey.

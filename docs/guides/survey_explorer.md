# Database explorer

The survey workspace separates databases and common channels in a resizable
sidebar. Channel operations remain available in Channel actions. The right side
contains Table and Profiles tabs. Labels are available in English, Spanish and
Portuguese. This adapts the explorer pattern from ARCHIE to native Qt/QGIS;
scientific operations and stored recipes are unchanged.

## Table

Select one database and one or more channels, then choose Load selection.
Pages contain 200, 500 or 1000 selected rows, with First, Previous and Next
navigation. Row numbers refer to the filtered selection, not original file row
numbers. The database row total is unfiltered. Changing channels, filters, page
size or channel versions resets navigation on the next load.

Only selected columns and filter columns are read through PyArrow batches.
Offsets scan preceding selected rows; this is not an indexed random-access
table. The reader looks ahead by one row rather than scanning to calculate a
filtered total. Table editing is disabled.

## Profiles

Choose the value channel and optionally a numeric X channel. The default X axis
is the one-based selected-sample ordinal, not elapsed time or distance. No
sorting, interpolation or CRS transformation occurs. Physical distance is an
explicit separate option using the saved X/Y channels and declared database CRS.
It reuses the Core distance implementation, supports projected/geographic CRS,
and restarts at each continuous valid run; coordinate gaps are never bridged.
Numeric text is accepted; malformed numeric text produces an error.

Choose transect and sensor columns and enter comma-separated values to narrow
the selection; blank values include all. These selectors also apply to table
preview and export. An additional filter is available. Repeated filters on the
same channel are intersected. Processing actions retain their own scope prompts.

Profiles preserve null gaps, changes between contiguous transect/sensor runs,
and nonincreasing explicit X values. Separate runs are not connected. Invalid
values or missing group identifiers are excluded. Statistics use every valid
sample in the loaded selection: minimum, maximum, mean and population standard
deviation. These are descriptive statistics, not a quality certification.

The profile preview accepts up to 3,000,000 selected rows and 256 contiguous
segments. Larger selections must be narrowed by transect or sensor; these are
preview limits, not database capacity limits. At most 6000 points are rendered
using a min/max envelope, with a visible reduction notice. Source values and
statistics are not replaced by the reduced display values. Long reads run on a
cancellable worker. NumPy supplies statistics and envelope selection, PyArrow
supplies column reads, and Qt paints the graph without a plotting dependency.

## Verification

Pure reader tests cover batch boundaries, look-ahead pagination, filtered
offsets, profile gaps, X resets, envelope spikes, full-selection statistics,
budgets, malformed values and cancellation. Offscreen real-QGIS tests exercise
pagination, filter resets, transect/sensor profiles and immutable input/history
in all three languages. Existing workspace and channel-pipeline smoke tests
remain in place. These checks use synthetic inputs, not private survey data.

## Pipeline stage inspector

Channel actions → Channel pipeline opens a graph and an inspector. A stage
selector navigates from sources toward the selected output; clicking a graph
node or an input link selects the same exact immutable version. Selected output
returns to the root channel. Current channel names and units are labelled as
current metadata, not assumed to be their historical values.

Step details shows recorded parameters, formulas, parent versions, libraries,
engine metadata and execution statistics where available. Missing library or
parameter records are explicitly identified, never reconstructed from the
current installation. All stored settings are displayed, including settings
that may be inactive for the selected process. Technical JSON preserves the
full original node record in a separate tab.

Copy step JSON copies the selected version record; Copy pipeline JSON copies
the full ancestry. Copying JSON does not run a recipe. Edit and run step opens
the existing formula/filter editor and creates a new channel after confirmation.
Renamed inputs are resolved by immutable version; newer input versions are not
silently substituted. The worker checks reviewed versions again before reading.
The new provenance records the reused source version. Other step types remain
inspectable; full ancestry replay is not implied by single-step reuse.
Labels support English, Spanish and Portuguese, and channel names are escaped.

Profiles include zoom, pan, cursor coordinates, fit and PNG export. A/B overlays
and B-minus-A diagnostics require identical explicitly declared units. They use
matching database row positions, not interpolation or spatial matching. Difference
statistics exclude any pair with a missing value. Display reduction remains
separate from full-selection statistics.

Transect/sensor values can be discovered from selected columns in batches. The
selector list is limited to 2000 unique values per column with an explicit notice;
manual CSV-separated values, including quoted identifiers, remain available.
View/export controls are collapsible, with an active-filter count kept visible.

The workspace keeps up to 100 session task records with actual completion,
failure, cancellation acknowledgement, reported progress and elapsed time.
Cancellation requests are not presented as cancellation until the worker reports
it. The catalogue history remains the persistent processing record.

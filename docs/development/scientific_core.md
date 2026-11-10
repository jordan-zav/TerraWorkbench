# Shared scientific core (first extraction)

The October 26 follow-up adds standalone acquisition/QC, IGRF, finite-DEM
terrain and horizontal coordinate APIs. See [acquisition APIs](standalone_acquisition.md)
for units, optional engines and the remaining host/scale boundaries.

Install the standalone distribution with python -m pip install . from this
repository, or install its wheel. Only terraworkbench_core is distributed;
the QGIS plugin, private data and validation datasets are not in the wheel.
NumPy and SciPy are required; pip install '.[prisms]' adds Harmonica for the
finite-prism isostatic model. The FFT implementation does not need that extra.

    from terraworkbench_core.gravity_corrections import normal_gravity_grs80
    print(normal_gravity_grs80([0., 45., 90.]))

The first extraction covers spectral filters, basic processing, gridding,
channel filters, magnetic pipelines/corrections, line leveling, gravity
reductions, isostasy and radiometry. Numerical implementations live in exactly one place.
Legacy root modules forward imports to the bundled core so existing QGIS
algorithm identifiers and recipes keep working. The QGIS ZIP includes its
own core and does not depend on a separately installed package.

The scientific package must not import QGIS, Qt or plugin adapters, directly
or indirectly. Tests enforce imports with QGIS and Qt blocked. Public APIs in
this initial 0.1 release remain experimental.

The inversion engine is also available in the core; see [standalone inversion](standalone_inversion.md).

Source-depth interpretation now includes Euler, Werner and profile SPI; see [methods and limits](../reference/methods/source_depth.md).

SurveyStore, survey_text_import and database-to-grid orchestration now live in the
core. Historical root imports remain compatibility adapters, with the same
SQLite catalogue/Parquet format and channel version ancestry. The optional
storage extra declares pyarrow. Raster export still requires a compatible
native GDAL installation, loaded only when invoked, not bundled in the wheel.
Installed-wheel checks cover import, column selection, formulas, geometry/CRS
metadata and channel lineage without QGIS or checkout access; they do not
certify an independently installed GDAL export stack.
The historical terraworkbench_core.text_import table API remains unchanged;
its pandas reader uses the optional tables extra. The root text_import module
continues to expose the survey parser, not the different historical table API.

Not yet extracted: remaining GDAL/raster and CRS adapters, some other kernels,
and remaining scientific orchestration in Processing wrappers.
This is not a complete standalone replacement for every QGIS workflow.
Android/ARM compilation, mobile bridges and performance are not validated.
No proprietary numerical equivalence is implied.

## Radiometric profile processing

radiometry.live_time_correction accepts interval-normalized count rates and
measured live time in milliseconds. It is separate from the non-paralyzable
dead-time model. Zero, missing or over-interval live times produce NaN; raw
negative rates are rejected. Do not correct a live-time-normalized rate twice.

radiometry.accumulated_profile_ratios requires explicit K/U/Th sum thresholds,
minimum potassium and maximum radius per side. It grows centered windows until
all three thresholds are reached; insufficient support remains NaN. Edges use
available samples. Missing, negative and low-K samples break a segment. Profile
IDs must additionally distinguish acquisition time gaps. Outputs contain ratios,
sample counts and a serializable recipe. This policy is deliberately explicit,
not a recovered historical algorithm. Inputs are concentration channels, not
raw detector counts. It currently operates on arrays in memory.

These APIs are not all exposed as specialised QGIS forms or SurveyStore
operations. Registered operations are also available through the advanced
JSON/NPZ Core console; this does not imply a discipline-specific workflow.
Raw-spectrum NASVD and covariance-aware processing
are now implemented separately in radiometric_spectra. radiometric_radon adds
a calibrated paired-detector temporal proxy with conditional uncertainty;
full atmospheric-radon reconstruction remains pending. Existing QGIS radiometry
retains its behavior.

## Standalone expansion

The new operation catalog provides spectral interpretation, equivalent sources,
gravity tensors/network adjustment, raw-spectrum radiometry, electrical/IP
primitives, layered DC/FDEM/TEM/MT and linear inversion diagnostics. See
[implementation and limitations](../research/core_expansion_implementation.md). The 128-item
research backlog is not a list of completed methods. New operations remain
experimental and require independent field validation.

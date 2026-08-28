# TerraWorkbench

TerraWorkbench is an independent QGIS plugin for geophysical data. It exposes selected functionality from the Harmonica library as native QGIS Processing algorithms, including batch processing and graphical Model Designer support, and provides a dockable Filter Stack for interactive multi-step workflows.

The project is not an official product of Fatiando a Terra.

## MAG exploration filters

- DX and DY first horizontal derivatives
- DZ first and DZ2 second vertical derivatives
- UC500m upward continuation
- RS residual enhancement
- THDR total horizontal derivative
- Tilt angle
- Directional horizontal gradient with configurable azimuth
- AS / ASA analytic signal amplitude
- TDX horizontal tilt angle
- Theta angle map

The provider also includes Bouguer correction, configurable upward continuation,
Gaussian low-pass and high-pass filters, reduction to the pole, and configurable
directional derivatives.

## Magnetic field corrections

- Reduction to the pole (RTP) with automatic IGRF-14 or manual field direction
- Reduction to the equator (RTE)
- General source-to-target magnetic field-direction transform
- Survey date read automatically from imported metadata, with manual override
- Optional remanent magnetization direction and an explicit maximum-gain cap

Automatic mode evaluates IGRF-14 at the raster center, survey date and observation
altitude using `ppigrf`. Inclination is positive downward and declination is
clockwise from geographic North. The gain cap is required because RTP/RTE can be
ill-conditioned, especially at low magnetic latitudes.

## Survey grid import

The **Import** menu converts source data to analysis-ready GeoTIFF without changing
the original survey files:

- Oasis montaj binary `.GRD` through Harmonica, including `.GRD.xml` title, CRS/EPSG,
  survey dates and line metadata
- GDAL raster formats including GeoTIFF, GXF, AAIGrid/ASCII and regular XYZ
- Complete regular CSV/ASCII grids with X/Y/value columns (irregular points are
  rejected instead of being silently interpolated)
- Raster datasets stored in Esri FileGDB folders, with subdataset selection

A single-file Geosoft `.gdb` is a proprietary channel database and is not an Esri
FileGDB. TerraWorkbench remains open source and does not bundle Geosoft code, but it
can optionally use a separately installed and licensed Oasis montaj runtime. It first
checks the conventional `Program Files/Geosoft/Desktop Applications` location, then
the saved location, then performs a bounded Geosoft/Seequent folder scan. If nothing
is found it asks the user to locate the installation and remembers that choice.

The **GeoDatabase (Oasis montaj) inventory/export** command validates `bin/omscore.exe` and the
adjacent Geosoft Python runtime. It can create a fast inventory or stream every
numeric channel to open CSV without changing the source GDB. TerraWorkbench then
adds the point dataset, line inventory and channel inventory directly to QGIS with
the recovered coordinate-system WKT. These exported files remain usable without
Oasis montaj. Full extraction may be substantially larger than the original
compressed database.

## Survey point gridding

After a full GeoDatabase extraction, TerraWorkbench offers to open **Grid survey
points to GeoTIFF** with the recovered point layer already selected. Choose the
magnetic, gravity or radiometric channel and configure:

- Projected output CRS; geographic inputs default to their local WGS 84 UTM zone
- Cell size, or `0` for a density-based estimate
- IDW or nearest-neighbor interpolation
- IDW power, maximum neighbors and search radius

A search radius of `0` fills the complete bounding rectangle so the result can pass
directly into FFT filters. This extrapolates across unsupported gaps and survey edges;
set a finite radius when a conservative NoData mask is more important than immediate
FFT compatibility. The resulting projected GeoTIFF can be used by RTP, RTE,
derivatives and the Filter Stack.

## Line QC, leveling and microleveling

**Crossover QC and tie-line leveling** works directly on an open QGIS point
layer. Select the observed channel, line identifier, line type and optional
fiducial/order field. It builds traverse and tie trajectories, interpolates both
measurements at every crossing, rejects robust MAD outliers and solves a
zero-mean least-squares constant for each connected line. It outputs leveled
points with raw values preserved, a crossover residual layer, a corrections
table and RMS before/after in the Processing log.

Apply instrument lag, diurnal, heading and datum corrections before tie-line
leveling when those raw measurements exist. Published grids should not be
automatically re-leveled as though they were raw line data.

**Directional microleveling** is the final, auditable grid step. It separates
short across-line wavelengths that remain long along the traverse direction and
writes both the corrected grid and the estimated corrugation grid. Inspect the
removed component before accepting the result.

## FFT spectral filters

- Butterworth low-pass, high-pass, band-pass and notch
- Ideal band-pass and band-reject (with an explicit ringing warning)
- Cosine roll-off low-pass and high-pass
- Directional cosine pass and reject with configurable strike azimuth and degree
- Stabilized downward continuation with Butterworth taper and maximum-gain cap
- Horizontal integration in easting and northing, and vertical integration

Filter wavelengths, continuation distances and pixel spacing are interpreted in
the raster CRS units. Downward continuation is inherently unstable; its tool
therefore requires stabilization parameters and documents the source-crossing
limitation. The algorithm formerly labelled `45HG` retains its Processing ID for
saved-model compatibility, but now accepts any azimuth clockwise from North.

## Filter Stack panel

When the plugin opens, the compact **TerraWorkbench — Filter Stack** panel is docked on
the right side of QGIS (maximum width 380 px). Selecting a step opens a non-modal
parameter/spectrum/IGRF inspector immediately to its left so the map remains visible.
Choose a raster and band, add any number of filters, edit parameters, and reorder,
duplicate or remove steps. **Run stack**
feeds every output into the following filter and adds the final raster to the map.

Stacks can be saved as reusable JSON recipes. Outputs may remain temporary, or a
folder can be selected to save the final GeoTIFF and, optionally, every
intermediate GeoTIFF. The panel can be shown or hidden from the Raster menu or
the TerraWorkbench toolbar button.

## GRAV exploration filters

- DX and DY first horizontal derivatives
- DZ first and DZ2 second vertical derivatives
- UC500m upward continuation
- Gaussian regional field
- Residual field from upward-continuation subtraction
- THDR total horizontal derivative
- Tilt angle
- TGA total gradient amplitude

## 3D gravity and magnetic inversion

The provider includes three optional open-source SimPEG workflows:

- Bounded 3D gravity inversion for density contrast
- Bounded 3D magnetic inversion for scalar susceptibility
- Cartesian magnetic vector inversion (MVI), exported as X/Y/Z components and
  magnetization amplitude

They accept projected observation points, optional uncertainties, receiver
elevation and optional ground/topographic elevation. They can build a uniform
TensorMesh or adaptive TreeMesh refined around observations and topography, use
Choclo integral kernels, and write VTK, NPZ, JSON QC and
observed/predicted/residual CSV. Disk-backed sensitivities are enabled by
default, the active-cell limit prevents accidental oversized jobs, and
cancellation is checked between inversion iterations.

**Joint 3D gravity–magnetics inversion** accepts separate gravity and magnetic
point layers in one projected CRS. It recovers density contrast and scalar
susceptibility simultaneously, with an adjustable cross-gradient term that
encourages shared structural boundaries without imposing a fixed property
ratio. It exports both models, separate residual tables and normalized-RMS QC.
Run several coupling weights: structural agreement is a hypothesis to test, not
proof that every gravity and magnetic source is the same body.

These are non-unique inversions, not image filters. Cell size, depth,
uncertainties, bounds, topography and inducing-field direction must be tested.

## Requirements

- QGIS 3.28 or newer
- Harmonica 0.7
- Dependencies, including `ppigrf>=2.1`, installed in the Python environment used by QGIS
- Inversion stack: SimPEG 0.25,
  discretize 0.12 and Choclo 0.3

TerraWorkbench declares QPIP as a QGIS plugin dependency. During installation, QGIS installs QPIP and QPIP reads requirements.txt, checks the active profile and offers to install any missing Python packages. The user must approve that dependency installation.

The scientific packages are installed in the QGIS user profile and are not bundled inside the TerraWorkbench archive. This avoids replacing the GDAL, NumPy and SciPy versions supplied by QGIS and allows separate dependency sets in different QGIS profiles.

QPIP reads the canonical `requirements.txt`, which declares both the 2D and 3D
stacks so a fresh installation is fully functional after the user approves the
dependency prompt. `requirements-inversion.txt` is retained as a documented
subset for manual or isolated inversion environments. TerraWorkbench still
loads its inversion imports lazily, so failure of the optional runtime does not
prevent import, filters, leveling or gridding from loading.

## Installation for development

Copy the complete TerraWorkbench folder into the active QGIS profile under python/plugins, then enable TerraWorkbench in the Plugin Manager. Its algorithms appear in the Processing Toolbox and its Filter Stack opens at the right side of QGIS.

On Windows, `install_update_open_qgis.bat` discovers a local QGIS installation, copies or updates the plugin in the last active profile, installs development dependencies in the plugin-local `_vendor` directory, enables the plugin and opens QGIS. Set `QGIS_ROOT` before running it only when automatic discovery cannot select the desired installation. Passing `--check` performs a read-only environment check; `--no-launch` installs or updates without opening QGIS.

`build_dist.bat` asks for the release version, validates the source and metadata, and creates a clean QGIS-installable ZIP in `dist`. The package is built from an explicit allowlist so Git data, tests, caches, scripts and previous archives cannot leak into a release.

## Raster requirements

FFT tools require an evenly spaced north-up raster in a projected CRS. Input grids must not contain NoData or non-finite cells. Bouguer correction accepts NoData and preserves it in the output.

## License

TerraWorkbench is released under GPL-3.0-or-later. Harmonica is maintained separately by the Fatiando a Terra project under its own license. Runtime license information is recorded in THIRD_PARTY_LICENSES.md.

# Potential-Field Geophysics — Technical Reference

TerraWorkbench unifies magnetic, gravity, spectral, survey-preparation and 3D inversion workflows inside QGIS. Every operation declares its numerical domain, exposes its physical or numerical parameters, and produces ordinary QGIS-compatible outputs.

This reference is an interpretation aid, not a substitute for survey QA/QC, geological control, uncertainty analysis or sensitivity testing.

## 1. Magnetic enhancements and derivatives

### DX and DY — horizontal derivatives

**Formula:** DX = ∂T/∂x; DY = ∂T/∂y.

They emphasize lateral field changes associated with contacts, faults, dykes and intrusive boundaries. The result depends on feature orientation. Combine both components through THDR and inspect noise amplification.

TerraWorkbench offers spatial finite-difference and explicit FFT variants. Spatial derivatives use neighbouring cells; FFT derivatives multiply the spectrum by the corresponding wavenumber operator.

### DZ and DZ2 — vertical derivatives

**Formula:** DZ = ∂T/∂z; DZ2 = ∂²T/∂z².

Vertical derivatives enhance short wavelengths and shallow sources but strongly amplify high-frequency noise and edge effects. DZ2 should be interpreted together with geology, the analytic signal and lower-order products.

### Upward continuation

**Formula:** T̂(h) = T̂(0) exp(−kh).

The continuation distance is an explicit parameter in raster CRS units. Larger distances suppress progressively shorter wavelengths. No distance is encoded in the algorithm name or Processing ID.

### Residual enhancement

**Formula:** Tres = T − TUC(h).

Subtracting an upward-continued regional field emphasizes shallower components. The selected height controls the regional/residual separation and must be reported.

### THDR, Tilt, analytic signal, TDX and Theta

- **THDR:** sqrt(DX² + DY²), useful for lateral boundaries.
- **Tilt:** atan2(DZ, THDR), normalizes amplitudes into an angle.
- **Analytic signal amplitude:** sqrt(DX² + DY² + DZ²), less sensitive to magnetization direction than the original field.
- **TDX:** atan2(THDR, abs(DZ)), a boundary-focused horizontal tilt measure.
- **Theta map:** a normalized derivative product for source-edge interpretation.

These are interpretation attributes, not unique depth or lithology estimators.

### Directional horizontal gradient

**Formula:** GH(α) = DX sin(α) + DY cos(α), with azimuth α clockwise from geographic North.

Azimuth is a user parameter. No angle is encoded in the algorithm name or Processing ID. Compare several azimuths when structural orientation is uncertain.

## 2. Magnetic field-direction transforms

### IGRF-14

Automatic mode evaluates IGRF-14 at the raster centre using survey date and ellipsoidal altitude. Manual mode accepts inclination and declination directly. Verify metadata, sign conventions and the field epoch.

### Reduction to the pole (RTP)

RTP transforms the inducing and magnetization directions toward a vertical field so anomalies are more nearly centred over their sources. It is ill-conditioned at low magnetic latitude and with strong remanence; TerraWorkbench exposes stabilization and optional remanent angles.

### Reduction to the equator (RTE)

RTE is an alternative low-latitude transform. It may produce elongated responses and is not automatically superior to stabilized RTP. Compare both against geology and source orientation.

### General field-direction transform

This operator transforms a source field direction into a configurable target inclination and declination. It uses a 2D FFT transfer function and returns a spatial GeoTIFF.

## 3. Gravity enhancement

Gravity DX, DY, DZ, DZ2, upward continuation, regional/residual separation, THDR, Tilt and total-gradient amplitude follow the same derivative and spectral principles as their magnetic counterparts. Gravity responses reflect density contrast rather than magnetization. Regional/residual separation is scale dependent and is not a unique depth separation.

## 4. Gravity corrections and anomalies

### GRS80 normal gravity and gravity disturbance

Normal gravity is calculated from pixel latitude on the GRS80 ellipsoid using Somigliana's formula. Gravity disturbance subtracts this reference field from observed gravity. Meter drift, Earth tides and calibration must already be resolved.

### Free-air correction and anomaly

**Linear correction:** FAC = vertical gradient × geometric elevation.

The vertical gradient is configurable. Elevation must use documented vertical referencing and units.

### Bouguer plate, Bullard B and simple Bouguer anomaly

The infinite-plate approximation uses reduction density and elevation. Bullard B accounts for Earth curvature through a spherical-cap approximation. Density assumptions materially affect amplitudes and should be tested.

### Terrain correction and complete Bouguer anomaly

Terrain correction uses rectangular prisms from a projected DEM. The DEM must align with the gravity grid, be filled and extend far enough beyond the interpretation area. Runtime grows rapidly with cell count, so TerraWorkbench enforces a safety limit.

The complete land Bouguer workflow combines observed gravity, GRS80 normal gravity, free-air, Bouguer plate, terrain and Bullard-B terms with explicit sign conventions.

### Airy Moho and isostatic residual

The Airy model converts topographic load into crustal-root thickness using crust and mantle densities. The residual subtracts the forward-modelled root response from the complete Bouguer anomaly. Test reference depth, density, model extent and resolution.

## 5. FFT spectral filters

FFT tools transform a complete, regularly spaced projected raster into wavenumber space, apply a transfer function and inverse-transform the result.

TerraWorkbench distinguishes:

- **SPATIAL / FINITE DIFFERENCE:** cell-neighbour operations.
- **FFT / HARMONICA:** spectral operators supplied by Harmonica.
- **FFT / MAGMAP-LIKE:** TerraWorkbench's conditioned spectral engine.
- **MIXED GRID / FFT:** attributes built from components calculated in more than one domain.
- **PHYSICAL CORRECTION / GRID:** physical reductions evaluated on raster cells.

### Spectral conditioning

The MAGMAP-like engine can remove a mean or plane, reflect-pad the grid, taper the padded margin, combine compatible transfer operators in one forward FFT, crop the original footprint and optionally restore the trend. This reduces, but does not eliminate, edge artefacts.

### Available transfer functions

- Butterworth low-pass, high-pass, band-pass and notch.
- Ideal band-pass and band-reject, with an explicit ringing warning.
- Cosine roll-off low-pass and high-pass.
- Directional cosine pass and reject with configurable strike.
- Stabilized downward continuation with gain control.
- Horizontal and vertical integration.
- Explicit easting, northing and upward FFT derivatives.

Wavelengths and continuation distances use raster CRS units. Use a projected metric CRS when parameters are intended in metres.

## 6. Survey preparation and import

TerraWorkbench imports GDAL-supported grids, CSV/ASCII data and Esri FileGDB content. On Windows, the official BSD GX Developer runtime reads single-file Geosoft GeoDatabase data without Oasis montaj and exports it to open CSV/GeoTIFF/QGIS layers. An installed Oasis runtime is only a fallback.

Point gridding supports projected output CRS selection, cell size, interpolation method, neighbour count and search radius. A zero search radius fills the complete rectangle for FFT processing but extrapolates into unsupported areas.

Crossover QC and tie-line leveling identify line intersections, reject robust outliers and solve line corrections. Directional microleveling addresses residual line corrugation; it does not replace lag, diurnal, heading or tie-line corrections.

## 7. Three-dimensional inversion

TerraWorkbench provides SimPEG-based gravity density, magnetic susceptibility, magnetic vector (MVI) and joint gravity–magnetic inversion. TensorMesh and adaptive TreeMesh workflows expose cell size, depth, padding, topography, uncertainties, bounds, iteration limits and safety limits.

Joint inversion uses cross-gradient coupling to encourage structural similarity without forcing a fixed density–susceptibility relationship. Run coupling-weight and mesh sensitivity studies. Inversion results are non-unique and must be evaluated against geology, acquisition geometry and residuals.

## 8. Minimum interpretation checklist

1. Confirm CRS, horizontal/vertical units, grid spacing and NoData coverage.
2. Preserve raw and corrected data with provenance.
3. Inspect line-leveling and crossover residuals before gridding.
4. Test padding, taper, cutoff wavelength and continuation distance.
5. Compare spatial and FFT derivatives when edge behaviour matters.
6. Document field direction, survey epoch, density and magnetization assumptions.
7. Review residual maps and sensitivity runs for every inversion.
8. Do not interpret a filtered maximum as unique evidence of depth, lithology or mineralization.

## 9. Trusted open-source reading

The **Trusted repositories** tab links directly to Harmonica, Verde, Boule, Choclo, GMT, xrft, SimPEG, discretize, ppigrf, QGIS and other canonical upstream projects. Consult their documentation and licenses before reproducing methods or code.

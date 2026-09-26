# Regional Airy residuals

Two boundary conditions are available. `airy_isostatic_anomaly` retains the
finite-prism model. `airy_isostatic_anomaly_fft` adds a Parker-series **periodic**
model. Changing between them changes the assumed mass outside the rectangle;
the FFT solver is not a faster evaluation of the same finite model.

## Periodic FFT model

Supply a complete `REGIONAL` basement raster, optionally aligned water thickness,
and a Bouguer observation raster inside its cell-centre bounds, in the same metric
CRS and vertical datum. `HEIGHT` is a constant observation plane (default sea
level), not an inferred airborne or terrain surface. The numerical function
requires `boundary="periodic"` explicitly. Regional NoData is rejected; Bouguer
NoData is preserved. Sampling is bilinear with no extrapolation.

The rectangle repeats periodically with **its original mean load**. The zero
wavenumber gravity is retained; there is no fitted bias, demeaning, padding or
tapering. Domain size and extent are physical assumptions and must be recorded
and tested, independently of cell size. An improved match to a survey cannot
identify an unpublished processing recipe.

For root thickness `t`, contrast `delta_rho`, reference depth `D`, observation
height `z` and angular wavenumber `k`, the downward root-gravity transform is:

```text
-2*pi*G*delta_rho*exp(-k*(D+z)) * sum_n [(-k)^(n-1) * FFT(t^n) / n!]
```

The implementation requires `max(abs(t)) < D+z`, preserves the analytic slab
term at k=0, and requires three consecutive small series terms. It raises an
error if convergence is not reached. Numerical term tolerance is not physical
model accuracy. Default FFT parameters are 30 km, 2670/3270 kg/m³ and sea level;
these are explicit choices, not universal or inferred survey parameters.

Tests include the uniform slab, the small-amplitude sinusoidal limit, upward
attenuation, water-equivalent loading, periodic translation and an independent
sum of repeated Harmonica prisms with an analytic background. The adapter is
also tested in real QGIS. `scripts/benchmark_isostasy_fft.py` records declared
sensitivity cases and generates experimental GeoTIFFs using local input paths.

The spectral formula follows [Parker (1973)](https://topex.ucsd.edu/geodynamics/parker.pdf).
The [USGS AIRYROOT report](https://pubs.usgs.gov/of/1983/0883/report.pdf) describes
a different combination of near-root and far-zone corrections; its global
far-zone treatment must not be confused with periodic continuation.

## Finite-prism model

The `airy_isostatic_anomaly` Processing ID and existing parameter names are
preserved. The adapter now calls `isostasy.py`, a numerical module without QGIS
imports. It builds finite Cartesian root and antiroot prisms and evaluates their
downward gravity with Harmonica. Residual = Bouguer minus root gravity.

## Inputs and model boundaries

- `INPUT`: Bouguer raster; `ELEVATION`: observation heights on exactly that grid.
  Their combined NoData mask is preserved.
- `REGIONAL`: optional independent basement/topobathymetry raster, band 1.
  It may have a different extent and resolution, but must use the same projected
  metric CRS. Without it, elevation supplies the load as in the legacy algorithm.
- `WATER`: optional water **thickness** raster, band 1, aligned with the regional
  model. Default is zero; oceans and lakes are never inferred automatically.
  Lake basement is lake-surface elevation minus water thickness, in the same datum.
- All heights and the reference Moho share one vertical datum. No datum or CRS
  transformation is implicit. The observation surface need not be the basement.
- The regional load must be complete. Observation gaps are not missing masses;
  missing regional cells cannot be silently dropped or filled. Supply a regional
  source covering the desired model domain.

Root thickness is `(rho_crust * basement + rho_water * water_thickness) /
(rho_mantle - rho_crust)`. A positive root replaces mantle with lighter crust;
its density contrast is negative. A negative root reverses this contrast.
The old defaults of 25 km reference depth, 2670 kg/m³ crust and 3070 kg/m³ mantle
remain for compatibility; they are not universal survey parameters.

## Cost and convergence

`BLOCK_SIZE=1` retains original model cells. Larger integer factors average load
over rectangular blocks, including partial boundary blocks. This conserves total
compensating mass, but changes root geometry. Compare successively finer model
resolutions; do not choose a factor solely to meet the computation limit.

`MAX_CELLS` limits model cells **after** aggregation, not the observation raster.
`MAX_INTERACTIONS` limits valid station/prism pairs (default 200 million).
The direct calculation remains O(stations × prisms). Chunking supports progress,
cancellation and bounded output buffers; it is not a fast multipole solver.
Increasing either limit is explicit and should follow a small timing test.

Model extent matters at Moho depths even when near-surface terrain effects appear
converged. Test increasing regional margins independently of cell resolution.
There is no spherical correction or global far-zone compensation in this model.
An empirical constant subtracted from a benchmark residual is a fit, not a
reproduction of a survey's physical correction.

The output GeoTIFF carries `TW_ISOSTASY` metadata with model parameters, sources,
aggregation, prism count, sign convention and the absence of a far-zone term.

## Verification

`tests/test_isostasy.py` checks mass balance, water loading against Harmonica's
Airy implementation, the infinite-slab limit, signs, missing observations,
cancellation and work limits. `tests/qgis_isostasy_smoke.py` checks the real QGIS
adapter with separate model and observation grids, masks, water and aggregation,
and verifies parity with the previous prism-layer computation for legacy inputs.

`scripts/benchmark_isostasy.py` accepts explicit local reference-grid and
SRTM30_PLUS tile paths. It records hashes, unadjusted errors, sensitivity cases
and limitations. `--full-grid` also writes experimental correction, residual and
difference GeoTIFFs. Survey data and benchmark outputs belong outside distributable
sources (for example the ignored `sample_data/local_private/` directory).

References: [Harmonica Airy load convention](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.isostatic_moho_airy.html)
and [SRTM30_PLUS version and tile documentation](https://topex.ucsd.edu/pub/srtm30_plus/README.V11.txt).

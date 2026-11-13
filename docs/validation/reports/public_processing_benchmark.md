# Public 2D processing campaign

Campaign dated 28 October 2026. This is executable numerical evidence with
declared scope, not completion of all geophysics or proprietary equivalence.
The Core runs without QGIS. No private surveys are used.

## Inputs and reproduction

The [source manifest](../../../scripts/public_processing_sources.json) records six
permitted datasets in the public export, with exact URL, size, SHA-256,
attribution, license notes and pin basis. Publisher MD5 values were verified
before recording SHA-256. A separate development-only case has unconfirmed
rights and is disabled by default; it is absent from the public catalogue.
No original observations are committed or bundled.

| Dataset | Source and purpose |
| --- | --- |
| [Bushveld gravity](https://doi.org/10.5281/zenodo.6511942) | NOAA NCEI/Fatiando; 3,877 published disturbances |
| [Southern Africa gravity](https://doi.org/10.5281/zenodo.5882430) | NOAA NCEI/Fatiando; 14,359 land reductions |
| [Lightning Creek magnetic grid](https://doi.org/10.5281/zenodo.7079711) | Queensland/Geoscience Australia P1029/Fatiando; 128,020 cells |
| [Britain magnetic data](https://doi.org/10.5281/zenodo.5879260) | BGS/Fatiando; 541,508 digitized samples, 4,320 contiguous segments |
| [Southern Africa topography](https://doi.org/10.5281/zenodo.6481379) | NOAA ETOPO1/Fatiando; projected coastal DEM |
| [Mobile gamma spectra v1.1.0](https://doi.org/10.5281/zenodo.20032395) | Breitenmoser, Stabilini, Kasprzak and Mayer; measured spectra and simulated templates |

Processed Fatiando products are declared CC BY 4.0 by their publisher records;
retain the original data-source acknowledgements as well. Britain contains
British Geological Survey materials, UKRI 2021, under the Open Government Licence.
The [spectra record](https://doi.org/10.5281/zenodo.20032395) currently declares
CC BY 4.0 for v1.1.0. Cite that dataset and the
[associated paper in Nature Communications](https://doi.org/10.1038/s41467-026-78464-2)
(preprint arXiv:2512.18769); the dataset author confirmed this citation pair.

Use an existing Python environment and explicitly chosen cache/output folders:

~~~text
python -m pip install '.[prisms,storage,tables,coordinates]' -r requirements/benchmark.txt
python scripts/benchmark_public_processing.py --cache CACHE_FOLDER --output NEW_OUTPUT_FOLDER
~~~

The output must be new. Add --offline to forbid downloads; repeated --case
selects only needed inputs. Cache bytes are verified every time; mismatched or
interrupted downloads remain for diagnosis and are rejected. Archive members
are read by exact name without path extraction. Reports include dependency
versions, dataset/module/runner hashes, Git revision/dirty state, metrics,
timing and scope. Failed cases remain failed while independent cases continue.

Each manual campaign retains report.json and a terminal report.public.json
with workstation/cache paths removed, including failures. The public
copy preserves source hashes, dataset provenance and numerical results.
Ordinary CI runs offline regressions without downloading these datasets.

## Results and contracts

| Check | Observed result | Scope |
| --- | --- | --- |
| Bushveld published disturbance | Max error 0.000000034 mGal | Published geometric heights, external Boule WGS84 gravity, Core subtraction |
| Southern Africa GRS80/slab | Max error 0.0000072 mGal | Explicit linear free-air and slab recipe; not full terrain correction |
| Lightning Creek FFT/RTP | Max field error approximately 0.000000000013 nT | Independent Harmonica transfers; common periodic boundary, declared test directions |
| Withheld 361-cell block | RMS linear 2.537; global TPS 1.866; local TPS 1.811; multilevel curvature 1.881; variational curvature 1.880 nT | Already gridded source, no raw-survey truth or universal acceptance threshold |
| Britain channel mean | Exact floating-point reference agreement | Sample-domain only, split at every published contiguous line ID |
| Coastal ETOPO1 attraction | Exact-tree max Geoana difference approximately 0.00000000040 mGal | Independent engine, 1,023 cells, 37 stations |
| Adaptive tree | Errors inside bounds at 0, 0.00001 and 0.001 mGal | Bounds exclude data, density, datum, outer terrain and curvature uncertainty |
| Finite Airy roots | Max Geoana difference approximately 0.00000000047 mGal | Periodic model checked separately through mean-load conservation |
| Gamma spectra | Rebinning of 29 spectra from 14 files; windows and NNLS/BVLS comparisons on two high-count hover spectra | Diagnostic optimizer checks, not certified activities |

Stored Britain values and pinned row counts are compared against separate
pandas/NumPy parsing. Southern Africa has unspecified horizontal datum: the
gravity recipe applies no reprojection. ETOPO1 retains its MSL heights during
horizontal reprojection; no vertical transformation is invented.

Interpolation uses Lightning Creek index slices northing 40:137 and easting
40:141. Training takes every fifth node, excluding the block 1,700 to 2,700 m
from the crop origin in each axis. There are 404 training points and 361 held-out
cells. The terrain case places numerical evaluation stations over a projected
33 by 31 coastal DEM at 2,500 m spacing near 18.4 E, 33.9 S, plus one far-field
station; these are not measured gravity stations.

Spectral fits use explicit square-root-count Gaussian weights with a one-count
floor, rather than the paper's Bayesian Poisson method. Reduced chi-square
exceeds one for the simplified fits and remains reported: optimizer agreement
does not establish an adequate physical source model.

NASVD checks use the three single-pass files with six spectra each on their
original shared energy axes and measured live times. Full-rank reconstruction
and rank-two weighted residual optimality are checked; negative reconstructions
are counted rather than clipped. Rank two is an explicit numerical test choice,
not an inferred physical component count or validated denoising optimum.

## Failures traced

- Normalized RGB indexed a validity mask as a raster and failed on point
  channels/scalars. Broadcasting now supports channels and grids.
- Sectioned XYZ detection retained the first-channel slash and consumed later
  Line markers as data. It now suggests marker comments and star nulls when an
  explicit repeated line channel exists, and retains the ITM pair over auxiliary
  longitude/latitude roles. It assigns neither CRS nor absent line IDs.
- The initial benchmark reference truncated means because SciPy received integer
  input. The reference now uses float. The Core filter was already correct.
- Independent NumPy parsing also needed explicit star-null handling for missing
  auxiliary Tellus sensor values; the Core importer already preserved those
  nulls. This reference-parser correction did not change survey values.
- At the strict numerical tolerance of 0.00001 nT, 400 multilevel iterations
  did not converge. This remains a rejected trial. With a 6,400-iteration
  budget and the same tolerance, the three levels reached their declared
  99 percent stopping criterion in 611, 1,198 and 5,350 iterations. Both final
  solvers must report convergence for this benchmark to pass; no default Core
  setting was changed to hide the rejected trial.

Regressions reproduce the original failures. Independent auxiliary checks use
Geoana point-mass gradients for Euler and dense segmented Gaussian posteriors
for heterogeneous correlated radon errors and multiple smoothing strengths.

## Remaining boundaries

Concentration lines and Rn spectral templates do not supply calibrated paired
upward/downward airborne series with independent atmospheric truth. The reviewed
sources do not close full atmospheric-radon reconstruction. Unknown calibration
coefficients are never inferred from unknown geology to manufacture validation.

This campaign does not certify every experimental/electrical/EM/seismic method
or resolve geological nonuniqueness. [Public inversion validation](public_inversion_benchmark.md)
has separate convergence/integration contracts; shared SimPEG agreement is not
independent validation of SimPEG itself.

## Archived evidence from 28 October 2026

The [processing JSON summary](../records/public/public_processing_20261028.json)
retains the six permitted cases from the recorded historical campaign. Original
logs and the complete seven-case record remain in the development archive;
the public summary is not a new run or a new aggregate pass certificate.

Local Windows verification passed 685 tests with 40 dependency warnings, the
independently installed Core wheel, QGIS ZIP validation and four QGIS smoke
entry points. The latter registered 95 algorithms and exercised text-import and
workspace flows in EN/ES/PT, and gridding/smoothing/AGC integration. The sectioned
XYZ wizard was tested in all three languages. These counts describe this run,
not a future release certificate.

The [inversion JSON record](../records/public_inversion_20261028.json) retains
the six-case public recipe replay and the separate converged Gauss-Newton
experiment. The [evidence index](../records/README.md) distinguishes their scope.

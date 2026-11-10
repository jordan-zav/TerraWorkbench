# Calibrated radiometry, profile gravity and geostatistics

Implemented 28 October 2026. These additions run in the independent Core with
NumPy and SciPy. Eight registered operations also appear in the advanced Core
catalogue and typed forms in English, Spanish and Portuguese. They do not add
eight separate QGIS Processing algorithms. PyKrige is a benchmark dependency
only; production kriging uses the Core implementation.

## Operations and physical contracts

| Operation | Contract and output |
| --- | --- |
| gravity.polygon_forward | Station x,z and simple polygon vertices in metres; upward z; density contrast in kg/m3; downward gravity in mGal. Infinite strike extent. |
| gravity.polygon_density_fit | Fixed polygons, observed mGal and positive independent reading errors. Linear density contrasts and optional constant offset, full parameter covariance, residuals and conditioning. |
| radiometry.upward_window_radon | Calibrated upward U, downward U and downward Th rates; six explicit coefficients and full rate covariance. Signed radon contribution, terrestrial U/Th and propagated covariance. |
| radiometry.window_radon | Four calibrated windows and a four-component response matrix. Signed component separation and radon-subtracted windows with full covariance. |
| radiometry.full_spectrum_radon | Spectra, response templates, independent channel errors and component names. Signed weighted component separation, radon-subtracted spectra, marginal variances, chi squared and conditioning. |
| radiometry.background_correction | Count rates minus explicit aircraft, cosmic and radon contributions. Each background may be scalar or time varying. NaN remains missing; infinity is rejected. |
| potential.empirical_variogram | Projected planar coordinates, values and explicit lag edges. Classical empirical semivariance, pair counts and mean separations; optional axial azimuth. |
| potential.ordinary_kriging | Projected coordinates, queries and explicit spherical/exponential/Gaussian variogram. Predictions, conditional model variances, neighbour support and local conditioning. |

Use terraworkbench_core.operations.run_operation with an identifier and a
parameter dictionary. Direct Python functions live in gravity_profiles,
radon_corrections, radiometry and geostatistics. The existing Core job/workflow
API preserves source provenance and array results. JSON geometry, calibration
matrices and component names remain explicit inputs in the forms.

## Gravity geometry and datum uncertainty

Polygon gravity uses a logarithmic edge integral, checked against independent
area quadrature and the infinite horizontal cylinder solution. Either vertex
order and concave simple polygons are accepted. Self intersection, degenerate
edges and nonadjacent touching are rejected. Horizontal edges and vertex limits
use analytic limits. This is infinite-strike 2D modelling: finite-end 2.5D
corrections and inversion of polygon vertices are not provided by these methods.

The density fit keeps geometry fixed and uses noise-whitened, column-scaled SVD.
Density contrasts may be negative. Formal covariance is conditional on known
independent absolute reading errors and geometry; it is not rescaled to force
unit chi squared and does not establish geological uniqueness.

The existing gravity.network_adjustment operation now optionally accepts
anchor_std_mgal, a dictionary of positive independent standard deviations for
every reference station in anchors_mgal. References then enter as uncertain
observations instead of fixed constants. The full station/drift covariance
retains the shared datum error. Omitting the new parameter preserves exact
references. Correlated reference errors are not modelled. Separate reading and
reference chi squared and residuals are returned.

## Radon calibration and uncertainty

The upward-window model follows IAEA TECDOC-1363 equation 5.7. With upward rate u,
downward U and Th rates, and coefficients a1,a2,au,at,bu,bt:

    R = (u - a1 U - a2 Th + a2 bt - bu) / (au - a1 - a2 at)
    U_ground = U - R
    Th_ground = Th - at R - bt

Rate covariance order is upward U, downward U, downward Th. Optional six by six
coefficient covariance uses the stated coefficient order and first-order
propagation. A nearly unidentifiable denominator fails. Shared calibration can
correlate records; only per-record marginal covariance is materialized.
Rates must already have the background, stripping and other preprocessing
required by their calibration. No universal coefficients or atmospheric
concentration in Bq/m3 are inferred from final concentration grids.

The four-window method solves a calibrated response system. A low-energy
Bi/K/U/Th basis requires the appropriate continuum correction and calibration;
an arbitrary energy window is not an implementation of IAEA equation 5.5.
The full-spectrum method supports up to eight named templates, including
interfering Cs/Ba responses when available. Negative coefficients are returned
and flagged instead of clipped. The specified channel errors must be fixed and
independent; correlated rebinned noise requires a different likelihood.

Radon estimated from a spectrum/window is correlated with those measurements.
The corrected covariance therefore includes the subtraction cross terms. It
does not simply add independent radon variance. Template, energy calibration
and geometry errors are excluded from the four-window/full-spectrum covariance.
Near-zero negative spectral variances caused only by roundoff are floored;
unstable negative results fail. Chi squared diagnoses model mismatch, not a
certificate of field calibration or radon removal quality.

## Kriging and variogram conventions

For separation h and range r, the exponential model is
nugget + partial_sill (1 - exp(-3 h/r)); the Gaussian model substitutes
3 (h/r)^2. Spherical support reaches the sill at r. The value at exactly zero
separation is zero. Partial sill excludes nugget. Exact observations, including
nugget-scale process variation, are retained with zero conditional variance;
this is not measurement-error smoothing. Model variance excludes variogram
parameter and geological uncertainty.

Local kriging uses 3 to 128 neighbours. A positive search radius returns NaN
where fewer than three neighbours support a query; exact observed positions
remain available. Zero radius permits extrapolation and must be selected
deliberately. Duplicate coordinates fail rather than being silently averaged.
Local systems are normalized for unit-stable condition checks and reused for
shared neighbourhoods. Query/element/system budgets prevent unbounded work.

Empirical variograms use half the squared value difference. Lag bins include
their left edge and the last bin includes its right edge. Empty bins are NaN.
Azimuth is axial, clockwise from north. Above the pair budget, sampling is
uniform over distinct-index ordered pairs with replacement, with a recorded
seed; counts are sampled counts, not independent-pair uncertainty estimates.
Coordinates must already be projected in metres. No geographic degree
distances, automatic variogram fitting or anisotropic metric is implied.

## Reproducible validation

Tests in tests/test_2d_expansion.py cover independent polygon quadrature,
analytic cylinders, translation/orientation, density recovery, rank and budget
failures, covariance against direct matrix systems/finite differences,
uncertain reference propagation, kriging against covariance-form systems and
variogram pair/direction conventions. These checks use synthetic public-domain
geometry and no private surveys.

scripts/benchmark_2d_extensions.py reuses the pinned source manifest of the
[public processing campaign](public_processing_benchmark.md). Its output is a
new directory containing parameters, SHA256, versions, diagnostics and limits:

- Lightning Creek public magnetic grid: 404 training and 361 held-out points,
  three explicit stress-test variograms, compared with PyKrige moving-window
  predictions and variances. The Gaussian range convention is converted before
  comparison. Held-out error is reported; parameters are not claimed optimal.
- PSI measured gamma spectra: five-template K/U/Th/Rn plus Cs or Ba separation,
  compared with independent SciPy least squares. Template units, signed
  coefficients, residual chi squared and propagated variance remain visible.
  Laboratory templates do not validate an airborne survey calibration.
- Infinite-cylinder gravity and synthetic density/offset recovery. This is
  analytic validation rather than an invented measured-profile truth.

The measured Cs-spectrum trial gives a negative signed radon coefficient and
reduced chi squared about 7.36; the Ba-spectrum trial gives about 2.13. These
are explicit calibration/model mismatch diagnostics under the declared noise
assumption, even though independent linear solvers agree. Neither trial
establishes physically valid atmospheric reconstruction for a field survey.

The manual public-processing CI workflow runs this campaign after the seven
existing public processing cases and retains both artifacts. Historical
[archived evidence](../records/README.md) remains tied to its original source
revision. Full field validation of atmospheric reconstruction still requires
instrument-specific calibration, spectra, auxiliary channels and independent
control. These additions do not close every item in the geophysics backlog.

The [archived extension record](../records/2d_extensions_20261028.json) contains
the successful Linux run, its clean source revision and all three comparison
cases. Local checks additionally exercised all 114 advanced forms in EN/ES/PT,
the 95-algorithm QGIS provider, an isolated installed Core wheel and the plugin
ZIP. The corrected domain label passed the focused 76-test regression.

## Primary references

- [IAEA TECDOC-1363, section 5.5.6 and equations 5.6/5.7](https://www-pub.iaea.org/mtcd/publications/pdf/te_1363_web.pdf).
- [Talwani, Worzel and Landisman, 1959](https://doi.org/10.1029/JZ064i001p00049).
- [USGS profile anomalies and finite-end corrections](https://www.usgs.gov/publications/calculation-gravity-and-magnetic-anomalies-along-profiles-end-corrections-and-inverse).
- [PyKrige ordinary kriging contracts](https://geostat-framework.readthedocs.io/projects/pykrige/en/stable/generated/pykrige.ok.OrdinaryKriging.html).

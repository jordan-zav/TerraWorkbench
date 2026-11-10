# Voxel recovery: explicit priors and independent scoring

Subsequent evidence: the [MVI evidence map](../mvi_evidence_map.md) lists the
later MVI reports. This report and its archived results are unchanged.

Implemented 28 October 2026. A small anomaly residual does not demonstrate
recovered geology. The new campaign distinguishes execution, data prediction,
inner solver accuracy and recovery of the generating bodies. Historical reports
are preserved; their passed statuses retain their original data-fit scope.

## Why the previous model errors were large

Potential-field data constrain combinations of cell properties. Smoothness,
zero reference and sensitivity weights select one solution without establishing
unique depth, volume or contrast. In this campaign 81 observations constrain
384 scalar properties or 1,152 Cartesian MVI components. The unconstrained
linear systems therefore have nullities of at least 303 and 1,071, respectively.
Prediction at withheld stations tests interpolation/extrapolation, not uniqueness.
Independent Newton/dipole volume integration is checked against the inversion
forward operator before any fit, separating forward-physics errors from recovery.

## Explicit Core constraints

Import spatial_property_constraints from terraworkbench_core.spatial_constraints,
or call the registered inversion.spatial_constraints operation. Supply active
cell centers in projected ENU metres, scalar lower/upper properties and an
explicit background_value. Supply support_prisms_m as west/east/south/north/
bottom/top boxes, depth_limits_m with explicit surface_elevation_m, or both.
Box unions are intersected with the depth interval. Membership uses cell centers,
without clipping cell volumes. Upward cell z is subtracted from the supplied
surface to obtain depth; there is no inferred terrain or vertical datum.

Hard mode fixes properties outside support by returning equal lower and upper
bounds. Soft mode leaves the bounds in place and applies outside_weight greater
than one to spatial regularization. This is a user hypothesis, not confidence or
automatically recovered geology. An incorrect support can force a wrong answer.
Provide a reference and starting model compatible with any nonzero fixed cells.

Pass the returned lower, upper and cell_weights to run_potential_field_inversion.
Scalar limits remain supported. Bounds may be per active cell; MVI also accepts
cell-major (n,3) or component-major (3n,) bounds. Per-cell MVI bounds apply to
each Cartesian component and are not amplitude limits or direction cones.
Positive cell_weights multiply existing regularization weights, including
sensitivity weights. They apply to the native SimPEG regularization terms,
not to the observations. The solver reports free/fixed parameter counts and
the supplied spatial weight range. CLI input NPZ files can carry these arrays.
These additions cover individual gravity, susceptibility and MVI inversions;
the joint cross-gradient API retains its existing bounds contract.

## Recovery metrics

Import model_recovery_metrics from terraworkbench_core.recovery_metrics or use
inversion.recovery_metrics. Supply centers, positive cell volumes, recovered
properties and independent truth in the same units. Vectors use cell-major ENU
(n,3). Body scoring expects property contrasts relative to a stated background;
it does not subtract an unknown nonzero background or segment absolute density.
Six numerical criteria are mandatory; there are no automatic acceptance
thresholds. Truth is used for scoring, never transferred into a production prior.

Both supports use the declared fraction of the maximum true amplitude. Connected
components use an explicit center-distance radius, not general mesh face
topology. The matcher minimizes total centroid distance; a different component
count fails location. Metrics include volume-weighted support Dice, thresholded
volume error, each true body's mean amplitude error, scalar polarity or mean
vector direction, and volume-weighted whole-model relative L2 error. Contrast
and direction are evaluated inside true bodies; support and model criteria also
penalize displacement and leakage. Effective participation volume describes
diffuseness separately. Missing directions fail rather than receiving zero error.

Callers may instead supply explicit connectivity_edges from mesh topology,
omitting the radius. Only edges whose two cells belong to the evaluated support
connect a body. This permits adaptive meshes without arbitrary distance links.
The archived campaign below retains its original radius and scores unchanged.

Defaults cap assessment at 20,000 cells and 200,000 connectivity links; the
matcher supports at most 64 true components. More than 64 predicted components
fails recovery without allocating an unbounded assignment matrix. These metrics
are deterministic benchmark tests, not posterior uncertainties or a field-data
geological certificate.

## Frozen campaign

Run scripts/benchmark_voxel_recovery.py with --output pointing to a new directory.
It writes protocol.json and its SHA256 before generating data or fitting models,
then incrementally preserves report.json. --quick is an incomplete diagnostic
subset. --require-recovery exits nonzero unless the complete campaign validates
a nonoracle configuration for every physical property kind. Ordinary completion
only means the experiments executed; scientific_status reports their outcome.

| Control | Declared protocol |
| --- | --- |
| Design geometries | Shallow, deep and horizontally displaced cubes |
| Withheld morphologies | Thin body and two separated bodies |
| Physical properties | Density, susceptibility and differently directed MVI bodies |
| Observation/holdout geometry | 81 points at z=100 m; 64 offset points at z=120 m |
| Noise | Two fixed Gaussian scales, seeds derived from fixture/kind/scale |
| Strategies | Baseline L2, compact IRLS, soft partial support, hard partial support |
| Partial support | Same broad box for every morphology; no true-body masks |
| Conditional oracle | Exact geometry and uniform body properties fitted by GLS |
| Negative control | Deliberately misplaced hard support, one per kind |
| Total | 153 cases, including 30 conditional oracles and three negative controls |
| Data prediction gates | Training WRMS below 2; clean holdout RMS/noise below 3 |
| Recovery gates | Location at most 100 m, volume and contrast error at most 35%, Dice at least 0.6, model L2 at most 50%, MVI direction at most 15 degrees; scalar polarity correct |
| Support definition | Half of true peak amplitude; 101 m connectivity radius |

Acceptance thresholds and strategies are fixed before the campaign. No strategy
is selected into production defaults. A case needs data, numerical and recovery
checks to pass together. A method configuration must pass all ten cases of its
property kind, including withheld morphologies. Oracle passes cannot certify
free-voxel recovery. Three wrong-support controls must be rejected. The benchmark
uses authored public synthetic recipes; it includes no private survey data.
These test morphologies were inspected during development diagnostics; they are
not an untouched external blind validation dataset.

The CI campaign retains protocol and reports. A successful execution workflow
can retain recovery_failed cases and scientific_status recovery_not_validated;
green CI must not be described as geological recovery. Use --require-recovery
for a strict scientific acceptance gate. Source hashes, package versions and
the commit identify the executed implementation.

## Primary implementation references

- [SimPEG weighted least squares](https://docs.simpeg.xyz/v0.25.0/content/api/generated/simpeg.regularization.WeightedLeastSquares.html): spatial weights, regularization terms and reference models.
- [SimPEG projected Gauss-Newton CG](https://docs.simpeg.xyz/v0.25.0/content/api/generated/simpeg.optimization.ProjectedGNCG.html): bounded optimization.
- [Existing storage and unit contracts](inversion3d_extensions.md): MVI effective susceptibility, physical magnetization exports and matrix-free operation.

## Archived clean-source results

The [153-case record](../records/voxel_recovery_20261028.json) comes from [Linux CI](https://github.com/jordan-zav/TerraWorkbench/actions/runs/40807523516) at source 513db2b59e4725b26fd97226054707ea64482468. Of 120 nonoracle cases, 7 passed the combined data, numerical and recovery gates. The 30 exact-geometry conditional controls passed in 30 cases; all three wrong-support controls were rejected. The scientific status is recovery_not_validated. No production default was changed.

| Property | L2 passes | Compact passes | Soft support passes | Hard support passes | Median L2 / hard-support model error |
| --- | --- | --- | --- | --- | --- |
| gravity | 0/10 | 0/10 | 0/10 | 3/10 | 92.9% / 64.0% |
| susceptibility | 0/10 | 0/10 | 0/10 | 4/10 | 90.6% / 49.8% |
| mvi | 0/10 | 0/10 | 0/10 | 0/10 | 97.3% / 90.5% |

The restricted cubical successes do not extend to all geometries. These results demonstrate benefits and failures of explicit assumptions; they do not establish general free-voxel geological recovery. Oracle geometry was supplied from truth and is excluded from that claim.

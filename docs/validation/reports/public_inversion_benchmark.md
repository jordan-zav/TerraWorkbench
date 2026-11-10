# Public potential-field inversion benchmark

Campaign dated 27 October 2026. The external dataset is the public synthetic
[SimPEG 0.25.0 cross-gradient tutorial](https://docs.simpeg.xyz/v0.25.0/content/user-guide/tutorials/13-joint_inversion/plot_inv_3_cross_gradient_pf.html).
It is not a real survey and is not the locally authored cube experiment.

## Reproduction and provenance

The repository script scripts/benchmark_public_inversion.py retrieves a pinned
1,059,116-byte archive and the pinned tutorial source. Data and source hashes
must match before use. Archive paths are checked and only regular files are
extracted. Existing cached bytes must match; originals are never overwritten.
The downloaded Python source is retained as provenance and never executed.
Choose the cache and a new output directory explicitly:
<code>python scripts/benchmark_public_inversion.py --cache CACHE_FOLDER --output NEW_OUTPUT_FOLDER</code>.
Install the inversion and validation extras in an existing environment.
Historical full execution logs are retained in the project development archive.
Ordinary CI tests the API controls without downloading this external dataset.

Archive SHA256:
ace33b2a651b7326185a53cbc799179817430e72f0d50cfd952d9baed52cb8bb

Tutorial source SHA256:
f38d03d22afe8476523420dc48f3696192ce00f85b78757a269c358ee54842da

There are 289 gravity and 289 magnetic observations on identical locations,
50,000 TensorMesh cells and 47,860 active cells under supplied topography. The
two float32 sensitivity matrices total 110,652,320 bytes. The inducing field is
the tutorial's 50,000 nT, inclination 90 degrees, declination zero. Uncertainty
is one percent of each dataset's maximum absolute anomaly, as in the tutorial.

Core joint inversion now accepts the exact supplied mesh and active mask,
starting values and matrix precision/budget. The benchmark uses 0.000001 starts,
both property bounds -2 to 2, cross-gradient weight 2e12 and ten iterations.
These choices reproduce a tutorial; they are not general survey defaults or
physically justified bounds for every property model.

The controlled reference recreates the documented SimPEG objective and controls.
It disables unused BFGS initialization, fixes the beta seed to zero and omits
plotting and iteration-file output. These differences from the published script
are explicit; no exact reproduction of its historical displayed figures is
claimed. Core and the reference share SimPEG, so agreement checks integration
and numerical recipe compatibility, not independent validation of SimPEG itself.

## Observed Windows results

This table records the original preconditioner at commit 4ebc17a. Current Core
uses the corrected weighted joint diagonal described in the
[convergence report](inversion_convergence_resolution.md). The reproducible
script retains reference and reference_choclo as legacy tutorial cases and adds
reference_weighted, using Choclo and an independently constructed weighted
diagonal. Its same_engine_reference field identifies reference_weighted as the
current integration comparison; the old trajectories remain reported separately.
That comparison explicitly sets cross_gradient_hessian to simpeg, preserving
the tutorial-reproduction recipe. Current Core defaults to gauss_newton. Its
separate from-start convergence run reaches both inner and outer criteria in
58 iterations, as detailed in the linked convergence report. The public section
of scripts/validate_inversion_resolution.py reproduces that case and requires
convergence before the outer limit.

| Execution | Gravity weighted RMS | Magnetic weighted RMS | Seconds |
| --- | --- | --- | --- |
| Controlled reference, tutorial's mixed engines | 1.1035 | 0.4432 | 42.5 |
| Controlled reference, Choclo for both fields | 1.1206 | 1.1398 | 44.4 |
| TerraWorkbench joint, Choclo | 1.1206 | 1.1398 | 48.6 |
| TerraWorkbench gravity alone | 0.9525 | — | 15.7 |
| TerraWorkbench susceptibility alone | — | 0.9619 | 14.5 |

With the same Choclo engine, Core and the controlled reference produced identical
models and predictions on this run. The reproducible check allows a relative
L2 difference up to 0.000001. The original mixed-engine reference used Geoana
for magnetics; relative Core differences were 4.66 percent in density, 8.33
percent in susceptibility, 0.142 percent in gravity predictions and 3.55 percent
in magnetic predictions. This difference is retained, not silently calibrated
away or described as full published-recipe equivalence.

The Choclo/Geoana magnetic matrices differed by only about 0.00000000000467
in relative Frobenius norm. The different inversion trajectories show numerical
sensitivity in this underdetermined nonlinear joint problem at the chosen
iteration/CG limits. Core reaching ten iterations is not convergence. The
supplied true models predict the observations at weighted RMS about 0.9902 for
gravity and 1.0101 for magnetics, consistent with the declared synthetic noise.
Some included separate-inversion model values are nonfinite on the active mask;
those models are reported as unavailable for comparison, not filled or altered.

Observed process-tree RSS peaks were approximately 438 to 718 MiB across cases,
including interpreter overhead and the extra matrix in the engine comparison.
Sampling includes Windows virtual-environment launcher descendants; measuring
only the small redirector process would underreport memory. RSS sampling is
not a hard maximum or a solver RAM guarantee. Cache state, compilation and
machine load affect timings; the table is not a controlled speed ranking.

## Interpretation and limits

All computations ran through Python/Core without QGIS. These sizes therefore
demonstrate backend capability, not a QGIS-imposed cell or iteration limit.
The active-cell limit and dense-sensitivity byte guard are Core controls; RAM,
I/O and solver convergence remain practical constraints.

The recovered joint models differ substantially from the supplied true model:
relative L2 errors are about 96 percent for density and 91 percent for
susceptibility. Agreement with a reference implementation and good data fit
do not demonstrate unique geometry, resolution or successful geological recovery.
The benchmark does not certify millions of inversion observations, real-survey
metadata handling, arbitrary priors or commercial-software parity. No benchmark
data, private surveys, images or installed dependency changes are bundled in the
plugin. Numerical reports record library versions, source hashes and input hashes.

## Repeat on 28 October 2026

The [archived numerical record](../records/public_inversion_20261028.json)
retains six fresh Windows executions with the same public inputs and recipe.

| Case | Gravity weighted RMS | Magnetic weighted RMS | Seconds |
| --- | --- | --- | --- |
| reference | 1.103482895 | 0.443191948 | 72.8 |
| reference_choclo | 1.120628933 | 1.139767906 | 76.3 |
| reference_weighted | 0.747097866 | 1.025558329 | 71.0 |
| joint | 0.747097866 | 1.025558329 | 68.9 |
| gravity | 0.952500441 | not applicable | 13.6 |
| susceptibility | not applicable | 0.961922468 | 13.4 |

Core joint and the separately assembled weighted reference have zero recorded
relative difference in density, susceptibility and both predicted fields. Both
share SimPEG; this validates recipe integration, not that dependency independently.

The ten-iteration reproduction intentionally uses the tutorial-compatible
Hessian option and reaches its iteration limit. Its inner and outer stopping
flags remain false and are retained in the record. It must not be presented as
a converged inversion. A separate from-start Gauss-Newton run reached its
operational convergence criterion in 58 iterations, as recorded in
the [convergence analysis](inversion_convergence_resolution.md). Relative errors
against the supplied true voxel models remain large; fitting the observations
does not resolve geological nonuniqueness.

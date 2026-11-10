# MVI and parameterized electrical, EM and SP validation

Campaign dated 27 October 2026. All inputs are authored synthetic data. No
private survey, acquisition settings, screenshots or QGIS session were used.
Numerical algorithms are unchanged in this campaign; the additions are a
reproducible test harness, regression controls and this evidence report.

Reproduce with scripts/validate_inversion_methods.py and a new output directory.
Sections potential, direction, electrical, fdem and sp can run separately.
The complete campaign has 48 cases, including one deliberately insufficient
MVI run. This does not mean 48 converged geological inversions.

All cases reuse one Gaussian realization, seed 413, with explicitly scaled
noise. These are controlled sensitivity checks, not Monte Carlo confidence or
survey-wide reliability estimates. Data-fit criteria were training weighted RMS
below two and holdout RMS below three where available. The deliberately short
run is expected to fail its target. Optimizer success, data fit, inner tolerance
and geological model recovery remain distinct evidence.

## Cartesian MVI: prediction succeeds, orientation remains conditional

The independent 200 m cube volume-quadrature reference supplies 49 observations
and 36 noiseless holdout points at another height. The mesh has 324 active cells
and 972 vector parameters. Three magnetization orientations and noise scales
0.5, 1 and 2 supply nine runs; initial beta ratios 0.3 and 3 and float32/disk
sensitivities add three further full MVI runs. Two scalar potential-field
controls and a one-iteration MVI negative control complete the 15-case section.

All 12 full MVI runs reach their declared data target and meet the final inner
CG tolerance. Training weighted RMS spans 0.558–0.971 and independent holdout
RMS spans 0.490–0.977. Float32/disk and float64/RAM predictions remain close in
this example. The one-iteration control has training RMS 6.739 and holdout
6.233; its workflow executes and exports successfully, while target_reached is
false and iteration_limit_reached is true. A regression preserves that distinction.

However, the volume-integrated recovered vector has angular errors about
5.8–39.1 degrees across the full MVI cases. Cell-vector relative L2 errors are
about 96–97 percent. These results do not validate recovered voxel directions,
body extent or amplitude merely because predicted anomalies fit well.

A separate diagnostic prescribes the exact cube geometry and fits only its
three uniform Cartesian vector coefficients. Each unit-axis response is checked
against independent volume quadrature. Across three orientations and four noise
levels, all 12 controls have rank three; noiseless coefficients recover to the
specified numerical tolerance, and maximum noisy angular error is 0.653 degrees.
This checks component signs/scales for this experiment and is consistent with
ambiguity/regularization in the free voxel problem. It is a known-body
least-squares control, not a new voxel-MVI algorithm or a proof that every
possible direction error has been excluded.

The vector parameters are effective susceptibilities in SI, consistent with
[SimPEG's vector model contract](https://docs.simpeg.xyz/v0.25.0/content/api/generated/simpeg.potential_fields.magnetics.Simulation3DIntegral.html).
They are not directly A/m. Magnetization equals the effective vector multiplied
by H0; this experiment uses H0 = B0 divided by mu0. The existing Cartesian MVI
recipe used VectorAmplitude regularization without vector references or IRLS
controls. The later [dispersive-IP and constrained-MVI extension](../../reference/methods/dispersive_ip_mvi.md)
adds those optional controls and component smoothness. The historical numbers
above retain their original recipe. Informative priors and further geometry
tests remain necessary before claiming reliable unconstrained voxel orientation.

The gravity and scalar susceptibility controls reach training RMS 0.890 and
0.869 and holdout RMS 0.442 and 0.792 respectively. Their cell-model errors
remain approximately 89 and 86 percent, again separating prediction from recovery.

## Electrical, FDEM and SP: fixed-geometry recovery

| Method | Cases | Noisy training weighted RMS | Observed noisy model error |
| --- | --- | --- | --- |
| Two-layer DC sounding | 6 | 1.024 | 0.77–1.53 percent |
| DC 2.5D, two zones | 3 | 1.081–1.084 | 3.28–6.59 percent |
| Static IP 2.5D, two zones | 3 | 0.926 | 2.66–5.33 percent |
| FDEM 3D, two zones | 6 | 1.174 | 4.00–8.36 percent |
| SP 3D, two prescribed sources | 3 | 0.969 | 0.0043–0.0086 percent |

The zero-noise cases recover their prescribed coefficients within their
predeclared tolerances. All nonlinear fits report success. The six sounding
and six FDEM cases include two substantially different starts; no meaningful
local-start disagreement appeared in these examples. Sounding also passes a
separate analytic homogeneous-half-space check. Its layer thickness stays fixed.

FDEM fits full within-record real/imaginary covariance with correlation 0.4.
Four training frequencies and three held-out frequencies give noisy holdout
weighted RMS about 0.135. The local weighted data-Jacobian singular values are
about 167 and 7.46 at one-percent noise: this describes only the two prescribed
conductivity zones, not resolution of a free 3D conductivity volume.

IP holds conductivity fixed. SP holds conductivity, source templates and a
noiseless reference fixed; source templates are individually neutral. SP's
noisy holdout RMS is 0.190. Its small conditional coefficient uncertainties
exclude conductivity, source-geometry and reference-error uncertainty. They
must not be presented as complete geological uncertainty.

Unlike the potential-field observations, these electrical/EM/SP data are
generated with the same forward kernel used by their fit. Holdout frequencies
or locations test conditional prediction, not independent physical validation.
The existing 3D DC/IP, analytic-half-space, FDEM mesh-refinement, conservation,
budget and cancellation regressions remain separate coverage; this sensitivity
campaign does not upgrade them into real-survey or unrestricted 3D-inversion
validation. No transient-IP, general TEM inversion or seismic inversion claim
is added by this report.

## Evidence and status

Reports include core-source hashes, script hash, versions, declared criteria and
per-case results. The 36-case run is retained under
evidencia conservada en el archivo de desarrollo del proyecto, corrida 20261027_135731_beca4d17054d439fb60e1fd13e2d7cbb.
Its exact executed harness snapshot is saved one directory above the report,
with its hash verified before adding the later direction section. The additional
12 direction controls are under the same session root in
20261027_140033_65bc1cd4a900445bb0b88461f14f8f25/direction.
Potential-field workflow folders retain NPZ, VTK, residual CSV and run manifests.

No new execution failure was found in these supported examples. MVI prediction
is supported by the independent holdout, but its voxel-direction recovery is
not closed. The electrical/EM/SP findings apply to their explicitly fixed
geometry and limited parameter sets. The separately validated joint
gravity–magnetic convergence result is unchanged.

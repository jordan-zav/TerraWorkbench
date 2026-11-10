# Inversion convergence and conditional resolution

Campaign dated 27 October 2026. Reproduce using the repository script
scripts/validate_inversion_resolution.py with a new output directory. The
inversion, prisms and validation extras supply its optional dependencies. The
resolution, synthetic and public sections can run separately. All numerical
outputs remain outside the repository. No private survey or images were used.

## Public joint inversion: data fit is not solver convergence

The first table records the preconditioner used at commit 4ebc17a. The correction
and subsequent measurements appear immediately below it; these historical
numbers are retained rather than silently replaced.

The pinned SimPEG public dataset, exact 47,860-active-cell mesh, observations,
field, bounds, noise, seed and coupling recipe are retained from the preceding
[public benchmark](public_inversion_benchmark.md). Both property references stay
at 0.000001, separately from starting models. Each case starts afresh; it is not
a continuation from a previously recovered model.

| Case | Outer budget | Inner CG budget / tolerance | Precision | Gravity / MAG weighted RMS | Final inner relative residual | Seconds |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | 10 | 100 / 0.001 | float32 | 1.121 / 1.140 | 0.916 | 38.7 |
| More outer iterations | 30 | 100 / 0.001 | float32 | 0.618 / 0.927 | 0.591 | 100.5 |
| Larger, more precise solve | 30 | 300 / 0.0001 | float64 | 1.003 / 0.999 | 0.0431 | 317.8 |
| Coupling weight zero | 30 | 300 / 0.0001 | float64 | 0.568 / 1.000 | 0.0000974 | 155.3 |

The first three coupled cases exhaust their budgets without meeting their inner
CG tolerance. The uncoupled case reaches the inner tolerance after 163 CG steps
in its final outer iteration; its outer inversion still reaches the iteration
limit. This supports investigating conditioning/preconditioning of the coupled
problem. It is not proof of a specific cause, or a universal recommended weight.
Weight zero removes the structural joint constraint.

The third case deliberately bundles precision, inner budget and tolerance
changes as an operational comparison. It does not isolate their individual
causal effects. Data RMS near one only describes fit relative to declared noise;
smaller RMS can also fit noise. The recovered public cell-model relative L2
errors remain about 93–96 percent for density and 91–92 percent for susceptibility.
Neither extra iterations nor agreement with a recipe establishes unique recovery.

## Corrected weighted joint preconditioner

The SimPEG 0.25.0 UpdatePreconditioner directive used by the original joint
recipe sums individual regularization diagonals without the combination's
paired-beta and coupling multipliers. It also uses the normal-matrix diagonal
without the factor two in the L2 data Hessian. Core now forms the diagonal of
the full weighted regularization Hessian and adds twice each weighted data
normal-matrix diagonal. It refreshes this after each paired-beta update. The
objective, observations, uncertainties, field, bounds, references and coupling
weight are unchanged. No installed dependency is modified.

A regression compares this diagonal against an explicitly assembled Hessian
with unequal data weights, strongly unequal property betas and nonzero coupling,
then changes the betas and checks again. The public benchmark retains both
legacy tutorial references and adds reference_weighted, which constructs the
corrected diagonal separately from Core. The same-engine comparison now names
that corrected reference explicitly instead of expecting the old iteration path.

Two new public runs retain coupling 2e12, float64 sensitivities, a 300-step CG
budget and relative CG tolerance 0.0001:

| Outer budget | Gravity / MAG weighted RMS | Final CG steps | Final CG relative residual | Outer relative model change | Seconds |
| --- | --- | --- | --- | --- | --- |
| 30 | 1.000713 / 0.998896 | 210 | 0.00008554 | not recorded in this run | 443.0 |
| 100 | 0.999976 / 1.000006 | 223 | 0.00009754 | 0.00009614 | 1495.8 |

The comparable old 30-iteration residual was 0.04315: the correction reduces
it by approximately 504 times and meets the inner tolerance without removing
coupling. In the new trajectory, CG misses its budget during intermediate
iterations 4 through 25, then meets tolerance at every recorded iteration from
26 through 100. This is not a claim that all inner systems were solved fully.
Timings reflect separate runs and are not a controlled speed comparison.

The 100-iteration run still exhausts its outer budget. Both squared data-misfit
ratios satisfy the stopping band's ten-percent tolerance, but relative model
change exceeds 0.000001. Core now reports relative_model_change,
data_target_tolerance_met and outer_convergence_met and requires the inner
tolerance as well before declaring outer convergence. The strict
unit_weighted_rms_met flag remains separate from that statistical stopping band.
It does not loosen the model-change threshold to obtain a favorable result.

At this stage the preconditioner defect was corrected, while complete outer
convergence remained unproven. The subsequent Gauss-Newton experiment below
resolves that remaining benchmark failure. Cell-model errors still reach
about 93 percent density and 92 percent susceptibility; improved numerical
conditioning does not remove the geological ambiguity.

Evidence is retained in isolated sessions under evidencia conservada en el archivo de desarrollo del proyecto, corrida inversion_convergence_resolution
20261027_100249_1fe17eb60c71437080632fbbeb91f4a8
and 20261027_101301_7c6100c019d94b8492cc130d95545e37. Each weighted/report.json
records source and input hashes, versions, controls, histories and diagnostics.

## Outer convergence with the residual Gauss-Newton Hessian

Core now defaults cross_gradient_hessian to gauss_newton. The simpeg option
retains the preceding stabilized approximation for recipe reproduction. Both
use SimPEG's unchanged cross-gradient objective and first derivative. The
new Hessian is twice the residual Jacobian's normal matrix, not the exact
indefinite Hessian of the nonlinear objective. No beta schedule, coupling
weight, noise, bound or stopping threshold was relaxed.

Let A contain the nonnegative cell-to-face averaging weights including the
square root of cell volume, and let u and v be the two face gradients. For
each cell and face pair i less than j, define the residual as
sqrt(A_i A_j) times (u_i v_j minus u_j v_i). The sum of their squares equals
the existing cell objective exactly. Differentiating these residuals gives
H_GN = 2 J_transpose J. Core builds its sparse blocks once per distinct model
and reuses them for inner products and the preconditioner. A model copy
protects cache invalidation against in-place changes.

Independent tests explicitly enumerate those face-pair residuals and their
Jacobian on nonuniform 2D and 3D meshes with an excluded cell. They verify
the objective, unchanged gradient, finite-difference residual derivative,
Hessian matrix, matrix-vector product, positive-semidefinite identity and
in-place cache invalidation. They also preserve the native simpeg-mode matrix.

After a preliminary warm-start investigation, the decisive public run starts
afresh from uniform 0.000001 values for both properties. It retains the original
47,860 active cells, 578 total observations, fixed references 0.000001, bounds,
field, uncertainty and coupling 2e12. It uses float64 sensitivities, CG budget
600, inner relative tolerance 0.00001 and outer budget 60:

| Result | Observed value |
| --- | --- |
| Outer iterations | 58, converged before the limit |
| Final relative model change | 0.000000850689, required at most 0.000001 |
| Final relative CG residual | 0.00000980983, required at most 0.00001 |
| Final CG iterations | 333 |
| Gravity / MAG weighted RMS | 0.999999958 / 0.999999998 |
| Elapsed seconds | 633.6 |

All 58 recorded inner systems meet their requested tolerance. Both data-target
and outer-convergence flags are true; iteration_limit_reached is false. Paired
beta values for the next iteration are retained in each history entry. This
demonstrates the operational outer stopping criterion for this public recipe,
not unique geology or a general gradient-stationarity certificate. Cell-model
errors remain about 93 percent density and 92 percent susceptibility.

The old and new runs change both the Hessian strategy and inner accuracy/budget,
so their timings do not isolate a single change or establish a universal speedup.
The scalar/vector engine and its iteration defaults are unaffected. The joint
iteration/CG defaults also remain unchanged; this large validation recipe must
explicitly supply its larger budget and tighter inner tolerance.

Reproduce the new case using the public section of
scripts/validate_inversion_resolution.py. Its gauss_newton case allows 80 outer
iterations as headroom for platform variation and fails unless convergence
occurs before the limit. The legacy benchmark script explicitly selects simpeg
mode for its reference-comparison recipe; joint-options can override that mode.
The measured fresh run and complete artifacts remain under
evidencia conservada en el archivo de desarrollo del proyecto, corrida 20261027_105800_1e0effc6cd2e42029ca669311102e9aa.

## Small cube: starting values, beta, noise and sparsity

Nine scalar susceptibility runs use the independently integrated 200 m cube,
49 noisy observations, 36 noise-free holdout locations, 324 active cells and
the fixed zero reference model from the earlier synthetic campaign. The cube
centroid depth is 200 m. Starts are varied independently of that reference.

| Case | Training weighted RMS | Holdout RMS in baseline noise units | Recovered centroid depth m |
| --- | --- | --- | --- |
| Baseline, 40 iterations / CG 200 | 0.75 | 0.63 | 213.3 |
| Only two outer iterations | 6.03 | 5.21 | 224.3 |
| Start zero | 0.80 | 0.65 | 215.4 |
| Start 0.005 SI | 0.75 | 0.63 | 213.3 |
| Initial beta ratio 0.1 | 0.97 | 0.69 | 217.8 |
| Initial beta ratio 10 | 0.85 | 0.66 | 215.4 |
| Declared errors halved | 0.96 | 0.65 | 198.7 |
| Declared errors doubled | 0.74 | 1.04 | 219.2 |
| L1 norms with three IRLS cycles | 0.87 | 0.67 | 213.7 |

Except for the deliberately insufficient two-iteration run, these runs meet
their data-fit targets. Their cell-model relative errors remain about 85–86
percent. A plausible centroid does not prove correct extent or amplitudes.
Changing the error scale changes the weighting and stopping target; errors must
come from a defensible noise model, not be adjusted merely to pass a test.

## Conditional coefficient resolution

Two prescribed 80 m prisms have unknown property coefficients. Linear resolution
and covariance use fixed Gaussian priors, fixed beta and physical-unit data errors.
An independent SVD calculation agrees with Core's Cholesky calculation to relative
and absolute tolerance 0.0000000001. This does not compute a regional voxel
posterior or account for unknown geometry, adaptive beta, IRLS or model error.

| Configuration | Effective coefficients, gravity | Effective coefficients, MAG |
| --- | --- | --- |
| Depth 150 m, separation 200 m | 1.999 | 2.000 |
| Depth 150 m, separation 90 m | about 2.00 | about 2.00 |
| Depth 650 m, separation 90 m | 1.26 | 1.20 |
| Depth 150 m, observation height 250 m | 1.91 | 1.94 |
| Depth 150 m, errors four times larger | 1.93 | 1.98 |

The maximum is two because the geometry is prescribed and only two coefficients
are unknown. The trace is not a probability, a count of geological bodies or a
universal depth-of-investigation cutoff. Prior scales are 0.4 g/cm3 for density
and 0.025 SI for susceptibility; baseline errors are 0.002 mGal and 0.3 nT.

## Alternative depth and separation hypotheses

Eight profile curves use 81 synthetic observations with Gaussian noise, seed 52,
and analytically computed prism fields. Each candidate geometry fits a single
nonnegative amplitude. The separation experiment prescribes two equal prisms
and their depth; the depth experiment prescribes one prism's horizontal location
and size. These assumptions substantially simplify real geological inversion.

At true depth 150 m, the minimum selects the true 150 m depth and 100 m separation
for both properties. At true depth 650 m:

- gravity's one-unit profile-misfit set spans sampled depths 375–800 m and touches
  the grid limit, so it does not supply a bounded depth estimate;
- magnetic depth has its minimum at 400 m; its one-unit set is 300–575 m and does
  not include the true depth, illustrating noise sensitivity rather than a
  calibrated confidence interval;
- both separation experiments admit every tested separation from 80 to 400 m
  within one unit of the minimum misfit.

These are sets defined by delta chi-squared at most one on an explicit finite
grid. They are not 95-percent intervals or geological depth estimates. The full
curves, fitted amplitudes, truth and grid-edge flags are preserved in JSON.

## Core controls and remaining work

Core exposes joint inner CG budgets/tolerances, Hessian mode and independent
references. The default joint Hessian strategy changes as described above;
iteration budgets and tolerances retain their existing defaults. Histories and final
diagnostics expose whether the inner solve met its requested tolerance, separately
from execution completion, data fit and the outer iteration limit. Scalar
inversion also exposes its relative CG tolerance. No installed solver is patched.

The corrected large coupled case now meets both inner and outer stopping
conditions with the explicitly tested Gauss-Newton recipe. Real surveys,
different geology, model discretization and correlated/systematic noise remain
outside this campaign. Passing regression tests means these contracts and
diagnostics work; it does not turn a budget-limited result into a converged model.

Primary controls: [SimPEG projected CG](https://docs.simpeg.xyz/v0.25.0/content/api/generated/simpeg.optimization.ProjectedGNCG.html),
[weighted regularization](https://docs.simpeg.xyz/v0.25.0/content/api/generated/simpeg.regularization.WeightedLeastSquares.html).
The original diagonal construction is documented under
[UpdatePreconditioner](https://docs.simpeg.xyz/v0.25.0/content/api/generated/simpeg.directives.UpdatePreconditioner.html).

## Public rerun on 28 October 2026

The [archived record](../records/public_inversion_20261028.json) includes a fresh
from-start run using the same public mesh, active mask, noise, coupling and
reference models. The numerical controls are float64 sensitivity, inner budget
600, CG relative tolerance 0.00001 and an outer budget of 80. The larger outer
cap does not change a trajectory that stops before reaching it.

| Diagnostic | Observed value |
| --- | --- |
| Completed outer iterations | 58 |
| Outer convergence met | true |
| Iteration limit reached | false |
| Final inner relative residual | 9.80982679606e-06 |
| Final relative model change | 8.5068906467e-07 |
| Gravity weighted RMS | 0.999999957776 |
| Magnetic weighted RMS | 0.999999998321 |
| Recorded inner systems meeting tolerance | 58 of 58 |
| Density relative cell-model error | 0.930195319 |
| Susceptibility relative cell-model error | 0.922654045 |
| Elapsed seconds | 921.2 |

These diagnostics establish the stated operational convergence for this public
synthetic recipe. They do not establish a unique geological model, field-survey
accuracy or convergence for arbitrary datasets. Full histories, versions,
source hashes and true-model error diagnostics remain available in the record.

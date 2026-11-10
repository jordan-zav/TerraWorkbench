# Spherical IRLS strategies and numerical safeguards

This follows the [stopping and chart investigation](mvi_stability.md). The
previous adaptive run reached data WRMS 1.0890 and 169.34 percent relative voxel
error on the published-example geometry. That failed recovery remains archived.
This work separates completion of an inner optimization from changes to its
objective. It uses synthetic data only.

## Controller

The previous Core schedule followed the SDK reference: beta, sparse weights,
angle scaling and sensitivity-prior weights could change after every accepted
Newton step. Such an adaptive method is not equivalent to solving a succession
of fixed weighted least-squares subproblems. The fact that a single Newton step
was accepted does not establish that its subproblem was solved. This is an
algorithmic policy difference, not a claim that the published S-IRLS method or
SimPEG is universally incorrect.

The default mvi_irls_update value is adaptive. It retains the reference
per-Newton update schedule, with the numerical safeguards described here.
The new lagged value is an explicit experimental diagnostic alternative.
The frozen controls did not finish their first subproblem within 40 steps;
silently substituting that strategy would stop existing recipes from reaching
their sparse stage. Both modes are available through the Core API and typed
parameter forms. Spherical MVI itself remains opt-in.

With mvi_irls_update set to lagged and a positive irls_iterations budget,
Core freezes beta and all prior
weights inside each subproblem. The numerical Jacobi preconditioner is still
updated for the current mapped Jacobian. Exact-zero chart recovery preserves
the fixed physical prediction and accepts only non-increasing fixed prior cost.
At each evaluated iterate the controller checks a projected-gradient reduction
before allowing another adaptive update.

For the diagonal H0 captured at the beginning of an epoch, define

    q(m) = norm(sqrt(H0) * (projection(m - gradient(m)/H0) - m)).

An inner solve is accepted when q is at most the larger of 0.001 times its
initial value and 1e-12. The metric is held fixed for that epoch. The relative
criterion is an explicit inexact-solve policy; it does not imply exact KKT
stationarity, a unique solution or a convergence theorem for nonlinear MVI.
Every evaluated cost is checked against the preceding cost in the same epoch.
A substantive increase raises an error rather than being silently accepted.

For positive IRLS budgets each angular component is bounded to pi/4 before
the first Armijo attempt, using the existing descent-preserving safeguard.
Previously the bound was tried only after a failed search; a very short accepted
global step could still attenuate a useful amplitude update because of an
enormous angular component. The limit changes the numerical search direction,
not the objective, bounds or data. Small Newton directions remain unchanged.
Non-IRLS solves retain the earlier failed-search retry policy.

If a search still fails, Core tries a feasible projected Jacobi-gradient
direction: projection(m - Hdiag_inverse * gradient) minus m, with the same
angular cap. Projecting this endpoint before backtracking prevents an enormous
raw diagonal-gradient step from staying clamped to a distant bound through all
20 trials. Original, bounded-angular retry and projected-gradient rescue each
have the existing finite 20-backtrack budget. Every accepted trial still passes
the same Armijo decrease test. Diagnostics label the rescue kind explicitly.

After inner acceptance, the existing SDK cooling and IRLS rules operate once.
Their cooling cadence counts completed subproblems. Angle and sensitivity priors
are refreshed only at those boundaries, and the next objective is evaluated
before searching again. Cross-epoch costs are different functions and must not
be interpreted as one monotonic objective.

The existing iterations parameter remains the total spherical Newton budget.
irls_iterations remains a maximum number of IRLS reweightings. Objective updates
also have a finite cap equal to iterations, preventing endless beta-only updates
when the constrained data target is unattainable. Budgets are not multiplied
silently. An unfinished subproblem can consume the entire Newton budget without
starting sparse IRLS; diagnostics report that outcome explicitly. With
irls_iterations equal to zero the previous non-IRLS path is retained.

## Independent checks

Exact polar maps now set the horizontal cosine to zero at theta equal to
plus/minus pi/2. The Jacobian and mapped diagonal use the same convention.
At a blocked pole, Core can reorient the physically undefined azimuth toward
the negative horizontal physical gradient, preserving the magnetization and
requiring a non-increasing fixed prior plus a feasible descent in theta.
Excluded cells and fixed directional priors remain protected.
[Polar regressions](../../../tests/test_spherical_poles.py) check both poles against
finite-difference Jacobians and verify exact physical preservation.

The legacy step-only ablation in benchmark_mvi_stability explicitly retains
raw SDK CG stopping, while the guarded production variant uses both residual
norms and chart recovery. Its recorded optimizer_metrics field makes that
distinction explicit instead of silently changing the historical ablation.

IRLS initialization retains a term's previous valid positive threshold when
its model percentile is exactly zero. This avoids failing on a zero angular
component even when another component contains signal. The zero-component
regressions exercise adaptive and lagged modes and require that the zero
component remain exactly zero; the safeguard does not perturb the model.

A separate irreducible-noise control has observations in the left null space
of its forward operator. The zero model already has zero prior penalty and
fits within the declared uncertainty. Core returns that stationary minimum
without constructing invalid zero IRLS thresholds or inventing signal.

The spherical PCG solver now requires both the raw relative residual and the
Jacobi-scaled relative residual to meet cg_rtol. For the fixed current diagonal
inverse M, the latter is sqrt(r.T M r) divided by sqrt(b.T M b), on the inactive
subproblem. This removes the ability of a large SI-amplitude gradient component
to hide a poorly resolved angular component. The original raw requirement is
retained. True residuals are recomputed before accepting CG; recursive residual
drift restarts the recurrence within the same finite CG budget. Cancellation is
checked between matrix products. This current-Newton metric differs from the
epoch-initial metric used for nonlinear inner convergence.

[test_spherical_cg_metric.py](../../../tests/test_spherical_cg_metric.py) constructs
a three-variable positive-definite system with known diagonal coordinate
scaling. Raw-only stopping accepts a relative residual of about 8e-7 while the
scaled residual is 0.5657 and the independent solution differs by over 50 percent.
The corrected solve meets both residual criteria and matches the independent
dense solution to the specified 1e-10 relative tolerance. This is a solver
counterexample, not a model-recovery benchmark. Diagnostics retain both norms,
residual replacements and any curvature breakdown; a finite CG budget remains
a limit rather than a convergence certificate.

The mixed-unit bound-step correction is separate from the IRLS controller.
The SDK active-set fallback scales all free-bound components using the maximum
inactive step. With amplitude in SI and angles in radians this couples unlike
units: an unrelated large angular step can inflate an amplitude correction.
Core now replaces only the free-bound components with their own Jacobi-scaled
negative gradient. The inactive CG solution is unchanged, and the existing
projected Armijo test still decides whether to accept the combined direction.
The true CG residual continues to audit only that inactive subproblem.

[test_spherical_bound_scaling.py](../../../tests/test_spherical_bound_scaling.py)
uses an independent diagonal quadratic with amplitude curvature 100 and gradient
minus 100, so its unconstrained optimal amplitude step is exactly one. Changing
an unrelated angular curvature between 1e-8 and 1e-12 changes the SDK amplitude
step from 1e6 to 1e10. The corrected amplitude step remains one and the inactive
CG step is identical. Diagnostics record spherical_bound_step_scaling and the
original/corrected magnitudes in spherical_bound_step_events.
The inactive CG residual is audited before the angular and bound-step
safeguards; it is not a residual of the subsequently modified search direction.
The additional line-search regression deliberately supplies a direction of
1e40 and an oversized diagonal inverse. The original 20 trials cannot decrease
the known quadratic; the projected rescue produces a feasible decreasing step.

[test_lagged_irls.py](../../../tests/test_lagged_irls.py) uses a fully determined,
diagonal forward operator and a changing sparse prior. Before every adaptive
update it independently solves the frozen dense normal equations. This checks
that the update occurs at a solution of the preceding subproblem, rather than
merely mirroring a controller counter. It also checks within-epoch objective
descent and actual entry into IRLS. Existing physical tests retain amplitude
caps, cancellation, matrix-free parity, source manifests and zero-data behavior.

The capped physical control checks actual IRLS counts against the budget and
the acceptance criterion at every completed subproblem. Its old assertion that
IRLS must have run was inappropriate for an unfinished inner solve. A separate
one-step budget test checks that no adaptive update is counted after the Newton
budget has already been spent. Requested sparsity is not evidence that
reweighting actually occurred.

Classical IRLS formulations solve a weighted subproblem before updating weights;
see [Daubechies et al.](https://arxiv.org/abs/0807.0575) and
[Voronin and Daubechies](https://arxiv.org/abs/1511.08970).
Their linear sparse-recovery results do not prove convergence for this bounded,
nonlinear spherical implementation. The MVI formulation and iterative scaling
motivation remain [Fournier et al.](https://doi.org/10.1190/geo2019-0244.1).

## Evidence and interpretation

The [archive](../records/public/lagged_irls_20261102.json) retains previous and new
results, actual stop reasons, frozen-epoch traces, source hashes and budgets.
The frozen-only and frozen-plus-Jacobi forty-step controls are retained
separately from the final bounded-angular strategy. Extended prototypes were
interrupted after the next analytic mechanism was identified; they have no
completed scientific verdict and are not counted as passes.
The matched published case keeps CG 200, Newton 40 and IRLS 20. A separately
declared reference-adaptive convergence control uses CG 800 and Newton 80.
Both retain the same synthetic data and all
six geological recovery criteria; truth never enters the optimizer.

## Recorded results

The local campaign uses 400 observations and 27,971 active cells. Numerical
versions, actual source hashes and full traces are recorded in the archive.
The corrected runs both finish 20 IRLS cycles after 23 spherical steps.

| Configuration | Data WRMS | Relative voxel error | Body direction error | Recovery criteria passed |
| --- | --- | --- | --- | --- |
| Previous adaptive, CG 200 | 1.08898 | 169.34% | 3.49 deg | 1 / 6 |
| Corrected adaptive, CG 200 | 0.99446 | 63.70% | 0.489 deg | 5 / 6 |
| Corrected adaptive, CG 800 | 0.99485 | 63.68% | 0.486 deg | 5 / 6 |

The CG-800 control meets both required residual tolerances on all 28 audited
solves, including the Cartesian initialization. The CG-200 control has 11
solves that miss at least one required tolerance, including its final solve.
The volume-weighted model difference between these two budgets is 0.4285
percent; this is a local budget comparison, not cross-platform reproduction.

The corrected results have one recovered component, centroid error 7.67 m,
support Dice 0.7957 and volume error 6.25 percent. Contrast error is about
30.31 percent. Location, volume, support, contrast and direction meet their
unchanged criteria. The global relative voxel error still exceeds the frozen
50 percent limit, so both geological recovery verdicts remain failed.
Stopping at the IRLS cycle budget is also not a proof of an outer fixed point.

The frozen-only control reaches 100.05 percent model error but completes no
IRLS updates within 40 steps. Successive numerical prototypes are retained,
including the bounded-angular control that still failed its line search.
These results explain why the lagged strategy remains an explicit diagnostic
choice while the reference adaptive schedule remains the production default.

The final local regression suite passed 855 tests. Independent checks cover
raw/scaled CG residuals, finite-difference polar derivatives, fixed-objective
subproblem solutions, zero components, irreducible noise and cancellation.

The follow-up 40-cycle control repeats the earlier failed CG-800 / Newton-80 /
IRLS-40 budget with the corrected code and identical inputs and criteria.
The earlier run had WRMS 2.2507 and 1004.01 percent model error. The corrected
run has WRMS 1.04463 and model error 50.008407 percent. All 48 audited solves
meet the raw and scaled criteria. It again stops at the IRLS budget, after
43 spherical steps, rather than proving an outer fixed point.

The 40-cycle model still fails the exact 50 percent model-error cutoff; rounding
the displayed value must not turn that verdict into a pass. Its other five
criteria pass: centroid error 3.53 m, volume error 27.08 percent, support Dice
0.8434, contrast error 21.35 percent and body direction error 4.64 degrees.
Its strict target_reached flag is false because WRMS exceeds 1; the misfit lies
inside the reference IRLS schedule's declared 10 percent chi-square band.

Diagnostics add irls_update_mode, irls_inner_relative_tolerance,
irls_subproblems, irls_inner_history and irls_stop_reason. A Newton budget,
IRLS budget, objective-update budget or failed line search is not successful
outer convergence. Inner precision, data fit and geological recovery must still
be assessed separately. The [causal audit](mvi_causal_diagnosis.md) documents the
large numerical null space; changing the optimizer cannot supply missing data.

The legacy cg_tolerance_met and cg_true_tolerance_met flags describe the raw
residual. Spherical precision also requires cg_scaled_tolerance_met; inspect
both norms and their histories. The benchmark's historical numerical_passed
flag checks the final raw residual only. It does not certify all inner solves,
the scaled criterion, outer convergence or geological recovery.

# MVI causal diagnosis

Synthetic controls executed on 2 November 2026. This report separates physical
consistency, numerical convergence and recovery of the generating model.
It does not certify field-data recovery or a unique geological interpretation.

The [ordered plan](../README.md) and [complete evidence](../records/mvi_causal_diagnosis_20261102.json) record the scope and negative results.

The subsequent [stability investigation](mvi_stability.md) isolates concrete
stopping, exact-zero chart and angular-search counterexamples and records Core
safeguards. This report's earlier runs and conclusions remain historical evidence.

## Physics and fixed L2

Independent volume integration and the analytic kernel differ by at most 1.89e-11 nT in the published geometry. The noise-free three-component uniform-prism control has relative model error 7.41e-16.

Six fixed-L2 controls use three operator-scaled beta ratios and two stopping
settings. The production optimizer agrees with augmented-SVD reference models
to 3.26e-14 relative error, with scaled optimality at most 1.1e-16.
These are optima of the stated regularized objective, not guarantees of truth.

The 100-cell control has 300 parameters, 121 independent data rows and 179
numerical null directions. Its model error stays near 99 percent despite
correct numerical minimization. Between 99.57 and 99.83 percent of squared
error energy lies in the numerical null space for these three fixed priors.

## Coordinates, priors and adaptation

Eight bounded controls agree with independent BVLS. With the physical prior preserved, spherical and Cartesian optima differ by 1.18e-13 relative L2.
The objective gradient also passes predeclared finite-difference checks.

| Cumulative change | Truth model error | Data WRMS |
| --- | --- | --- |
| Same physical L2 prior | 27.4943% | 8.7084 |
| Angular L2 prior | 12.6721% | 7.8771 |
| Angle scaling | 12.8325% | 7.8999 |
| Frozen sensitivity prior | 33.2206% | 8.4776 |
| Updated sensitivity prior | 33.4315% | 8.9297 |
| Beta cooling | 0.0000% | 3.1449e-08 |
| Sparse IRLS | 4.2879% | 1.1002 |

These stages do not all solve the same inverse problem. Only the first row
is required to match the Cartesian optimum. Subsequent changes alter the prior
or adaptation schedule, so a different model alone is not an implementation error.

The eight-cell control has full numerical column rank. With zero noise and
no regularization, its reference least-squares model agrees with truth to
4.05e-13 relative error. Under the three predeclared noise seeds, that unregularized model becomes less accurate; all seeds are retained. Fixed L2 stabilizes the solution but introduces measurable bias.

## What the large data can and cannot distinguish

The whitened, volume-scaled matrix has numerical rank 400 for 83913 Cartesian parameters: 83513 numerical null directions.

A thin SVD is computed with an explicit guarded working-array budget; no
model-by-model covariance or resolution matrix is formed. The diagnostic
uses the same volume-weighted model norm as the recovery score. Its rank cutoff
is a machine-precision cutoff, not a geological depth or noise-resolution threshold.

| Recorded model | Squared error energy in numerical null space | Relative null data leakage |
| --- | --- | --- |
| windows/cartesian_initialization | 99.8993% | 4.81e-15 |
| windows/core_spherical | 99.8747% | 4.2e-15 |
| windows/core_spherical_support_oracle | 99.9353% | 3.46e-15 |
| windows/native_spherical | 99.9849% | 5.66e-15 |
| linux_current/cartesian_initialization | 99.8993% | 4.57e-15 |
| linux_current/core_spherical | 99.9361% | 4.9e-15 |
| linux_current/core_spherical_support_oracle | 99.9215% | 3.51e-15 |
| linux_current/native_spherical | 99.9879% | 6.82e-15 |
| linux_matched/core_spherical | 99.9331% | 4.23e-15 |

This explains why fitting the observed projection does not identify the full
voxel magnetization. It does not establish that an arbitrary null-space model
is geologically acceptable. Weak nonzero modes can add further uncertainty.
The result is specific to this synthetic geometry and linearized TMI operator.

## Controlled large numerical budgets

The following additional runs use one numerical thread. They retain every
outcome and are not substitutions for the earlier two-thread Windows results.
The IRLS extension was selected because the original runs exhausted their IRLS
budget, not because a better truth score was found.

| CG / IRLS / outer budget | Data WRMS | Voxel error | Failed true CG solves | Recovery |
| --- | --- | --- | --- | --- |
| 200 / 20 / 40 | 0.9503 | 150.17% | 14 / 31 | False |
| 800 / 20 / 40 | 3.1491 | 322.05% | 1 / 31 | False |
| 800 / 40 / 80 | 2.2507 | 1004.01% | 6 / 51 | False |

A larger inner budget does not by itself establish stable nonlinear recovery.
Finite budgets, changing IRLS weights and different nonlinear trajectories
must remain visible. The convergence flags do not certify geological truth.

## Backend changes and reproducibility

Core now recomputes the residual of each inactive projected-CG subproblem,
separately from the recursive CG residual. The separate active-bound descent
step is excluded from that audit. Non-CG descent or stationary steps are labelled
explicitly. Results summarize all audited steps, not only the last solve.

Spherical diagnostics also distinguish the IRLS budget and its exhaustion from
the outer optimization budget. These changes do not introduce geological priors
or claim that a green last-CG flag resolves the model.

The new small dense reference and row/null APIs enforce explicit memory budgets.
The diagnostic scripts record input/source hashes, versions, libraries and threads.
Historical working-tree runs retain their actual dirty-state provenance.
Earlier source snapshots and complete numerical arrays remain in the isolated
development artifacts. Reconstructable synthetic inputs and full small traces are
also retained by the dedicated MVI causal diagnostics workflow.

## Interpretation and limits

Two issues must not be conflated. A numerical null-space perturbation leaves
the specified data unchanged, so it cannot explain failure to fit those data.
The poor fits in the higher-budget nonlinear runs also demonstrate unresolved
IRLS/outer optimization behavior. More inner iterations did not remove it.
Near zero amplitude, angular derivatives vanish or become poorly scaled; a
correct coordinate map alone does not guarantee robust optimization there.
This audit does not isolate a single implementation defect responsible for
all nonlinear trajectory differences, or demonstrate a universal optimizer fix.

Relative voxel L2 error is unbounded above. A value over 100 percent is not a
fraction of incorrectly classified cells and must not be labelled as such.

The demonstrated fixed-objective solvers and coordinate transformation pass
independent controls. The large parameterization remains heavily underdetermined;
adaptive prior choices and incomplete convergence can further alter its result.
Improvement requires explicit defensible model constraints, fewer independently
varying parameters or additional informative observations. Increasing iteration
counts alone is not a substitute for those assumptions. No default geological
prior was tuned to the known benchmark body.

The publication sources are [Li and Oldenburg (1996)](https://gif.eos.ubc.ca/sites/default/files/magnetics_inv.pdf)
and [Fournier, Heagy and Oldenburg (2020)](https://doi.org/10.1190/geo2019-0244.1).
They motivate the distinction between data fit, regularization and nonlinear
convergence; they do not certify this implementation or its field results.

# MVI evidence map

[Validation index](README.md) · [Documentation index](../README.md)

This map orders the magnetic vector inversion (MVI) evidence and states which
question each document answers. It does not change any report, record, frozen
protocol or published result. Each linked document keeps its own date, source
revision, scope and failures.

## Four separate questions

| ID | Question |
| --- | --- |
| Q1 | Do the forward operator and its derivatives represent the declared problem? |
| Q2 | Does the inversion fit the data and meet its numerical criteria within the declared budget? |
| Q3 | Which subsurface properties are identified by the available observations? |
| Q4 | Which recovered features are supported by independent geological evidence? |

A positive answer to one question does not answer another. A good data fit
(Q2) is not identifiability (Q3), and synthetic recovery against known truth
(Q3) is not field geological validation (Q4).

## Reading order

| Date | Document | Questions | Main recorded finding | Does not establish | Next |
| --- | --- | --- | --- | --- | --- |
| 28 Oct 2026 | [Voxel recovery validation](reports/voxel_recovery_validation.md) | Q1, Q3 | 153 synthetic cases: 7 of 120 nonoracle cases pass; MVI passes 0 of 40; exact-geometry oracles pass 30 of 30; three wrong supports rejected | Free-voxel recovery; results on a coarse 100 m mesh | MVI references |
| 29 Oct 2026 | [MVI references](reports/mvi_reference_validation.md) | Q1, Q2 | Native SimPEG and Core agree; both retain substantial model error | Unrestricted MVI recovery | Spherical method |
| 29 Oct 2026 | [Spherical MVI method](../reference/methods/spherical_mvi.md) | Q1, Q2 | Staged spherical API, angle conventions, storage and its validation | Geological recovery | Diagnostic plan |
| Plan | MVI diagnostic sequence (development archive) (Spanish) | Q1 to Q3 | Ordered controls separating implementation, convergence and resolution | Any result by itself | Causal diagnosis |
| 2 Nov 2026 | [MVI causal diagnosis](reports/mvi_causal_diagnosis.md) | Q1, Q2, Q3 | Kernel agrees with independent integration to 1.89e-11 nT; fixed L2 optima match SVD references; numerical rank 400 for 83,913 parameters | A unique geological model; the null-space fractions are specific to the recorded runs and operator | Stability |
| 2 Nov 2026 | [MVI stability](reports/mvi_stability.md) | Q2 | Stopping, zero-amplitude chart and angular-search mechanisms, with safeguards | Resolution of null-space ambiguity | IRLS strategies |
| 2 Nov 2026 | [IRLS strategies](reports/lagged_irls.md) | Q2 | Separates completion of an inner optimization from changes to its objective | Outer convergence or recovery | Outer budgets |
| 5 Nov 2026 | [Outer budgets and prior sensitivity](reports/mvi_outer_sensitivity.md) | Q2, Q3 | No frozen branch reaches the 0.001 stationarity ratio; CG 1600 changes the model by 0.008766 percent; beta 0.5 and 2 change it by 8.7 and 9.1 percent | Confidence limits or a bound on exact-solution error | Acceptance |
| 5 Nov 2026 | [Acceptance and downloaded data](reports/mvi_acceptance.md) | Q2, Q3 | Downloaded scalar cases pass prediction; three authored vector geometries pass 1, 1 and 0 of 6 body checks | Field geological recovery | Solver comparison |
| 6 Nov 2026 | Independent solver comparison (development archive) ([protocol](README.md)) | Q2 | On one captured problem, L-BFGS-B meets the stationarity criterion at accepted step 363; Core exhausts 80 steps; final objectives differ by 0.0000624 percent | A Core defect, or any geological effect of the solver choice | TW-MVI-TOP-1 |

## Status by question

| Question | Status | Where |
| --- | --- | --- |
| Q1 | Verified within the stated synthetic scope | Causal diagnosis; solver comparison directional checks |
| Q2 | Inner solves meet tolerance with larger budgets; Core outer stationarity is not demonstrated within its budgets | Outer budgets; solver comparison |
| Q3 | Row and null-space count, plus a top-depth evaluation on one synthetic prism outside the repository (TW-MVI-TOP-1, below) | Causal diagnosis; supervisor notes and TW-MVI-TOP-1 below |
| Q4 | Open; no independent subsurface control has been compared | [Coverage](README.md), R1 and R2; [permissions](README.md) |

## Supervisor review notes, 7 November 2026

These notes add context checked against the existing records. They do not
modify any record or published conclusion.

1. Null-space fraction context. The weighted operator has 400 rows, so its
   rank cannot exceed 400. An error vector without preferred direction would
   place on average 1 - 400/83,913 = 99.52 percent of its energy in the
   numerical null space. The support-oracle runs give 99.92 and 99.94 percent
   (records/mvi_causal_diagnosis_20261102.json, key subspace.cases). All 400
   singular values lie between 12,440 and 52,331 (key
   subspace.subspace.singular_values). The fraction shows that the remaining
   error is set by the prior rather than the data fit; it does not measure
   whether a specific geological feature is identifiable.
2. Body-level scores. The Core endpoint of the solver comparison passes all
   six body checks: location error 2.78 m, support Dice 0.864, direction error
   4.24 degrees, volume error 24.0 percent, contrast error 20.6 percent, and
   voxel error 49.68 percent against a 50 percent limit
   (../publication/solver_reference_results.json, key
   published.frozen_core.recovery). This is one familiar synthetic case.
3. Small-geometry failures. The three-geometry acceptance cases use an 8 by 8
   by 6 mesh of 100 m cells without padding, bodies of 8 cells and a 100 m
   location tolerance equal to one cell. The depth criterion uses the
   centroid, not the top. These failures cannot yet be attributed to missing
   information or to the MVI method.
4. Solver endpoint. The L-BFGS-B endpoint of the solver comparison was not
   scored and the distance between the two endpoint models was not reported.

## Separate evaluation: TW-MVI-TOP-1 (closed 7 November 2026)

TW-MVI-TOP-1 evaluated depth to the top of the magnetized body on synthetic
development cases: one uniform prism, 400 stations and 10 nT noise. It ran
outside the repository and is not part of paper replay 1.0 or the
solver-comparison protocol. Each stage had a frozen, hashed protocol, a
supervisor review before execution and a review of the results. Q4 was not
evaluated.

| Stage | Question | Result |
| --- | --- | --- |
| A0 | Q1, Q2 | Core and an independent SciPy reconstruction agree on the prediction and on the threshold top depth in every column where both models intersect. With 10 m cells the top metric is quantized by layer. |
| A1 | Q3, parametric | Profile of misfit against top depth for a prism fitted to data from a prism. Noise-free: delta chi-square of at most 4 between 18 and 28 m (true top 21.6 m). With noise: 19 to 31 m with free magnetization; 20 to 25 m with a magnitude prior derived from the truth. The deep side is weakly bounded by the thickness and magnetization trade-off. |
| A2 | Q2, Q3, voxels | Pilot with 5 m cells and two cases. A per-cell upper amplitude bound did not improve the top depth (gain 0 in both cases). Even with the true support the top was recovered about 7.5 m too deep. One case stopped through the SimPEG minimum-change IRLS criterion with misfit 3.7 percent above target. |
| A3 | Q2, Q3, voxels | Within the true support, changing only the sensitivity weights moved the amplitude centroid 6 to 7 m and the top hit rate from 1 to 100 percent, with weighted RMS misfit between 0.95 and 1.01. The predeclared rule left the result descriptive because one arm missed the strict target. |

Reading, within these cases only: the parametric model bounds the top depth,
while in voxel inversion the recovered top depth is set by the regularization
rather than by the data. Neither an amplitude bound nor the sensitivity
weights fixed it reliably without independent depth information. These results
do not authorize changing production weights or defaults, and the free
inversion without weights was not tested.

Two Core reporting findings were recorded without code changes. The stop label
adaptive_irls_stationary does not identify which criterion ended IRLS, and
target_reached uses the strict target while SimPEG may stop IRLS within a 10
percent misfit tolerance.

Protocols, run records and the synthesis (version 3, SHA256
271aa468fb7c3fb2ebb0bf450d3eacc6ef776acff5e49ee26d4804a1f84f4ae6) are kept
in the local session area of the development machine and are not part of this
repository.

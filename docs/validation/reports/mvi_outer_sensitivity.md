# Adaptive IRLS budgets and frozen-prior sensitivity

The 5 November 2026 campaign separates additional optimization from sensitivity
to regularization strength. It uses the same synthetic published-example
geometry, data, noise, initialization and six recovery criteria as the
[previous safeguarded run](lagged_irls.md). It does not validate field recovery
or establish a unique geological model.

Subsequent evidence: the [acceptance campaign](mvi_acceptance.md) and the
[independent solver comparison](../README.md).
The [MVI evidence map](../mvi_evidence_map.md) gives the full reading order.
This report and its results are unchanged.

The complete machine-readable record is
[mvi_outer_20261105.json](../records/mvi_outer_20261105.json).
The starting 40-cycle physical model reproduces the previous saved model
exactly, not merely within a display tolerance.

## Declared controls

The case contains 400 observations, 27,971 active cells and 83,913 vector
parameters. All initial controls use CG 800 and raw/scaled relative tolerances
of 0.0001. The adaptive extension doubles IRLS from 40 to 80 cycles and the
outer budget from 80 to 160 steps. This budget change was declared before its
result and was motivated by budget exhaustion, not by the truth score.

Three branches start from the identical final spherical model of the 40-cycle
run. They retain its effective regularization matrices, multipliers, norms and
thresholds. Only beta is multiplied by 0.5, 1 or 2. Every branch is retained;
none of these factors becomes a new production default. The weights and
starting model hashes are checked across branches, and each branch verifies
that its regularization hash remains unchanged.

Each frozen branch has 80 additional Newton steps. A branch can stop earlier
after a factor-1000 reduction of its projected gradient in its own fixed
initial Jacobi metric. This is a stated coordinate optimality diagnostic,
not a proof of global optimality, geological uniqueness or a physical
posterior uncertainty interval. The preconditioner is updated while the
regularization weights and the diagnostic metric remain fixed.

Truth enters only the output scoring. No support oracle, true direction,
true amplitude or known-body mask is supplied to these inversions.

## Recorded results

| Control | Data WRMS | Voxel error | Recovery checks | Required inner precision |
| --- | --- | --- | --- | --- |
| Adaptive IRLS 40 | 1.044635 | 50.008407% | 5 / 6 | All audited solves pass |
| Frozen weights, beta times 0.5 | 0.993980 | 47.671621% | 6 / 6 | All 80 solves pass |
| Frozen weights, unchanged beta | 1.030910 | 49.365777% | 6 / 6 | All 80 solves pass |
| Frozen weights, beta times 2 | 1.096149 | 51.900213% | 5 / 6 | All 80 solves pass |
| Adaptive IRLS 80 | 1.041135 | 49.831746% | 6 / 6 | 20 spherical solves miss at least one norm |
| Adaptive IRLS 80, CG 1600 | 1.041137 | 49.831944% | 6 / 6 | 14 spherical solves miss at least one norm |

The unchanged-beta continuation lowers its fixed objective by 0.1874 percent.
Its volume-weighted model changes by 2.5389 percent from the starting model,
and its voxel error decreases by 0.6426 percentage points. This demonstrates
unfinished optimization at the 40-cycle endpoint without changing beta or
the regularization weights.

The lower-beta and higher-beta solutions differ from the unchanged-beta
solution by 8.7157 and 9.1366 percent in the volume-weighted model norm.
Their voxel errors span 47.6716 to 51.9002 percent, with different data fits.
These are finite-budget sensitivity results; incomplete optimization can
still affect their differences. They are not confidence limits or evidence
for selecting beta from the known synthetic truth.

## Stationarity remains separate from recovery

| Frozen branch | Fixed objective reduction | Final projected gradient divided by its initial value | Stop |
| --- | --- | --- | --- |
| beta times 0.5 | 2.6801% | 0.046014 | Newton budget |
| unchanged beta | 0.1874% | 0.124421 | Newton budget |
| beta times 2 | 1.2749% | 0.019743 | Newton budget |

All three ratios remain above the predeclared 0.001 threshold. All 240 inner
solves meet both raw and Jacobi-scaled residual criteria, but no frozen branch
demonstrates the required stationarity reduction within its budget. Passing
the six recovery checks does not replace that missing convergence evidence.

The adaptive 80-cycle model changes by 1.6824 percent from adaptive 40 and
finishes after 83 spherical steps at its IRLS budget. It passes the frozen
recovery thresholds, but 20 of its 83 spherical solves fail the raw criterion
and 18 fail the scaled criterion; their union contains 20 solves. The last
solve also misses scaled precision. It therefore cannot establish a clean
precision-controlled comparison of outer convergence.

The separately declared CG-1600 control repeats the 80-cycle protocol after
these failures were observed. Inputs and criteria match, implementation
hashes are checked, and the recorded Cartesian warm-start trajectory is
identical. It changes the volume-weighted model by only 0.008766 percent
from CG 800. Its voxel error is 49.831944 percent, versus 49.831746 percent
with CG 800. It stops at the same 80-cycle IRLS budget after 83 spherical
steps. Fourteen raw and nine scaled spherical solves still miss tolerance;
their union is fourteen. Therefore, this budget increase has a very small
observed model effect but does not certify inner or outer convergence.
Recovery thresholds must not override those failed precision checks.

The substantial information ambiguity documented in the
[numerical row/null audit](mvi_causal_diagnosis.md) remains relevant. These
controls demonstrate budget and prior-strength effects; they do not assign
the entire remaining model error to one cause. In this comparison, doubling
CG is insufficient to explain or remove the remaining approximately
50 percent voxel error. This is an observed budget sensitivity, not a bound
on the error of an uncomputed exact nonlinear solution. More iterations cannot be
treated as additional observations or as a geological constraint.

## Reproduction and independent checks

Run scripts/benchmark_mvi_outer.py with --scale published and a new --output
directory outside the checkout. Its quick scale is a harness check with
smaller stated budgets, not the published-scale scientific result. The
protocol records all factors, budgets and implementation hashes. Generated
NPZ arrays, frozen histories and the original failed precision checks are
retained alongside the summary.

The precision follow-up uses scripts/benchmark_spherical_mvi.py with
--scale published, --variants core_spherical, --irls-update adaptive,
--cg-maxiter 1600, --outer-iterations 160 and --irls-iterations 80. Record
the residual-failure motivation through --budget-reason and use a fresh
--output directory. Both precision budgets remain in the archive.

The continuation harness is also checked against independent two-variable
diagonal ridge solutions for beta 0.5, 1 and 2. Fixed angle bounds make these
solutions analytic; the predicted amplitudes must equal observed / (1 + beta)
to relative tolerance 0.0000000001. These controls require initialized SDK
inverse problems, matching the actual continuation boundary. The 12-test
targeted suite also retains the existing lagged-IRLS and scaled-CG references.
No new dependency or production numerical default is introduced.

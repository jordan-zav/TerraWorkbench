# Spherical MVI stopping and coordinate safeguards

This follow-up to the [causal audit](mvi_causal_diagnosis.md) isolates three
numerical failure mechanisms. It does not resolve the large voxel model's
null-space ambiguity or certify geological recovery. All controls use synthetic
data; no private survey or acquisition metadata is included.

The subsequent [IRLS investigation](lagged_irls.md) adds numerical safeguards
and an opt-in frozen-objective controller. Results below retain the earlier
per-Newton implementation as historical evidence, rather than results of the
new safeguards.

## Demonstrated mechanisms

The SDK has a critical projected-gradient stopping threshold of 1000 times eps,
separate from tolG. With the SDK default eps of 0.00001, that threshold is 0.01.
Distance to an amplitude bound can make the projected-gradient norm smaller
than 0.01 even when data residuals are large. A one-prism start with amplitude
0.005 stopped without an optimization step. The shared Core optimizer now sets
the default eps no larger than tolG divided by 1000. Explicit internal eps
overrides remain available for controlled legacy experiments; the spherical
optimizer always enforces the requested gradient tolerance. Other stopping
criteria and finite budgets still apply.

At exactly zero amplitude, both angular derivative columns vanish. A radial
derivative can satisfy coordinate stationarity despite a nonzero Cartesian data
gradient: the current spherical chart cannot express a useful direction. Merely
tightening the tolerance does not fix this. The new directive considers rotations
of free exact-zero cells toward the negative physical data gradient. Magnetization
and predicted data are exactly unchanged. It accepts a rotation only when the
current fixed regularization cost does not increase beyond floating-point
roundoff and a useful negative radial derivative becomes available. Nonzero
amplitudes and excluded cells are untouched. A directional prior can reject the
rotation. No known model, support or direction enters this decision.

Near zero, angular Gauss-Newton steps can be enormous. The original Armijo search
with the production budget of 20 backtracks can fail to find a useful step. Only
after that search fails, Core retries with angular components limited to pi/4.
If clipping loses descent, a feasible Jacobi-gradient direction is used instead.
The same projected Armijo test, bounds and objective apply. Already accepted
Newton steps are unchanged. This is a targeted fallback, not a proof of global
convergence or a general trust-region algorithm.

The exact-zero directive runs after IRLS and before sensitivity and Jacobi
updates. In forward_only mode it uses a Cartesian Jacobian-transpose product
without retaining a complete sensitivity matrix. Cancellation remains checked.

These are Core engineering additions to the formulation in
[Fournier, Heagy and Oldenburg (2020)](https://doi.org/10.1190/geo2019-0244.1),
not claims of exact reproduction of that implementation. The SDK interfaces and
stopping definitions are in the
[SimPEG 0.25.0 optimizer](https://github.com/simpeg/simpeg/blob/v0.25.0/simpeg/optimization.py).

## Fixed-objective counterexamples

Run [benchmark_mvi_stability.py](../../../scripts/benchmark_mvi_stability.py) with
--output pointing to a new directory. The geometry is one known 100 m prism,
49 observations and three Cartesian parameters. This fully determined geometry
is deliberately distinct from free voxel recovery. Noise is zero, sigma is
0.1 nT and beta is 0.00000001. The prior is physical volume-weighted L2; its
spherical representation has amplitude smallness only. The independent solution
is an augmented-matrix SVD with the identical beta, data and prior.

Four starts are crossed with four methods: legacy SDK stopping, tighter stopping
alone, tighter stopping plus angular retry, and the complete guarded method.
The nonlinear budget is 50 iterations and 20 line-search backtracks. The frozen
pass criteria are data WRMS at most 1 and relative independent-solution error
at most 0.00001. Neither is a general geological-recovery criterion.

| Start | Legacy WRMS | Guarded WRMS | Guarded relative SVD error |
| --- | --- | --- | --- |
| Zero amplitude | 83.9755 | 2.70e-9 | 1.39e-15 |
| Amplitude 1e-12 | 83.9755 | 0.0001965 | 2.88e-6 |
| Opposite direction | 74.6049 | 2.87e-9 | 8.28e-16 |
| Regular nonzero | 2.71e-9 | 2.70e-9 | 1.50e-13 |

The regular-start legacy value is a comparison, not an expected failure.
For the opposite-direction case, tighter stopping alone still leaves WRMS
63.9471 at zero amplitude. For the tiny-amplitude case, tighter stopping alone
still exhausts all 20 backtracks without a useful step; the angular retry is
accepted and recovers the independent solution within the frozen criterion.

The [machine-readable archive](../records/public/mvi_stability_20261102.json) retains all
16 cases, including failures, runtime versions, source hashes and traces. The
dedicated MVI causal diagnostics workflow repeats the controls with current and
matched reference dependencies and retains full artifacts. Unit regressions
also exercise matrix-free chart recovery, excluded cells, fixed directional
priors, unchanged successful Newton steps and a bounded quadratic using the
shared optimizer.

Passing the independent-solution criterion does not imply exact nonlinear
stationarity. Some controls reach their iteration budget. Inspect the physical
Cartesian scaled optimality, history and stop reason separately; normalization
by an initially vanishing spherical gradient is particularly misleading.

## Large-case evidence and diagnostics

The published-geometry control retains 400 observations, 27,971 active cells and
the existing six geological recovery criteria. CG budget 200, IRLS budget 20,
outer budget 40 and one numerical thread are held fixed against the previous
controlled run. Truth is used for synthetic generation and scoring only.

| Controlled run | Data WRMS | Relative voxel error | Failed true CG checks | Recovery |
| --- | --- | --- | --- | --- |
| Before safeguards | 0.9503 | 150.17% | 14 / 31 | Failed |
| With safeguards | 1.0890 | 169.34% | 13 / 31 | Failed |

The synthetic input hashes match exactly, and the Cartesian initialization is
unchanged. Both runs stop after 20 IRLS cycles and 26 spherical iterations,
rather than reaching outer stationarity. The corrected run reorients 1,012
exact-zero cells at iteration 16; the angular-search retry is never needed.
The support Dice improves from 0.0969 to 0.2273 and direction error from
5.17 to 3.49 degrees, but both remain failed geological recoveries. The voxel
error and data fit worsen. This control therefore provides no evidence that
these safeguards solve the large recovery problem. Relative voxel error can
exceed 100 percent; it is not a fraction of incorrectly classified cells.

There are 31 audited CG solves including the five Cartesian initialization
steps. The final true CG relative residual is 0.001784, above the requested
0.0001, and target_chi of 1 is not reached. The benchmark's looser WRMS-at-most-2
data flag passes, but must not be confused with that target or model recovery.
The archived protocol's common directive_order describes the native reference
template; the Core diagnostic spherical_directive_order records its actual
additional chart directive.

Diagnostics now expose gradient_critical_tolerance, angular_step_safeguard_events,
angular_line_search_retries, zero_amplitude_chart_reorientations and
zero_amplitude_chart_events, in addition to true CG residual history and budget
flags. A successful final CG solve does not erase earlier failures or establish
outer convergence. Chart rotations preserve a fixed current objective, whereas
IRLS and sensitivity-prior updates can change that objective between iterations.

No geological prior or benchmark threshold was adjusted to improve recovery.
The historical [causal audit](mvi_causal_diagnosis.md) remains intact, including
its failed higher-budget controls. A numerical safeguard must be assessed
separately from the information content of the data and the chosen prior.

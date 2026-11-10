# Staged spherical magnetic vector inversion

The subsequent [causal audit](../../validation/reports/mvi_causal_diagnosis.md) separates mechanical
solver verification from null-space ambiguity and unresolved nonlinear fits.
Diagnostics now include true inactive-CG residuals, whole-history failure
counts, the IRLS iteration budget and its exhaustion flag. A completed run
does not certify numerical convergence or geological recovery.

The later [IRLS strategy controls](../../validation/reports/lagged_irls.md) retain adaptive per-Newton
updates by default. Set mvi_irls_update to lagged for experimental frozen inner
subproblems. Finite Newton budgets in that mode can finish before sparse
reweighting starts; inspect irls_stop_reason and the frozen-epoch diagnostics.

Set mvi_parameterization to spherical in run_potential_field_inversion,
run_inversion_workflow or an MVI CLI recipe. Cartesian MVI remains the default.
No QGIS or Qt is required. The method follows
[Fournier, Heagy and Oldenburg (2020)](https://doi.org/10.1190/geo2019-0244.1)
and the [SimPEG example](https://github.com/simpeg/simpeg/blob/v0.25.0/examples/03-magnetics/plot_inv_mag_MVI_Sparse_TreeMesh.py),
with the numerical differences described below; it does not claim bitwise
reproduction of that publication's field inversions.

The existing TMI projection kernel is retained; the model parameterization and
regularization change. The formulation does not separate induced and remanent
magnetization uniquely from magnetic data alone.

## Phases and parameters

The first phase uses separate L2 Cartesian component regularizers and a target twice target_chi.
mvi_cartesian_iterations bounds that initialization. Its beta and vector seed
the spherical phase, which has separate iterations and irls_iterations budgets.
History labels both phases; progress indices count completed initialization
steps. Diagnostics retain actual counts, budgets and Cartesian diagnostics.

Supply corrected TMI anomalies in nT and projected ENU metres. Reference and
starting models remain Cartesian effective susceptibility SI, in (n,3) or
component-major (3n,) layout. reference_in_smooth requires an explicit vector
reference and preserves reference interfaces. Regional subtraction remains a
separate data-space operation. Positive cell_weights retain their prior meaning.

regularization_norms contains amplitude smallness and x/y/z gradient norms.
mvi_angle_norms contains x/y/z spatial gradient norms of both angles. Angular
smallness is zero: no preferred absolute direction is silently supplied.
Defaults remain L2. Sparse norms require positive IRLS budget, but IRLS starts
only after its data-fit condition; requesting sparsity does not prove it ran.
regularization_weights supplies amplitude alpha_s/x/y/z and corresponding
spatial angle coefficients. Adaptive angle scaling and sensitivity-prior weights
update per Newton step by default, or at subproblem boundaries in lagged mode.
mvi_sensitivity_weights defaults to component_approximation, using the native
SDK component-diagonal rule on the exact current map. The optional mapped_exact statistic uses complete
mapped column energies for the prior too. That changes the inverse problem;
it is an experimental prior choice, not a solver-precision switch. Both modes
use the complete mapped diagonal in the numerical preconditioner.

mvi_amplitude_max is a nonnegative scalar or one value per active cell, with
at least one positive entry. It bounds vector magnitude in effective SI.
Zero caps impose exactly zero magnetization; undefined angles remain free to
continue the regularized field. Cartesian lower/upper bounds are rejected in
this mode. Supplied references and starts must respect magnitude caps. Projection
of the computed Cartesian initialization is counted explicitly.

An explicit benchmark recipe is shown below. Its finite budgets do not guarantee
convergence; inspect CG residual, actual IRLS count, data fit and recovery.
The numerical_passed benchmark flag tests the final inner solve only; inspect
the retained iteration history for earlier CG budget exhaustion.
That historical flag uses the raw residual; the spherical solver additionally
requires the Jacobi-scaled residual. Read cg_scaled_tolerance_met as well.

    {
      "mvi_parameterization": "spherical",
      "mvi_cartesian_iterations": 20,
      "iterations": 40,
      "regularization_norms": [0, 1, 1, 1],
      "mvi_angle_norms": [1, 1, 1],
      "irls_iterations": 20,
      "mvi_amplitude_max": 10,
      "cg_maxiter": 200,
      "cg_rtol": 0.0001
    }

## Conventions and safeguards

Internal ordering is amplitude, elevation from horizontal and azimuth from East
counterclockwise toward North. Angles use radians; elevation is bounded to
minus/plus pi/2 and azimuth is periodic. These differ from geographic inclination
positive down and declination clockwise from North. Public NPZ/VTK models remain
Cartesian ENU with positive-up z; existing SI and physical A/m exports are retained.

The map preserves exact zero amplitude without an artificial epsilon. Its
analytical derivative and periodic regularization are checked by finite differences.
For physical sensitivity G and map derivative D, data Gauss-Newton diagonal
diag(D.T G.T Wd**2 G D) includes within-cell component cross products. Retaining
the complete 3-by-3 component Gram avoids substituting the physical diagonal
alone. This is the exact Gauss-Newton diagonal, not all second derivatives of
the nonlinear objective. Near-zero preconditioner entries use a recorded machine
precision floor without adding an objective prior.

The adaptive event order is angle scaling, canonical projection, IRLS, exact-zero chart
recovery, sensitivity weights and then Jacobi. Chart recovery and a failed-search
angular retry are Core safeguards beyond the reference implementation; see the
[stability controls](../../validation/reports/mvi_stability.md). The preconditioner sees the current
beta and prior weights. Numerical stability and recovery still require checking;
ordering alone does not resolve nonuniqueness or unstable prior choices.
During a frozen inner solve, only canonical projection, non-increasing exact-zero
chart recovery, the numerical Jacobi preconditioner and tracing update per step.

RAM, disk and matrix_free modes are supported. Matrix-free storage retains a
3-by-3 Gram (72 float64 bytes per cell) plus bounded temporary receiver blocks;
it does not retain the full data-by-model sensitivity matrix. The full-matrix
storage limit is not a total process-memory limit. Disk caches use a namespace
bound to inputs, geometry, field and kernel versions, preserving unrelated files.
Manifests hash the spherical module and record conventions, phase diagnostics
and precision. Cancellation retains a failed manifest without a completed model.

The [benchmark](../../../scripts/benchmark_spherical_mvi.py) compares shared Cartesian
initialization, native SDK spherical inversion, Core spherical inversion and a
truth-labelled support control. Data use independently converged dipole-volume
quadrature, with the existing six frozen recovery criteria and mesh adjacency.
Fit, inner precision and model recovery are assessed separately. A successful
run or coherent angle does not certify voxel geometry or geological truth;
nonlinear IRLS results are not fixed linear-Gaussian posteriors.

## Reproducible evidence

The [archived campaign](../../validation/records/spherical_mvi_20261029.json) retains the
authored quick case, published-example geometry, all four final variants and
development controls, including unsuccessful and interrupted runs. These are
synthetic benchmarks, not independent field-data validation. Input and source
hashes identify each run; development runs explicitly record a dirty checkout.
Full model arrays and traces are retained by the Spherical MVI validation workflow.

The grouped Cartesian warm start and exact-mapped prior experiments remain
visible in that archive. Componentwise L2 initialization follows the spherical
reference example; changing sensitivity statistics changes regularization and
can alter geometry even when the data remain well fitted. Comparing those
experiments does not isolate a unique cause for every recovered-model difference.

## Recorded results (29 October 2026)

Published-example geometry: 400 observations, 27,971 active cells. Only the
support oracle uses the true region in fitting. Model error is relative voxel
L2 error; angle is the recovered-body direction error under the frozen scoring
rule. Final CG flags do not summarize all previous inner solves.

| Variant | Data WRMS | Model error | Direction error | Final CG tolerance | Recovery |
| --- | --- | --- | --- | --- | --- |
| cartesian_initialization | 1.106 | 102.4% | 11.63 deg | True | False |
| native_spherical | 0.918 | 62.2% | 2.91 deg | False | False |
| core_spherical | 0.848 | 82.1% | 3.32 deg | True | False |
| core_spherical_support_oracle | 1.150 | 95.1% | 4.17 deg | False | False |

The support oracle uses the true region in fitting and is not free recovery.
These results do not close validation of voxel geometry. Read the archived
controls before interpreting better data fit or coherent directions as better
geological recovery.

## Linux comparison with current dependencies

The [Linux workflow](https://github.com/jordan-zav/TerraWorkbench/actions/runs/40988009776) completed all eight cases with the same inputs and protocol.
All recovery verdicts agree, but this is not strict numerical reproduction.
The free published Core model differs by 28.1 percent in relative L2 from the
Windows model; its model error is 81.1 percent and data WRMS is 0.630. The
Cartesian initialization differs by only 5.4e-8 relative L2.

Windows used NumPy 1.26.4, SciPy 1.17.0 and SimPEG 0.25.0; Linux used
NumPy 2.4.6, SciPy 1.17.1 and SimPEG 0.25.2. Operating system, libraries and
nonlinear IRLS trajectories are confounded. The workflow dependency_profile
option windows_reference fixes those six recorded numerical package versions
for a separate control. This does not fix BLAS, compiler or Python builds.
Do not attribute the discrepancy to one package without that comparison, or
interpret unchanged pass/fail flags as stability of every recovered voxel.

## Matched dependency control

The [matched-version workflow](https://github.com/jordan-zav/TerraWorkbench/actions/runs/40989442953) records the same six numerical package versions as Windows.
Inputs and scientific controls agree; the Linux run includes all four quick
variants and the published free Core variant.

The published free model differs by 46.31% relative L2 from Windows. Its voxel error is 80.5%, data WRMS 0.783, final CG tolerance True and recovery False.

Matching these packages is a separate control, not a guarantee of identical
BLAS, compilers, Python builds or nonlinear solver trajectories. It does not
identify an individual dependency as the cause, or establish recovered geometry
as correct. Both the current-profile and matched-profile Linux results remain
in the archive with their actual commits, versions and source hashes.

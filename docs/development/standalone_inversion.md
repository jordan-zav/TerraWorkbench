# Standalone potential-field inversion

Cartesian MVI remains the default. The optional [staged spherical formulation](../reference/methods/spherical_mvi.md)
refines amplitude and periodic angles while retaining Cartesian public outputs.

The optional inversion engine is part of terraworkbench_core.inversion. It imports no QGIS or Qt. Historical inversion_core imports and existing QGIS Processing callers forward to this implementation.

Use Python 3.11 or newer and the inversion extra declared in pyproject.toml: SimPEG 0.25, discretize 0.12 and choclo 0.3. Importing the module does not load these optional dependencies. Existing notebook environments and installed packages are not modified.

The [MVI and other-method campaign](../validation/reports/inversion_methods_validation.md) separates
independent prediction checks from voxel-direction recovery and fixed-geometry
electrical/EM/SP fits. In its MVI examples, a good anomaly fit still leaves
integrated direction errors of about 6–39 degrees. Effective vector parameters
are SI susceptibilities rather than magnetization directly in A/m.
The subsequent [dispersive-IP and constrained-MVI extension](../reference/methods/dispersive_ip_mvi.md)
adds spectral/transient inversions and optional vector references, IRLS and
component smoothness. Its improved constrained examples require an explicit
support assumption; they do not close unconstrained voxel-direction recovery.

## Inputs and scientific controls

run_potential_field_inversion accepts projected XYZ receiver coordinates in metres, corrected observations and positive standard deviations. The z coordinate increases upwards. Gravity uses gz in mGal and recovers density contrast in g/cm3. Its gravity_component defaults to up, preserving the historical SimPEG convention. Set down explicitly for positive-down observations: input data, returned predictions, regional prediction and exported residuals all follow the selected convention. This changes the observation component, not the coordinate z axis. Magnetic observations are TMI in nT and scalar susceptibility is SI. MVI uses the SimPEG Cartesian vector formulation; a nondefault gravity component is rejected for magnetic-only inversions.

Automatic TensorMesh or TreeMesh construction accepts topography, cell sizes, depth and padding. To preserve an existing discretization, pass mesh and its boolean active_cells mask. The mask can exclude a prescribed nonmagnetic cover. This is an explicit modeling assumption. Without topography the historical flat-surface behavior remains; it does not constitute measured cover.

Scalar inversion supports a constant reference_value or a reference_model with one value per active cell, plus a separate starting_model. Norms are supplied as four values in regularization_norms: smallness, x, y and z gradients. Any norm below two requires positive irls_iterations. These controls accept a supplied regional reference; they do not manufacture a missing published reference. All references and starting models must be finite and inside the bounds.

Beta cooling and target_chi are explicit. Sparse inversion lets UpdateIRLS manage its own cooling and stopping; a separate TargetMisfit does not terminate the run as soon as the initial L2 fit reaches the target. The diagnostics record the actual number of IRLS cycles and the achieved weighted RMS. Completing execution and reaching the requested data misfit are recorded separately.

regularization_weights supplies the four alpha coefficients; when omitted, SimPEG defaults are retained. reference_in_smooth controls whether smoothness penalizes the difference from the reference or the recovered model itself. beta0_ratio and cg_maxiter expose the initial tradeoff and inner solver iteration budget. These are scientific recipe choices and should be recorded explicitly when comparing different runs.

Individual gravity, susceptibility and MVI inversions also accept optimizer_tol_f,
optimizer_tol_x and optimizer_tol_g. Defaults preserve the existing values
0.000001, 0.00000001 and 0.000001. These control outer objective, model-change
and gradient stopping; cg_rtol separately controls the inner linear solve.
beta_seed explicitly controls the initial eigenvalue-estimation seed, retaining
the previous default of zero. Diagnostics and workflow provenance retain these
settings. They do not establish geological convergence or reproduce a different
SimPEG release's IRLS implementation merely by matching numerical settings.

Scalar inversions can select an explicit cell_difference regularization convention
for historical recipes; physical_gradient remains the default. See the
[definitions and independent operator references](../reference/methods/regularization_conventions.md).

For historical recipe comparisons, supply all four alpha coefficients explicitly.
Current SimPEG defaults scale smoothness with the regularization mesh base
length; they are not necessarily four unit coefficients. The active-cell mask,
interpolation method for its surface, reference model, initial model and the
history of regional subtraction must also match. Comparing raw objective values
across releases without checking their normalization can introduce a factor-of-two
misinterpretation; compare physical residuals and noise-normalized RMS as well.

Both scalar/vector and joint engines use ProjectedGNCG with an explicitly initialized Jacobi preconditioner. Scalar/vector uses UpdatePreconditioner; joint inversion uses the full weighted Hessian diagonal, preserving paired betas, coupling and the L2 data Hessian's factor two. It refreshes after each paired-beta update. BaseInvProblem is constructed with init_bfgs=False, the supported SimPEG 0.25 option that avoids factoring the initial BFGS regularization Hessian. The optimizer refuses a search direction without its explicit preconditioner. No solver exception is swallowed and no installed SimPEG source is patched.

Sensitivity precision defaults to float64 for the scalar/vector engine and may explicitly be float32. max_sensitivity_bytes checks the dense matrix estimate before simulation allocation. Disk storage via sensitivity_path reduces RAM demand but does not eliminate matrix size or I/O costs. This limit is a matrix estimate, not a process memory ceiling.

When every initial model value is on a bound, a Jacobi-preconditioned feasible descent step releases variables whose gradient points inward. This avoids the zero-step stall in the SimPEG 0.25 projected-CG active-set scaling. The line search and projection remain active, with no BFGS fallback or library patch. Diagnostics record bound_start_restarts and iteration_limit_reached. Reaching an iteration limit is not convergence.

Joint cross-gradient inversion accepts the same explicit gravity component, uses a fixed beta eigenvalue seed and reports per-dataset weighted RMS, iteration-limit status and whether both weighted RMS values are at most one. This last diagnostic is a data-fit criterion, not a proof of joint stationarity, structural agreement or geological correctness. The QGIS adapters retain their historical positive-up input convention.

Joint inversion also accepts a supplied mesh with its boolean active_cells mask,
scalar or per-active-cell starting_density and starting_susceptibility, explicit
sensitivity_dtype and max_sensitivity_bytes. Defaults preserve the historical
zero-density, 0.0001-susceptibility start and float32 sensitivity storage. The
byte guard estimates both dense physical matrices, not total solver memory.
Supplied geometry is retained exactly; it is not rebuilt from cell_xy or depth.

Joint cg_maxiter and cg_rtol now expose the inner solve budget/tolerance, keeping
the historical defaults of 100 and 0.001. Scalar inversion also exposes cg_rtol,
with its historical 0.001 default. History and diagnostics record cg_iterations,
cg_relative_residual and cg_tolerance_met independently of weighted data RMS.
Undefined inner residuals become null rather than invalid JSON. A bound-gradient
restart is not a successfully solved CG system. No data-fit flag certifies
gradient stationarity or geological recovery.

Joint histories also report relative_model_change, data_target_tolerance_met
and outer_convergence_met. Outer convergence requires both squared data-misfit
ratios within ten percent of one, relative model change at most 0.000001 and
the inner CG tolerance. Reaching an iteration limit does not certify these
conditions. A ratio in that stopping band differs from the stricter weighted
RMS at most one flag. The public strong-coupling case meets both inner and
outer criteria in 58 iterations with the tested Gauss-Newton recipe; see the
convergence report for its explicit budgets and remaining scientific limits.

cross_gradient_hessian defaults to gauss_newton. This forms twice the normal
matrix of the existing cross-gradient face-pair residual Jacobian, preserving
the objective and first derivative. A sparse matrix is cached for each distinct
model, including safe invalidation after in-place changes. The simpeg mode
retains the earlier stabilized Hessian approximation for recipe reproduction.
The default iteration/CG budgets are unchanged and are not a promise that an
arbitrary dataset converges in ten iterations. The tested large recipe uses
float64 sensitivities, cg_maxiter 600, cg_rtol 0.00001 and an outer budget 60.
Histories retain next_paired_betas for provenance of the adaptive tradeoffs.

Optional reference_density and reference_susceptibility decouple joint starting
models from the smallness prior. If a reference is omitted, that property's
starting values remain its historical implicit prior. Supply both references
when varying starts to avoid confounding the two effects. Each accepts a finite
scalar or an active-cell vector in the physical property units.

## Complete execution and artifacts

For command-line use, run python -m terraworkbench_core.inversion with --kind susceptibility, --input survey.npz, --recipe recipe.json and --output a-new-directory. The NPZ contains xyz, observed and standard_deviation; it can also contain topography, regional_prediction, reference_model, starting_model and active_cells. The JSON supplies cell_xy, cell_z, depth and the other numerical options described above. --mesh-ubc accepts an existing native octree; pair it with active_cells in the NPZ. Input arrays are loaded without pickle.

run_inversion_workflow takes the same kind, coordinates, observations, uncertainties and numerical options, plus a new output_directory. It executes inversion, calculates predictions and residuals, and writes model.npz, model.vtk, data.csv and run.json. The VTK writer supports tensor and octree cells without an additional VTK installation. Existing output directories are refused.

An optional regional_prediction is subtracted from observations before inversion; predictions of the total field are restored for the residual table. This is a data-space background, distinct from reference_model. If the entire regional field is removed, the local result is a contrast relative to it; choose bounds and a prior consistent with that definition. Do not automatically subtract a full regional field and simultaneously treat the local solution as an absolute model.

The NPZ retains geometry, active mask, recovered model, observations, uncertainties, background, predictions, expanded fields and numerical array options including supplied references and topography. run.json records package versions, the engine source hash, option descriptions, iteration history, fit diagnostics and execution state. Failed or canceled executions are marked failed and are never marked complete. Cancellation is checked before preparation and between iterations, not inside a running native kernel.

This validates the supported modern engine, not exact equivalence with historical SimPEG 0.15 notebooks or a particular published target. Reproducing a publication still requires its original observations, errors, mesh, field, regional treatment and regularization recipe.

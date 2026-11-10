# 3D inversion: storage, artifacts and scalable linear diagnostics

Expansion implemented 28 October 2026. Numerical code remains independent of
QGIS and Qt. The inversion extra uses SimPEG 0.25.x, Discretize and Choclo;
the new fixed linear diagnostics need only NumPy/SciPy. No installed dependency
was modified. Source/runtime hashes and method assumptions belong to each run.

The known-prism property fits use the existing optional prisms extra and its
Harmonica forward kernels. They reuse the shared column-scaled, noise-whitened
Gaussian calibration solver rather than adding another least-squares engine.

## Potential-field sensitivity storage

Both run_potential_field_inversion and run_joint_cross_gradient_inversion accept
sensitivity_mode: auto, ram, disk or matrix_free. Auto preserves the historical
selection from sensitivity_path. Disk requires a path. Matrix-free requires no
storage path and uses SimPEG/Choclo forward-only operators, including transpose
products and accumulated sensitivity diagonals, for gravity, scalar
susceptibility and Cartesian MVI. It trades repeated kernel work for avoiding
the full observation-by-model sensitivity allocation; it is not a GPU or
universal speed improvement.

The theoretical dense sensitivity size remains in sensitivity_bytes.
stored_sensitivity_bytes is zero in matrix-free mode. This does not imply
zero RAM: mesh, model, regularization, optimizer and operator work arrays still
exist. max_sensitivity_bytes bounds allocated sensitivity storage and does not
cap all process memory or arithmetic. sensitivity_dtype controls the stored
matrix; no float32-equivalent operator trajectory is promised.
The default storage budget is 512 MiB per inversion, including both matrices
for a joint solve. An explicit larger budget or None overrides this storage
guard. Matrix-free mode avoids the dense allocation instead of bypassing the
guard by silently allocating it elsewhere.
Masked inputs and complex values presented as real potential-field data are
rejected through the shared array contract, including workflow backgrounds,
active masks and model/reference arrays. Missing values must be handled before
inversion; no missing-data mask is silently discarded.

max_mesh_cells limits all mesh cells separately from max_cells, which limits
active cells. Tensor mesh estimates fail before constructing an oversized mesh;
octrees are checked after refinement and before topographic activation. Supplied
meshes must be 3D and within the total-cell budget. This is not a hard native
allocator limit during octree refinement.

The individual inversion Jacobi preconditioner now uses the diagonal of the
actual L2 Hessian, including the data term's factor two and the current beta and
regularization weights. The joint solver already had its weighted correction.
This can change individual iteration trajectories without changing their
objective. Tests check the diagonal against an explicitly assembled Hessian.
Cancellation is checked within optimizer Hessian products as well as iteration
boundaries. A running compiled kernel cannot be interrupted internally.
Zero free-variable gradient now releases inward-pointing bound variables via
the Jacobi step; a stationary interior reports zero relative CG residual
instead of the native zero-divided-by-zero diagnostic.

## Complete standalone joint workflow

Import run_joint_inversion_workflow from
terraworkbench_core.inversion_workflows. Supply the six gravity/magnetic XYZ,
data and standard-deviation arrays, output_directory and ordinary joint solver
options such as mesh, active_cells, cell_xy, cell_z and depth.

The workflow preserves model.npz, model.vtk, gravity.csv, magnetics.csv and
run.json in a new output directory. Existing directories are rejected. Each
CSV includes observed data, noise, regional background, residual prediction,
total prediction and residual. Separate regional_gravity and regional_magnetics
are subtracted in data space. They are not property reference models.

Coordinates are projected metres with upward elevations; gravity uses the
declared up/down convention in mGal, density contrast is g/cm3, TMI is nT and
susceptibility is SI. The manifest records typed input hashes, explicit mesh
cell geometry, numerical options, source hashes and library versions. Callback
state, external process state and mesh topology are excluded from the hash and
declared as such. Cell geometry/active masks are retained with results.

The manifest's state describes artifact completion separately from its
numerical_status. A finite execution that misses convergence can complete its
artifacts with numerical_status set to not_converged. Optional
require_convergence rejects that run and preserves artifacts and diagnostics
with a failed manifest. Joint convergence still requires stable model change,
both statistical data targets and the final inner CG tolerance. A deliberately
short run is never relabelled converged.

The individual workflow also records typed input/mesh hashes and numerical
status. Optional require_data_target rejects a fit above its declared target;
this gate checks data fit, not outer stationarity, inner convergence or geological
uniqueness. Manifest writes use a staged file replacement. Cancellation is
checked before completion; compression/VTK output itself remains synchronous.

## MVI export units

The [optional spherical solver](../../reference/methods/spherical_mvi.md) uses the same Cartesian output
and physical-unit contracts. Its internal angles are not exported as susceptibility
components, and its nonlinear IRLS result does not inherit linear-Gaussian uncertainty.

Scalar and joint gravity results additionally export density_contrast_g_cm3
and density_contrast_kg_m3; susceptibility results export susceptibility_si.
Historical gravity and density cell fields remain g/cm3 aliases, not mGal
anomalies. Unit maps in both manifests make the distinction explicit.

Cartesian MVI parameters are effective susceptibility vectors in SI, stored
component first with upward z. Canonical exported fields now explicitly name
effective_susceptibility_x_si, effective_susceptibility_y_si,
effective_susceptibility_z_si and effective_susceptibility_amplitude_si.
Physical magnetization fields use magnetization_x_a_m, magnetization_y_a_m,
magnetization_z_a_m and magnetization_amplitude_a_m, multiplying the effective
vector by H0 = B0/mu0 with B0 converted from nT to tesla.

Historical unqualified magnetization_* fields retain their previous SI values
for compatibility. They are aliases, not physical A/m values. The manifest
records this distinction and the units of every exported MVI model field.
Use canonical unit-qualified names in new workflows.

## Known-geometry 3D property inversions

Two additional operations estimate signed physical properties while keeping
prism boundaries fixed: gravity.prism_density_fit returns density contrast in
kg/m3, and magnetic.prism_magnetization_fit returns physical ENU magnetization
in A/m. These are not free-voxel inversions or conversions to susceptibility.
Both return full Cartesian parameter covariance, residuals, conditioning and
explicit parameter order. Absolute errors are independent and known; geometry,
calibration and inducing-direction uncertainty are excluded. Rank-deficient
bodies are rejected. Optional background offsets remain explicit.

The magnetic fit accepts ENU vector data or small-anomaly total-field projection
along supplied inducing inclination/declination. It does not invert the exact
vector norm. Observations must be outside the supplied prisms. Priors about
body shape make this a different inverse problem from unconstrained voxel MVI;
good known-body recovery cannot certify the voxel result. Coordinates/prism
bounds are metres. Gravity up/down convention is explicit, with Harmonica's
downward g_z converted accordingly.

## Scalable fixed linear resolution

The existing dense linear_resolution remains useful for small audit cases.
The new matrix_free_resolution module offers two additional registered APIs:

| Operation | Output and scope |
| --- | --- |
| inversion.stochastic_resolution | Estimates of posterior variance diagonal, resolution diagonal and effective parameter count, with probing standard errors and checked CG histories. |
| inversion.point_spread | Selected covariance and resolution columns in the supplied parameter coordinates, with checked precision solves. |

The advanced forms and process-specific cautions are authored in EN/ES/PT.
The operation registry accepts numeric matrices with its usual typed input
provenance. Direct Python calls also accept SciPy sparse matrices and
LinearOperators with correct forward/adjoint products. Operator callbacks are
not serializable recipe inputs; callers must preserve their own operator/model
provenance. No dense model-square precision, inverse or resolution is created.

For supplied G, independent positive data errors and prior operator L:

    H = G.T Wd^2 G + beta L.T L
    C = inverse(H)
    R = C G.T Wd^2 G

Beta must be positive and the combined precision must be positive definite.
An adjoint consistency probe catches common adapter mistakes; it is not a proof
of rank or physical correctness. An optional positive precision diagonal supplies
Jacobi preconditioning. All CG solves are checked against the true residual;
exhausted iteration/application budgets, invalid products and cancellation fail
the operation rather than publishing a successful estimate.

Rademacher probing estimates each diagonal as the mean of elementwise z times
the relevant operator applied to z. Returned standard errors describe Monte
Carlo probing variability only, excluding finite-solve bias. Trace variability
is measured from each full trace sample, preserving cross-component covariance.
Negative variance estimates remain flagged; corresponding estimated standard
deviations are NaN instead of silently clipped. Resolution estimates are not
clipped. More probes may be needed. Basis mode checks exact diagonals up to CG
tolerance for at most 1024 parameters; it is an audit mode rather than a large
regional default.

Selected point-spread outputs are columns R[:,j], not averaging-kernel rows.
Their spatial interpretation depends on the caller's model-to-cell mapping and
parameter units. Neither this nor reference-model DOI supplies a universal
geological depth cutoff. Fixed linear Gaussian covariance is not a posterior
for bounded voxel inversion, learned beta/IRLS weights, nonlinear conductivity
or cross-gradient coupling. Model inadequacy and uncertain geometry are excluded.
Logical element and operator-application budgets are explicit, not hard process
memory guarantees.

## Reproducible campaign

scripts/benchmark_inversion3d_extensions.py accepts --cache, --output and an
optional --section. Outputs must be new. It uses the existing pinned
[public SimPEG sources](public_inversion_benchmark.md) without executing
downloaded Python code or redistributing raw inputs.

- Independent Gauss-Legendre volume integration generates gravity and TMI for
  an authored buried cube. Tests vary noise and MVI direction and compare
  withheld predictions with separate Geoana analytic prism kernels. Cell-model
  and integrated-vector errors remain reported independently of data RMS.
- Known-cube density and twelve vector-property controls use the Core's new
  fixed-geometry fits with independent volume-integral observations, varying
  magnetization direction and noise. Noiseless recovery is checked; noisy
  direction errors and Cartesian covariance remain available.
- Short stored/matrix-free trajectories compare the same objective and inputs
  for gravity, susceptibility and MVI. They validate operator/storage integration,
  not outer convergence or geological uniqueness.
- The exact public joint mesh and inputs exercise standalone artifacts with a
  deliberately small iteration budget. Expected nonconvergence remains visible;
  the prior [58-iteration convergence record](inversion_convergence_resolution.md)
  remains separate and is not overwritten by this short integration case.
- Eight declared spatial zones of that public mesh test linear diagnostics
  against a dense reference and report stochastic sampling errors. This is an
  explicit reduced parameterization, not a 47,860-cell dense voxel posterior.
- A 100,000-parameter diagonal operator has an analytic covariance and no dense
  sensitivity/covariance allocation. It is an operator stress test, not a
  regional geophysical speed benchmark.

The manual public inversion workflow runs this campaign and the broader existing
MVI/electrical/FDEM/SP validation. Versioned evidence belongs in
[benchmark records](../records/README.md). Historical results remain linked to
their own source revisions. Regression tests also cover strict rejection,
input-hash changes, cancellation inside CG, units and mesh allocation guards.

The [archived extension report](../records/inversion3d_extensions_20261028.json)
and [48 method controls](../records/inversion3d_methods_20261028.json) passed
in clean-source Linux CI at b70d40460255c550d79b4fc14df144ee495c409b.
The eight free-voxel examples have training WRMS 0.645 to 0.977 and withheld
WRMS 0.458 to 0.981, while cell-model relative errors remain 85.5 to 96.6
percent. The exact-known-cube controls recover noiseless magnetization to
relative error below 0.000000001 and have maximum noisy directional error
0.475 degrees under their prescribed experiment. Those geometry-conditioned
results do not transfer to free voxel MVI. The large diagonal control matches
its analytic variance at reported numerical precision; it is not a regional
runtime comparison.

Local validation also exercised 118 advanced forms in all three languages and
QGIS 3.44.12 potential-field/IRLS/octree joint workflows with SimPEG 0.25.2.
The independent wheel was tested outside the checkout and the plugin ZIP was
validated. The numerical source revision's three
[quality gates](https://github.com/jordan-zav/TerraWorkbench/actions/runs/40795852998)
passed separately from the manual public campaign.

## Remaining scope

This expansion improves existing 3D potential-field inversions and supplies
general fixed-linear diagnostics. Existing 3D DC/IP, FDEM and SP adapters retain
their declared mesh/zone/Jacobian budgets; the parameterized EM methods do not
become regional voxel solvers through this change. A general 3D transient-EM
voxel inverse, calibrated nonlinear constrained posterior, full tensor-data
inverse and universally validated geological recovery are not established.
Field validation and appropriate priors remain necessary.

## Primary sources

- [SimPEG 0.25 magnetic integral simulation and operator contracts](https://docs.simpeg.xyz/v0.25.0/content/api/generated/simpeg.potential_fields.magnetics.Simulation3DIntegral.html).
- [SciPy conjugate gradient residual and positive-definiteness contract](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.cg.html).
- [Dharangutte and Musco, Hutchinson diagonal estimator analysis](https://doi.org/10.48550/arXiv.2208.03268).
- [Harmonica prism magnetization units and ENU components](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_magnetic.html).
- [Harmonica density and gravity vertical convention](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html).

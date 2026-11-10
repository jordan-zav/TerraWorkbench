# Archived public-data validation evidence

Campaign date: 28 October 2026. Numeric records contain parameters, source and
dataset hashes, dependency versions and measured diagnostics. Downloaded survey
and spectrum bytes are not redistributed here. Local workstation/cache locations
are excluded from these records.

| Record | Evidence and scope |
| --- | --- |
| [Processing record](public/public_processing_20261028.json) | Seven public inputs; gravity, magnetic transforms, interpolation, terrain/Airy, channel storage, radiometric products and spectra. Linux CI source revision is recorded. |
| [Inversion record](public_inversion_20261028.json) | Public synthetic SimPEG recipe replay plus a separate from-start Gauss-Newton convergence run on Windows. Full histories and model-error diagnostics are retained. |
| [2D extension record](2d_extensions_20261028.json) | Clean-source Linux CI: Lightning Creek kriging against PyKrige, measured PSI spectra against independent least squares, and analytic polygon gravity/density recovery. Parameters, signed estimates, misfit and limits are retained. |
| [3D extension record](inversion3d_extensions_20261028.json) | Fifteen cases: independent volume fields, stored/operator inversion equivalence, known-prism properties, exact public joint artifacts, reduced linear resolution and a 100,000-parameter operator control. |
| [3D method controls](inversion3d_methods_20261028.json) | Forty-eight MVI, known-body, electrical/IP, FDEM and SP controls, including a deliberately under-iterated MVI case. Completion is separate from convergence and model recovery. |

Read the [processing methods and limitations](../reports/public_processing_benchmark.md),
[inversion protocol](../reports/public_inversion_benchmark.md) and
[convergence analysis](../reports/inversion_convergence_resolution.md) before interpreting
the metrics. Optimizer agreement, convergence and unique geological recovery
are separate claims. Timings and sampled memory are observations of these
executions, not a hardware-controlled performance comparison.

The extension protocol is in [2D method contracts](../reports/2d_extensions.md).
Its [successful CI run](https://github.com/jordan-zav/TerraWorkbench/actions/runs/40718409619)
also reran all seven existing public processing cases. The archived extension
record identifies source revision f2674ead2f5db2ca90f391e80a5807a543906fd9.
Laboratory spectral template agreement does not establish an airborne radon
calibration: negative components and elevated chi squared remain warnings
against treating solver agreement as validated physical reconstruction.

The [3D campaign](https://github.com/jordan-zav/TerraWorkbench/actions/runs/40795853002)
passed at source b70d40460255c550d79b4fc14df144ee495c409b. Read its
[contracts and limits](../reports/inversion3d_extensions.md): free-voxel model errors
remain 85.5 to 96.6 percent in these examples despite satisfactory data fits.
Known-body controls condition on exact geometry and are a different inverse
problem. No raw public archive, private data or local cache path is included.

The [voxel recovery record](voxel_recovery_20261028.json) retains all 153 cases, including failures, from [clean-source CI](https://github.com/jordan-zav/TerraWorkbench/actions/runs/40807523516). Read the [frozen recovery protocol](../reports/voxel_recovery_validation.md); completion does not certify geological recovery.

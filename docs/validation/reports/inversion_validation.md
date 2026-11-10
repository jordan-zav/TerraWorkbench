# Synthetic inversion campaign

Campaign on 26 October 2026. All observations are synthetic; no private survey
or acquisition settings are used. Reproduce with the repository script
scripts/validate_inversion_campaign.py, an installed inversion extra and a new
output directory. Its default campaign runs nine scalar/vector cases and three
joint cases. The joint-only option repeats only the joint experiments.

## Independent observations and holdout

A 200 m cube centred at elevation -200 m has density contrast 0.4 g/cm3 or
effective susceptibility 0.025 SI. Direct Gauss-Legendre volume quadrature of
Newtonian gravity and dipole field density generates the observations; the
inversion Jacobian is not used to synthesize data. Quadrature orders 12 and 16
are compared. A separate geoana forward calculation evaluates the recovered
model at 36 holdout locations and a different elevation from the 49 observations.
The inverse mesh has 324 active cells. Gaussian noise uses seed 82, standard
deviations 0.002 mGal and 0.3 nT. These are synthetic test parameters.

The inducing direction is 60 degrees inclination and 25 degrees declination;
the MVI experiment deliberately uses a different magnetization direction.
Reference integration and analytic mesh forward predictions agreed within
0.000000000000009 mGal and 0.0000000000005 nT for the true block models.

## Findings and fixes

A zero-density start with a nonnegative bound exposed a real optimizer stall:
the SimPEG 0.25 active-set gradient is scaled by the inactive CG step, which is
zero when every parameter starts on a bound. The stalled run returned a zero
model after 40 iterations, weighted RMS about 59, and did not reach its target.
Core now takes a Jacobi-preconditioned inward descent step for this case, retaining
projection and line search. No BFGS factorization or installed-library patch is
introduced. Unit tests cover inward and binding gradients, and an end-to-end
positive-density test starts exactly on the zero lower bound.

Gravity's observation component is now explicit. Default up preserves existing
callers; down changes input/prediction sign consistently without changing density
or positive-up coordinates. Scalar and joint up/down runs recover matching
models. The workflow NPZ, residual CSV and manifest retain that convention.
The down-component regression also removes and restores an explicit regional
prediction. QGIS inversion summaries now include the Core solver diagnostics.
Magnetic-only inversions reject a nondefault gravity component.

Primary backend contracts:
[SimPEG gravity units and upward gz](https://docs.simpeg.xyz/latest/content/api/generated/simpeg.potential_fields.gravity.Simulation3DIntegral.html),
[joint cross-gradient formulation](https://docs.simpeg.xyz/latest/content/user-guide/tutorials/13-joint_inversion/plot_inv_3_cross_gradient_pf.html).

## Observed fit and sensitivity

Weighted RMS is residual divided by the supplied standard deviation, then RMS.
Holdout RMS uses the noise-free independent field and baseline uncertainty.

| Baseline inversion | Training weighted RMS | Holdout weighted RMS |
| --- | --- | --- |
| Gravity | 0.83 | 0.62 |
| Susceptibility | 0.98 | 0.63 |
| Cartesian MVI with remanence | 0.64 | 0.59 |
| Joint, uncoupled | 1.00 gravity / 1.00 magnetic | 0.79 / 0.67 |
| Joint, coupling 2e12 | 0.81 gravity / 1.00 magnetic | 0.37 / 0.68 |

The nine scalar/vector cases include gravity up/down, initial beta ratios 0.3/1/3,
uncertainty multipliers 0.5/1/2, and float32 sensitivities stored on disk versus
float64 in memory. All satisfied the predeclared training RMS below two and
holdout RMS below three. These acceptance criteria check numerical behaviour,
not an exact reproduction of the true cell model or a universal parameter recipe.

Joint coupling zero stopped after 23 iterations. Coupling 2e12 reached the
40-iteration limit, with magnetic weighted RMS 1.00026. It passed the campaign's
data-fit threshold but did not establish optimizer convergence or exact unit
misfit. Core joint diagnostics now separate iteration-limit status and individual
fits. The paired beta estimate uses a fixed seed for repeatability.

## Artifacts, interruption and limitations

Scalar/vector cases execute the complete run_inversion_workflow and reopen
model.npz, data.csv and run.json; the workflow also writes model.vtk. Joint cases
exercise the joint Core API and its VTK/expanded-model helpers, saving models and
diagnostics. Joint export is not claimed to be the scalar command-line workflow.
Additional regression tests cancel after an actual solver iteration and require
failed state with no finished model or residual publication. Existing tests also
exercise CLI completion, sparse IRLS, mesh/sensitivity guards and the prohibition
on BFGS fallback. A completed execution can still miss the numerical target.

The recovered cell models differ substantially from the true compact cube:
baseline relative L2 model errors are about 89 percent for density, 85 percent
for susceptibility and 97 percent for MVI. Good predictions therefore do not
establish a unique shape, depth or magnetization direction. No geological
resolution claim is made. The small flat-topography campaign does not certify
regional-scale RAM/runtime, arbitrary topography, every noise model, all
electrical/EM inverse methods or inversion of a particular published survey.

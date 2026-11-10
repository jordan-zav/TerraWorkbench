# Dispersive IP and constrained MVI

Implemented in Core on 27 October 2026. These are Python/operation-workflow
features; this change does not add specialized QGIS forms. No private survey,
acquisition settings or images were used. Existing installed libraries are not
modified. All numerical work remains in terraworkbench_core.

## Spectral and transient IP

The new dispersive_ip module extends the existing direct Pelton Cole-Cole
resistivity model with bounded nonlinear inversions. Spectrum parameters are
rho_zero in ohm m, intrinsic chargeability m in V/V, resistivity relaxation time
tau_rho in seconds and exponent c. The convention is exp(+i omega t): passive
resistivity has negative imaginary part. No automatic phase-sign guessing or
conversion between conductivity-model and resistivity-model time constants is
performed.

| Core operation | Function and result |
| --- | --- |
| sip.fit_cole_cole | Fit rho0, m, tau_rho and c to complex resistivity |
| ip.cole_cole_decay | Cole-Cole step/pulse-off values or rectangular gate means |
| ip.fit_decay | Fit m, tau_rho and c to normalized transient data |
| ip.sensitivity | Static-IP sensitivity for supplied 2.5D/3D geometry and conductivity |
| ip.dispersive_forward | Frequency/time responses using a prescribed sensitivity |
| ip.dispersive_inverse | Recover m, tau_rho and c per prescribed cell/zone |

Functions can also be imported directly from terraworkbench_core.dispersive_ip;
ip_sensitivity belongs to electrical_pde. All operations are discoverable via
operations.operation_info and executable via operations.run_operation or the
existing typed Core workflow system, without QGIS or REST. The information
contract declares NumPy/SciPy; the sensitivity operator additionally declares
SimPEG 0.25.x through the existing electrical extra.

The direct cole_cole_decay function returns an array. The registered operation
wraps it in a result dictionary with decay_v_v and waveform/normalization metadata;
workflows can pass the decay_v_v field into ip.fit_decay.

### Time response, gates and primary voltage

The Cole-Cole decay uses the Mittag-Leffler relaxation E_c of negative
(t/tau_rho)^c. It is evaluated as a positive exponential mixture, using the
inverse rate-distribution CDF. For probability p its dimensionless rate is
[sin(pi c p) / sin(pi c (1-p))] raised to 1/c. The Debye endpoint c=1 uses
the exact exponential. Each gate averages the exponential analytically before
integrating the mixture; a gate is not replaced by its midpoint.

This Cole-Cole relaxation differs from the stretched-exponential SIP model in
[Kang and coauthors' reference implementation](https://github.com/simpeg-research/kang-2018-spectral-inducedpolarization).
Background on the relaxation function is given in
[Time Domain Characterization of the Cole-Cole Dielectric Model](https://pmc.ncbi.nlm.nih.gov/articles/PMC7851980/).
The implementation is checked against independent Debye and half-order erfcx
identities, including finite pulses and gate integrals.

With an infinite charging period, secondary/DC primary is m times the
relaxation. A finite pulse starts at -pulse_duration_s and ends at zero; its
secondary response subtracts the relaxation at t plus pulse_duration_s.
normalization selects dc for fully charged primary, or pulse for primary
immediately before finite-pulse switch-off. These conventions are available
for both curve and spatial inversion. They must match the supplied data.

Times are nonnegative seconds; gates are an (n,2) array of start/end seconds.
Supply times OR gates, not both. Values and errors supplied to fit_ip_decay
are V/V. The older electrical.integrated_chargeability operation returns
mV/V: divide BOTH its values and their errors by 1000 before fitting here.
For its measured finite-pulse primary, select pulse normalization and supply
the actual on-time. For finite signed pulse histories use the separate
[prescribed-current-history API](ip_current_history.md). Receiver transfer
functions and electromagnetic induction are not modeled by these kernels.

### Complex noise and solver contracts

Spectrum errors apply separately to real and imaginary components. A shared
2x2 or per-record covariance can instead include real/imaginary correlation;
covariance units are squared ohm m for complex resistivity or squared V/V for
normalized spatial IP. Records remain independent. Primary-voltage uncertainty
and cross-gate/cross-frequency covariance are not inferred automatically.

Initial values, references and bounds are explicit. Curve fits default to no
regularization; their optional nonzero beta penalizes distance to the declared
reference, which defaults to the initial parameters. Spatial fits require beta
and reference explicitly. Positive rho0 and tau use logarithmic coordinates;
m and c retain physical coordinates. The L2 prior uses those transformed
coordinates. Results retain the physical reference and log-parameter indices.

Forward evaluations, including the final prediction and numerical Jacobian
calls, are counted. Cancellation and hard call budgets raise rather than
publishing a successful solve. Exhausting the optimizer budget yields
success=False. Results also expose weighted RMS, numerical data-Jacobian rank,
singular values and active bounds. Optimizer success and numerical rank do
not prove parameter identifiability or adequate data fit. Failed quadrature
raises instead of silently returning an unverified curve.

### Spatial IP scope

ip_sensitivity returns a matrix whose rows follow ABMN and whose columns
follow supplied active cells/zones. Conductivity, geometry, terrain mask and
parameter labels are held fixed. Frequency output is the dimensionless complex
IP anomaly 1-rho(omega)/rho_dc, not complex resistivity itself. Time output is
secondary/selected primary in V/V. Observations have shape (n_ABMN,n_samples).
Within-record spectral covariance follows flattened row-major ABMN/sample order.

The operator combines the existing normalized static-IP Jacobian with each
region's dispersive response. This is the small-polarization, quasi-static
approximation. It is not a nonlinear complex-conductivity PDE/Maxwell solver,
and large chargeability or induction-dominated observations require further
modeling. The implementation fits at most 32 cells/zones, hence 96 dispersive
parameters, with a two-million-element dense Jacobian guard and a 100,000-output
sample guard. This is a budgeted parameterized spatial inversion, not an
unrestricted industrial voxel tomography claim.

## MVI controls and remaining ambiguity

Cartesian MVI now supports amplitude-group IRLS, requested regularization norms
and weights, independent vector references and starting models. A vector model
must be (n_active,3) or a component-major vector [all x, all y, all z]; scalar
reference controls are rejected rather than ignored. Reference and start must
be finite and inside component bounds. A missing vector reference means zero,
independently of the start. Scalar inversion keeps its existing contracts.

mvi_regularization defaults to amplitude, preserving the old numerical recipe.
The optional vector_smooth mode combines common amplitude smallness with
component smoothness, penalizing direction changes as well as amplitude changes.
Norms below two require positive irls_iterations. The usual IRLS stopping and
cycle limits apply; a separate initial L2 target does not prematurely stop the
sparse stage. Diagnostics report actual cycles, target status and resolved
regularization weights. IRLS is nonconvex and is not a uniqueness guarantee.

MVI parameters remain effective susceptibility SI. Diagnostics now declare
that unit, component-major positive-up layout, and the H0 factor converting to
magnetization A/m. Existing exported field names remain compatible. The flat
automatic-surface builder also now handles collinear profiles without a Qhull
triangulation failure; this inferred flat surface is not measured topography.

## Numerical results

scripts/validate_ip_mvi_extension.py reproduces the 28-case extension with a new
output directory. Sections ip and mvi can run separately. It records source
hashes, package versions, inputs, predictions, recovered parameters and reports.
The IP cases use three exponents (0.4, 0.65, 0.9), noiseless/noisy spectra and
finite-pulse gate data, plus two-zone PDE frequency/time fits. Noiseless model
parameters meet the predeclared recovery tolerances. Noisy weighted RMS is
0.976–0.984 for spectra, 0.995–1.002 for transient curves, 0.973 for spatial
spectral IP and 0.928 for spatial transient IP. These are authored synthetic
checks with one fixed Gaussian realization, not field validation or Monte Carlo
coverage. PDE decay data use the same linearized spatial model as their fit.

Twelve MVI runs cross three orientations with two support masks and two recipes.
The synthetic 200 m cube is inside an explicitly prescribed 400 m support box
of 64 cells; the unrestricted comparison uses 324 active cells. No true
direction is supplied. The support box is an informative geometric assumption,
not a region automatically recovered from data.

| True inclination / declination | Full mesh amplitude | Full mesh vector IRLS | Support box amplitude | Support box vector IRLS |
| --- | --- | --- | --- | --- |
| 25 / -35 degrees | 37.51 | 26.95 | 3.20 | 1.37 |
| -35 / 135 degrees | 36.84 | 21.65 | 1.25 | 0.29 |
| 0 / 90 degrees | 5.88 | 1.32 | 0.85 | 1.67 |

Entries are integrated-vector angular errors in degrees, not voxel-wise
orientation accuracy. All holdout weighted RMS values remain below 1.04. The
optional recipe is not uniformly superior: the third support-box angle worsens,
and two sparse runs stop with training RMS 1.027 and 1.021, above the strict
unit target. Their target_reached flags remain false. They satisfy the campaign's
looser numerical diagnostic threshold, not a claimed strict-target convergence.
The unconstrained direction problem remains ambiguous. Useful geological
support/prior information must come from defensible independent evidence.

The final campaign is retained under evidencia conservada en el archivo de desarrollo del proyecto, corrida 20261027_150718_e9496ceeea0946329137088debee21e8.
Separate tests check primary conventions, 2.5D/3D static-IP consistency, numerical
rank deficiency, work guards before covariance allocation, cancellation,
nonconverged status, vector-reference shapes and a complete typed transient-IP
forward/inverse workflow. No installed library source or original survey is changed.

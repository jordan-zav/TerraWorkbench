# Explicit IP stack modeling and inversion

The Core ip_stacking module predicts stacked off-time responses and fits
already-stacked V/V observations using a declared finite current history.
It reuses ip_waveform and the existing Cole-Cole quadrature and solver.
It does not detect pulses or process raw instrumental voltage time series.

## Selection and timing

Supply the full event_times_s/current_a history under the existing
[current-history contract](ip_current_history.md). Current and polarization
are zero before the first event; the last event is actual final switch-off
at time zero. No periodic steady-state prehistory is inferred.

off_event_indices selects actual switch-off events using zero-based indices.
Indices must be unique and increasing; current after each selected event must
be zero and current immediately before it must be nonzero. Earlier pulses
remain in every selected cycle's history, even when their off-periods are
excluded from the stack. Excluding a cycle does not erase its polarization.

times_s or gates_s is relative to EACH selected switch-off. Every observation
must remain inside that off-period. A gate may end at the next on-switch; a point
sample exactly at that on-switch is rejected because it would include on-time
voltage. Repeated zero-current markers do not end an off-period.
Current history and observation geometry are shared across the stack;
different histories or moving geometry require separate calculations.

stack_weights are explicit nonnegative cycle weights, normalized to sum to one.
Omitting them gives equal weights. All-zero weights are rejected; zero-weight
cycles are recorded but do not contribute to the numerical combination.
Their supplied histories and diagnostic outputs still obey the work limits.

## Two conventions, explicitly selected

stack_mode is mandatory. Let w_i be the normalized weights and I_i the signed
current immediately before cycle i switches off. Let N_i be secondary voltage
divided by the fully charged DC primary for I_i. Let P_i be the cycle primary
voltage in the same DC units, or one for dc normalization.

| Mode | Implemented combination |
| --- | --- |
| mean_of_ratios | sum_i w_i N_i/P_i |
| ratio_of_sums | sum_i w_i abs(I_i) N_i / sum_i w_i abs(I_i) P_i |

mean_of_ratios represents averaging per-cycle normalized V/V curves.
ratio_of_sums represents dividing weighted polarity-aligned raw-voltage sums;
its amplitude factors are essential when on-current magnitudes differ.
These modes need not agree. Neither is claimed to reproduce every instrument.

normalization=pulse uses each final pre-switch primary; dc uses the corresponding
fully charged DC primary. Pulse is the default. Keep this selection consistent
with the input observations and their errors. Multiplying or reversing the
entire current waveform leaves either normalized stack unchanged.

For mean_of_ratios, a participating cycle with near-zero primary is rejected.
For ratio_of_sums, the mixed primary must be nonzero; one cycle may have zero
primary while the complete voltage sum remains defined. No absolute value is
applied to the secondary response or primary ratio. Polarity alignment uses
the signed on-current, preserving physically signed transients.

## API and spatial fitting

| Core operation | Direct Python function |
| --- | --- |
| ip.stack_decay | ip_stacking.stack_ip_decay |
| ip.fit_stack | ip_stacking.fit_ip_stack |

Forward output contains decay_v_v, cycle_secondary_to_dc and
cycle_primary_to_dc_ratio, together with the history, selected indices,
normalized weights, signed reference currents and conventions. The final
decay_v_v field chains directly into observed_v_v in typed Core workflows.
Names and parameter labels are authored in English, Spanish and Portuguese.
Dependencies remain NumPy and SciPy; no new package is required.

Without sensitivity, model parameters are scalar intrinsic m (V/V), resistivity
relaxation time tau_s (seconds) and exponent c. The curve inverse requires
initial parameters and positive observation errors. Reference defaults to
initial and beta defaults to zero. Bounds are explicit; default upper m is 0.5.

With a supplied normalized static-IP sensitivity, parameters are per-zone
vectors, and initial/reference have shape (n_zones,3). Spatial fitting requires
both reference and beta explicitly. Each cycle's secondary and primary memory
are mixed across zones before the selected stacking normalization. Dividing
individual zone curves first is not equivalent and is not implemented.
There are at most 32 fixed zones, with conductivity and geometry held fixed.
The small-polarization approximation remains; this is not coupled nonlinear
complex-conductivity/Maxwell inversion.

Observed data and their standard deviations must already be stacked V/V.
The API does not estimate errors or divide uncertainty by the square root of
the cycle count. Shared primary errors, cross-gate covariance and correlated
cycles need a justified noise model; this fit uses independent supplied errors.
Numerical rank and optimizer success do not establish parameter uniqueness.

## Budgets and limitations

The full history has at most 128 switches; at most 64 off-periods may be selected.
All selected prefixes together are limited to 4096 relaxation terms, including
primary-memory terms. Cycle diagnostic arrays are limited to 100000 values.
The existing two-million-element sensitivity/Jacobian limits, counted complete
stack predictions, cancellation and nonconverged status remain in force.

No transmitter ramps, receiver transfer functions, mains/sferic removal,
automatic gate picking, empirical drift correction or vendor-specific rejection
recipe is inferred. A correct fit to the wrong stacking convention can bias
the recovered parameters; preserve acquisition and processing metadata.

## Numerical evidence and references

Independent Debye gate formulas check both conventions and both primary
normalizations. Tests also cover unequal on-currents, full polarity reversal,
selected-cycle history preservation, zero weights, primary cancellation,
off-period boundaries, integer index validation, work limits, cancellation,
two-zone recovery and a complete exported forward/inverse workflow.

scripts/validate_ip_stacking.py completed 16 authored clean/noisy cases using
four selected off-periods: curve fits for c=0.4/0.85 under both modes, plus
two-zone fits under both modes and both primary conventions. Clean recovery
meets 1e-4 relative parameter tolerance. These tests use one fixed Gaussian
realization and a prescribed small sensitivity matrix; they are not a new PDE
solve, field validation or Monte Carlo coverage. Inputs, predictions, fitted
parameters, package versions and source hashes are retained under
evidencia conservada en el archivo de desarrollo del proyecto, corrida 20261027_180755_1dd68bcf89cd4df8b130e5a80ca0f740.

The importance of finite pulse history is discussed in
[Spectral induced polarization: frequency domain versus time domain laboratory data, Appendix C](https://doi.org/10.1093/gji/ggab071).
An example of normalized positive/negative decay stacking appears in
[Understanding the Fate of H2S Injected in Basalts by Means of Time-Domain Induced Polarization Geophysical Logging](https://doi.org/10.1029/2023JB028316).
These references motivate the distinctions; the equations above define the
local contract and do not claim numerical equivalence to an instrument.

# IP with prescribed current histories

Implemented in Core on 27 October 2026. The ip_waveform module computes and
inverts Cole-Cole off-time curves after a finite piecewise-constant current
history. It shares the verified Mittag-Leffler relaxation and gate quadrature
with dispersive_ip; there is no second implementation of that kernel.

## Why the history matters

Polarization can persist from earlier positive and negative current pulses.
Using only the last on-time can change the apparent decay and fitted parameters.
The importance of the complete pulse sequence is described in
[Spectral induced polarization: frequency domain versus time domain laboratory data, Appendix C](https://doi.org/10.1093/gji/ggab071).
That reference motivates history modeling; it does not certify this local
implementation or any field dataset.

## Input and normalization contract

- event_times_s contains 2 to 128 strictly increasing switch times in seconds.
  Its last entry must be zero: the final switch-off.
- current_a contains signed current in amperes immediately AFTER each switch.
  The final value must be zero and the preceding value must be nonzero.
- Current and polarization are assumed zero before the first supplied event.
  Unknown prehistory is not silently replaced by a periodic steady state.
- Supply times_s OR gates_s. Times are nonnegative seconds after final switch-off;
  gates are positive-width start/end pairs in the same reference.
- The signed final on-current is I_ref. Reversing or scaling the entire current
  history leaves the normalized V/V result unchanged; I_ref remains recorded.
- normalization=dc uses fully charged DC voltage for I_ref. normalization=pulse
  uses the predicted voltage immediately before final switch-off. Values and
  standard deviations supplied to inversion must follow the same convention.
  The history operations default to pulse; the existing single-pulse API keeps
  its dc default.
- Intrinsic chargeability m is V/V, tau_s is the resistivity-model relaxation
  time in seconds, and exponent c is in (0,1]. No conductivity-time conversion
  or mV/V conversion is inferred.

For example, switch times [-7,-5,-3,-1,0] with currents [2,0,-2,2,0] describe
a positive pulse, a pause, a negative pulse, a positive pulse and final off.
Observations in this API follow the final off; they are not a stacked average
of the earlier off-periods. For explicitly selected off-period combinations,
use the separate [stack modeling and inversion API](ip_stacking.md).

## Implemented response

Let a_j = (I_j - I_(j-1))/I_ref, with I before the first event equal to zero.
Let E(t) be the unit Mittag-Leffler relaxation for the supplied tau and c.
After the final switch-off:

secondary/DC primary = -m sum_j a_j E(t-t_j).

The final pre-switch primary/DC primary ratio is:

P = 1 - m sum_(t_j<0) a_j E(-t_j).

For pulse normalization the decay is divided by P. Rectangular gates average
each relaxation over their full width before superposition. The implementation
rejects near-zero normalizing primary voltage rather than returning a large,
misleading ratio. It retains signed responses; it does not take absolute values.

For spatial calculations, normalized static-IP sensitivity S mixes each
zone's secondary response and primary-memory contribution separately. Division
by the mixed primary occurs AFTER spatial mixing. Averaging separately
normalized zone curves would give a different result and is not used.

## Core operations

| Operation | Purpose |
| --- | --- |
| ip.waveform_decay | Forward curve/gate response and primary ratio |
| ip.fit_waveform | Bounded fit of intrinsic m, tau_rho and c |
| ip.spatial_waveform | Fixed-sensitivity response for prescribed zones |
| ip.fit_spatial_waveform | Bounded fit of three parameters per zone |

The direct Python functions have the same parameter contracts. Forward results
contain decay_v_v; typed workflows can pass this field to observed_v_v in the
inverse operation. Results record current history, signed reference current,
primary convention, units and prehistory assumption. Operation provenance
records input and entry-module hashes and NumPy/SciPy versions. No new optional
dependency is required; generating a PDE sensitivity separately requires the
existing electrical extra. Labels and operation names are authored in English,
Spanish and Portuguese.

Curve fitting supports positive independent observation errors, explicit bounds,
initial/reference parameters and optional L2 beta. Positive tau is fitted in
log coordinates. Spatial fitting requires explicit reference and beta and is
limited to 32 fixed zones. Solver/forward budgets, cancellation, rank and
nonconverged status follow the existing dispersive-IP contract. Rank and a good
fit do not establish geological uniqueness.

## Limits

This is a finite ideal-switch current-source model. It does not infer transmitter
ramps, receiver transfer functions, arbitrary on-time observations, instrumental
stacking recipes, steady-periodic prehistory or electromagnetic induction. Supply a
complete justified history and the correct data normalization. Truncating a long
history is a modeling decision, not an automatic correction.

There are at most 4096 event/sample relaxation terms, including the pre-switch
primary terms, and no shifted time may exceed 1e12 seconds. Spatial output is
limited to 100000 values with a two-million-element sensitivity/Jacobian budget.
Very small final on-current relative to earlier amplitudes is rejected to avoid
unbounded normalization. Finite precision can limit highly cancelling histories.

Spatial IP retains the quasi-static, small-polarization approximation with
conductivity, geometry and zone support fixed. It is not a coupled nonlinear
complex-conductivity or Maxwell inversion. Arbitrary field-data import and
instrument calibration remain separate from this mathematical API.

## Validation

Tests compare a single pulse against the previous implementation for three
exponents and both primary conventions. Independent Debye gate formulas and
half-order erfcx point formulas check signed multi-pulse superposition. Other
checks cover current reversal/scaling, near-zero primary, work limits, masks,
cancellation, numerical nonconvergence, two-zone recovery and a complete typed
forward/inverse workflow.

scripts/validate_ip_waveform.py reproduces 16 authored synthetic cases: two
histories, three exponents, clean/noisy gate curves, and clean/noisy two-zone
2.5D PDE-sensitivity responses under both primary conventions. All 16 passed
their declared numerical criteria. Clean parameter recovery meets 1e-4 relative
tolerance. Spatial noisy weighted RMS is 0.934 for DC and 0.933 for pulse
normalization; the largest spatial parameter relative error is about 3.7%.

These are conditional synthetic checks with one fixed Gaussian realization.
The spatial synthetic generator and inverse share their linearized kernel;
this is not independent nonlinear PDE or field validation. The report records
source hashes, library versions, parameters and inputs/predictions in NPZ files.
Evidence is retained in evidencia conservada en el archivo de desarrollo del proyecto, corrida 20261027_152515_fb2e908d1b414690a80f4ee87950c977.

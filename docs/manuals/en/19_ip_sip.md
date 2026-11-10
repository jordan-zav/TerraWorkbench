# 19. IP, SIP, Cole–Cole and current history

[English](../en/19_ip_sip.md) · [Español](../es/19_ip_sip.md) · [Português](../pt/19_ip_sip.md)

## Quantities and domain

Integrated chargeability depends on time gates, primary voltage and normalisation. V/V and mV/V differ by a thousand. A time integral without declared normalisation/units cannot be compared directly with dimensionless Cole–Cole amplitude.

electrical provides integrated_chargeability and cole_cole_resistivity. dispersive_ip includes frequency- and time-domain forward/fitting. Exponent, tau and complex convention must accompany results; opposite phase signs can arise from temporal convention rather than geology.

## Waveform and memory

An isolated ideal pulse does not represent alternating-sign pulses and residual polarisation from earlier pulses. ip_waveform models explicit current history and gates. Record switching times, pulse amplitudes, gate start/end and the primary-voltage reference.

Stacking may use mean of ratios or ratio of sums. They are not algebraically equivalent when denominators vary. stack_ip_decay and fit_ip_stack retain conventions, weights and accepted intervals. Do not reconcile campaigns by retrospectively changing the chargeability definition.

## Spatial inversion

Static IP in electrical_pde is linearised around fixed conductivity for small chargeabilities. It is not automatically full spatial inversion of dispersive Cole–Cole Earth. Spatial current-history functions also require the sensitivity model and zones in their contract.

Decay fits may be ambiguous in tau, exponent and amplitude when gates miss relevant scales. A local covariance array does not establish unique identification. Examine correlations, bounds, reserved gates and uncertainty sensitivity.

## Procedure

1. Check DC polarity and geometry.
2. Retain measured current and original gates.
3. Identify normalisation and units of every observation.
4. Fit a model appropriate to the domain and pulse sequence.
5. Compare the complete response, not only summary chargeability.
6. Examine time/frequency residuals and parameter bounds.

See [dispersive IP](../../reference/methods/dispersive_ip_mvi.md), [current history](../../reference/methods/ip_current_history.md), [stacking](../../reference/methods/ip_stacking.md) and each contract's primary references. A registered IP operation does not mean all instrument IP modes are implemented or validated.

## Related implementation

[dispersive_ip](../../../terraworkbench_core/dispersive_ip.py), [ip_waveform](../../../terraworkbench_core/ip_waveform.py), [ip_stacking](../../../terraworkbench_core/ip_stacking.py)

---

[Contents](README.md) · [Previous](18_electrica_dc.md) · [Next](20_em_mt.md)

# 22. GPR, seismic traces and boreholes

[English](../en/22_ondas_sondeos.md) · [Español](../es/22_ondas_sondeos.md) · [Português](../pt/22_ondas_sondeos.md)

## Array contract

waveform_processing accepts matrices with traces in rows and uniformly sampled time on the last axis. It uses seconds, metres and m/s. These kernels do not establish SEG-Y/all proprietary GPR readers, instrument-response removal or a complete seismic interpretation system.

Identify time zero, dt, trace spacing, channels and component orientation first. Record whether amplitudes are calibrated physical values or digital counts. Time interpolation/resampling is a separate recorded operation.

## Trace preparation

trace_bandpass applies zero-phase Butterworth SOS; two passes change amplitude response relative to one. dewow reduces low-frequency content using a chosen window. remove_trace_background removes a common component and can erase real horizontal reflectors. correct_time_zero shifts time reference; explicit_time_gain changes amplitudes using a declared function.

Keep a version without display gains. Velocity or reflection-amplitude fitting on AGC output must account for its signal transformation. Compare time edges, unsupported regions and differences at each step.

## Limited interpretation tools

fit_diffraction_hyperbola fits effective geometry/velocity under a hyperbolic model. normal_moveout needs compatible velocity and offsets and is not migration. phase_velocity_image produces a representation whose resolution depends on array geometry and data. hvsr_windows and sta_lta_picks implement window analysis and change detection without automatically determining true events or stratigraphy.

## Logs and trajectory

well_log_io reads LAS text and updates curves using lasio where required. Check mnemonics, units, NULL, depth range and spacing. A LAS well-log file is not a LiDAR cloud despite the shared extension.

borehole offers depth QC and minimum-curvature trajectory. Measured depth, inclination and azimuth need defined references. Along-hole measured depth is not vertical elevation or horizontal distance. Reconstructed trajectories inherit heading/inclination uncertainty.

## Acceptance

Check sample/trace counts, dt, plausible velocities, axis reversals, nulls and values reopened from export. Separate original, corrected and interpreted curves. Controlled examples test specific contracts, not all instruments or formats.

See [methods and limits](../../research/core_expansion_implementation.md), [method validation](../../validation/reports/inversion_methods_validation.md) and [waveform/log APIs](../../reference/api/en.md).

## Related implementation

[waveform_processing](../../../terraworkbench_core/waveform_processing.py), [well_log_io](../../../terraworkbench_core/well_log_io.py), [borehole](../../../terraworkbench_core/borehole.py)

---

[Contents](README.md) · [Previous](21_potencial_espontaneo.md) · [Next](23_integracion_experimentos.md)

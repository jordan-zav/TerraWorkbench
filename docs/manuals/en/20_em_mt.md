# 20. FDEM, TEM, transients and magnetotellurics

[English](../en/20_em_mt.md) · [Español](../es/20_em_mt.md) · [Português](../pt/20_em_mt.md)

## Separate the problems

FDEM uses discrete frequencies and complex responses; TEM uses time evolution, excitation and gates. MT uses natural-field impedance with its own axes/units. Conductivity fitted by any of these models depends on geometry, calibration and parameterisation.

## FDEM

fdem_layered represents layered Earth and fit_fdem_conductivity fits conductivities at fixed geometry. Record transmitter/receiver separation, orientation and height, frequency, moment and component. Do not substitute secondary B in teslas for ppm of primary without the appropriate instrument conversion.

fdem_3d_forward and fit_fdem_3d_zones support isotropic 3D fields and local zonal fitting on an explicit mesh. Sparse factorisation imposes work limits. This does not establish industrial million-voxel inversion, anisotropy or automatic mesh design.

complex_calibration fits/applies complex response. Amplitude/phase calibration needs standards and instrument context; missing transfer information is not justification for assuming unity response.

## TEM and gates

tem_stepoff_layered models ideal turn-off; tem_waveform_layered incorporates a piecewise-linear waveform. State whether the variable is B or dB/dt and its units; these contracts use T/s for dB/dt where applicable. An ideal dipole does not equal a finite loop with actual electronics.

tem_gate_average, stack_transients and gate_recorded_transients distinguish integrated prediction, recorded data and stacking. Define times relative to turn-off or absolute time, widths and pulse signs. Interpolation does not create support outside a record.

## MT

magnetotellurics uses Z = E/H in ohms, exp(+iωt) convention and North/East horizontal axes. Its 1D response has positive Zxy and Zyx = −Zxy. Apparent resistivity depends on |Z|²/(μ₀ω); E/B rather than E/H has different units and requires conversion.

layered_impedance, apparent_resistivity_phase, phase_tensor and fit_layered_resistivity provide primitives and fits. The module is not an EDI/MTH5 reader or a robust time-series transfer-function estimator. Computing a phase tensor neither validates the input fields nor removes all instrument distortion.

See [methods and limits](../../research/core_expansion_implementation.md), [inversion-method validation](../../validation/reports/inversion_methods_validation.md) and [SimPEG's catalogue](https://simpeg.xyz/). Do not attribute every external-engine capability to TerraWorkbench.

## Related implementation

[layered_em](../../../terraworkbench_core/layered_em.py), [fdem_3d](../../../terraworkbench_core/fdem_3d.py), [magnetotellurics](../../../terraworkbench_core/magnetotellurics.py), [transient_processing](../../../terraworkbench_core/transient_processing.py), [complex_calibration](../../../terraworkbench_core/complex_calibration.py)

---

[Contents](README.md) · [Previous](19_ip_sip.md) · [Next](21_potencial_espontaneo.md)

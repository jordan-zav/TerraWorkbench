# 13. Gamma radiometry, spectra and radon

[English](../en/13_radiometria.md) · [Español](../es/13_radiometria.md) · [Português](../pt/13_radiometria.md)

## Products versus observations

K, eU and eTh concentrations, count rates and channel spectra are different inputs. K is commonly in percent; eU and eTh are equivalent ppm under calibration and equilibrium assumptions. An RGB image alone retains neither uncertainty nor a necessarily comparable scale between campaigns.

radiometry provides safe ratios, terrestrial dose rate, F parameter, ternaries and QC. Ternary display maps K to red, eTh to green and eU to blue; record percentiles and normalisation. Ratios need adequate denominator support. safe_ratio and accumulated thresholds avoid interpreting divisions by near-zero values as reliable enrichment.

## Calibrating counts

1. Identify integration time, live time and prior corrections.
2. Apply the appropriate dead-time or live-time model without double correction.
3. Estimate and remove instrument, cosmic and radon backgrounds using appropriate calibration.
4. Correct height relative to a justified reference.
5. Resolve window or spectral mixing using a calibrated response matrix.
6. Convert to concentrations and propagate uncertainty under declared assumptions.

For a non-paralysable detector, dead-time correction is n = m/(1 − τm). It fails when the denominator is not positive. live_time_correction is different: it needs measured live time and interval-normalised rates. Do not routinely combine both corrections.

## Spectra and covariance

energy_rebin and fit_energy_calibration handle energy scale and bin redistribution. Window integration needs energy bounds and covariance handling. fit_full_spectrum and spectral_unmix solve different models; document templates, units, backgrounds and constraints.

NASVD and MNF reduce noise under statistical assumptions. Smoothing creates no new energy information; assess amplitude bias, covariance and negative components. fit_radiometric_response and radiometric_concentrations need relevant standards and instrument response. No sensitivity is universal across detectors.

## Radon: actual scope

Implemented options include upward-detector, calibrated-window and full-spectrum corrections and a paired-detector temporal proxy. Coefficients and backgrounds need calibration; correlation or an algebraic solution does not establish complete atmospheric field reconstruction. Examine chi squared, spectral residuals, negative components and temporal stability.

Laboratory standards and simulations do not replace airborne conditions, pressure, humidity, height and system geometry. Existing reports retain these limitations.

Further reading: [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf), [calibration/radon contracts](../../validation/reports/2d_extensions.md), [implemented methods](../../research/core_expansion_implementation.md) and [public campaign](../../validation/reports/public_processing_benchmark.md). IAEA supplies methodological context, not automatic validation of local coefficients or code.

## Related implementation

[radiometry](../../../terraworkbench_core/radiometry.py), [radiometric_calibration](../../../terraworkbench_core/radiometric_calibration.py), [radiometric_spectra](../../../terraworkbench_core/radiometric_spectra.py), [radiometric_radon](../../../terraworkbench_core/radiometric_radon.py), [radon_corrections](../../../terraworkbench_core/radon_corrections.py)

---

[Contents](README.md) · [Previous](12_terreno_isostasia.md) · [Next](14_estructura_profundidad.md)

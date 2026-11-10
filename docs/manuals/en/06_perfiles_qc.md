# 6. QC, trajectory, timing and acquisition corrections

[English](../en/06_perfiles_qc.md) · [Español](../es/06_perfiles_qc.md) · [Português](../pt/06_perfiles_qc.md)

## Preserve acquisition order

Profile filters operate in samples, time or distance. Database names a container, not a mathematical domain. Time requires a numeric time axis; distance requires a metric abscissa defined per profile. Cumulative distance follows the trajectory and is not radial distance from the first observation.

Define line and sensor before filtering. Nulls, group changes, non-increasing axes and gaps split runs. The engine does not sort, interpolate gaps or join lines automatically. Inspect speed, heading, spacing and duplicates before assuming uniform sampling.

## Magnetic acquisition corrections

A base station corrects temporal variation under assumptions about synchronisation and representativeness. Review its quality and time support: extrapolation beyond the record can introduce an unsupported correction. Lag shifts the measurement–position relationship; record its sign and verify it using repeat lines or comparable signals.

Heading correction models orientation-dependent effects. Tolles–Lawson needs appropriate vector data, calibration and geometry; a regression that absorbs geology is not demonstrated instrument compensation. Preserve design, coefficients and calibration windows for reproduction.

## Choosing a channel filter

| Process | Decisive parameter | Risk |
| --- | --- | --- |
| Moving mean or median | Odd sample window | Attenuating narrow anomalies |
| Hampel despike | Window and MAD threshold | Treating real signal as spikes |
| Detrend | Degree and axis domain | Removing useful regional content |
| Butterworth | Cutoff, order and sampling rate | Incorrect unit conversion or dominant edges |
| Separate notch API | Rejected frequency and bandwidth | Removing signal with interference |

ChannelFilterOptions accepts odd windows from 3 to 1,001 samples, Butterworth orders from 1 to 10 and at most three million rows per run. Time/distance axes are checked for monotonicity and uniformity within an explicit tolerance. Cutoff frequency is in cycles per axis unit, not the rad/m used by 2D FFT.

Moving filters need complete windows and leave null edges. Butterworth uses forward/backward SOS: phase shift is reduced, but amplitude response reflects two passes. A short run may have no valid output; the original is not silently copied and presented as filtered.

## Mobile-gravity QC

Drift requires consistent times and epochs. Tide, Eötvös and motion corrections need compatible velocity channels and sign conventions; do not apply them merely because a heading field exists. These airborne steps do not automatically transfer to stationary land gravity.

See [standalone acquisition](../../development/standalone_acquisition.md), [channel rules](../../guides/survey_workspaces.md) and [SciPy forward/backward SOS](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html).

## Related implementation

[channel_filters](../../../terraworkbench_core/channel_filters.py), [profile_distance](../../../terraworkbench_core/profile_distance.py), [profile_preparation](../../../terraworkbench_core/profile_preparation.py), [preprocessing](../../../terraworkbench_core/preprocessing.py), [survey_corrections](../../../terraworkbench_core/survey_corrections.py), [survey_correction_pipeline](../../../terraworkbench_core/survey_correction_pipeline.py), [magnetic_compensation](../../../terraworkbench_core/magnetic_compensation.py)

---

[Contents](README.md) · [Previous](05_bases_canales.md) · [Next](07_nivelacion_gridding.md)

# 10. Magnetometry, the main field and compact sources

[English](../en/10_magnetometria.md) · [Español](../es/10_magnetometria.md) · [Português](../pt/10_magnetometria.md)

## Identify the input quantity

Total field, IGRF-residual anomaly and sensor differences are not interchangeable. Subtracting the main field again from an anomaly introduces a magnitude error. Record base station, date and previous corrections. A commercial or historical channel name does not necessarily describe its present content.

igrf_field computes East, North and Up components, total field and angular elements through ppigrf. Inputs are geodetic longitude/latitude, height in kilometres and a date valid for the installed coefficients. The Core records coefficient file, hash and epoch range. It does not automatically reproject coordinates or convert a vertical datum. [IGRF models the main field](https://www.ncei.noaa.gov/products/international-geomagnetic-reference-field), not local anomalies.

## RTP, RTE and components

Reduction to the pole or equator transforms an anomaly under assumptions about field and magnetisation directions. An induced direction may be inadequate in the presence of remanence. Conditions producing small denominators need stabilisation; a symmetric map does not certify physical correctness.

magnetic_components provides component conversion and TMI reconstruction from gradients with explicit directions. Weak-mode and mean-level recovery depend on the method's constraints; gradient integration does not necessarily recover a measured absolute datum. Document gradient units and any unobservable component.

## Enhancement products

| Product | Emphasis | Limitation |
| --- | --- | --- |
| Horizontal derivatives and THDR | Lateral variation | Noise and orientation sensitivity |
| Vertical derivative | Short wavelengths | Amplifies high-frequency errors |
| Analytic-signal amplitude | Combined gradients | Not susceptibility |
| Tilt, theta and TDX | Contrasts and gradient ratios | Instability with small denominators |
| Pseudogravity | Transformation under a source model | Requires assumptions; not measured gravity |

Units and trend restoration depend on the product. Preserve a corrected, unenhanced grid as the quantitative modelling reference.

## Dipoles and compact objects

magnetic_dipole_field and fit_magnetic_dipoles provide forward and local position/moment fitting. They require geometry, initial ranges, bounds and enough observations. A fitted dipole does not classify UXO or establish hazard, material or age. Check the dipole approximation against object size and sensor distance.

See [magnetic components](../../reference/methods/magnetic_component_api.md), [compact sources](../../reference/methods/compact_magnetics.md), [acquisition contracts](../../development/standalone_acquisition.md) and [method sources](../../research/PAPER_BACKED_MAGNETIC_METHODS.md).

## Related implementation

[geomagnetism](../../../terraworkbench_core/geomagnetism.py), [magnetic_components](../../../terraworkbench_core/magnetic_components.py), [magnetic_pipeline](../../../terraworkbench_core/magnetic_pipeline.py), [magnetic_products](../../../terraworkbench_core/magnetic_products.py), [compact_magnetics](../../../terraworkbench_core/compact_magnetics.py)

---

[Contents](README.md) · [Previous](09_fft_espectros.md) · [Next](11_gravimetria.md)

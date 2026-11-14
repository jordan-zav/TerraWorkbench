# 8. Spatial filters, masks and mosaics

[English](../en/08_filtros_espaciales.md) · [Español](../es/08_filtros_espaciales.md) · [Português](../pt/08_filtros_espaciales.md)

## Space versus frequency domain

A spatial filter works on raster neighbourhoods; an FFT filter applies a spectral transfer. Some linear filters have related representations in both domains, but a median is nonlinear and has no single Fourier transfer. The 2D circular median and a 1D channel median are distinct tools.

smooth_nine_point provides TerraWorkbench binomial smoothing. The optional smooth_least_squares_9x9 API was removed in 1.1.0 and always raises NotImplementedError; migrate explicitly to smooth_nine_point or circular_median. These alternatives are different filters, with no numerical equivalence claimed. circular_median uses circular support; its size follows the API or form contract. automatic_gain_control changes local contrast: an enhanced anomaly does not necessarily retain its original amplitude for physical-property estimation.

## Recommended procedure

1. Review raster resolution, orientation and mask.
2. Choose a radius or window appropriate to sampling and purpose.
3. Save a new output and recipe rather than replacing the input.
4. Calculate input–output differences and compare statistics on common support.
5. Examine edges and narrow anomalies even when the result looks cleaner.

Missing-neighbour handling belongs to the particular operator. Do not replace NoData with zero before a median without documenting it. When comparing products, prevent different masks from silently changing which observations enter the RMS.

## Directional and wavelet filtering

grid_tools provides directional filters, mosaics and directional wavelet filtering. Record azimuth, scales, wavelet family, boundary extension and gains. Flight-texture filtering does not automatically identify noise: geology can share the same orientation.

A mosaic must explicitly resolve overlap, precedence, lattice, CRS and missing data. Do not combine products with incompatible amplitudes as equivalent observations. A smooth seam can conceal a datum difference.

## Reviewing an output

Measure range, mean, spread, finite fraction and removed amplitude. Compare profiles crossing features in several directions. If a filter changes units or normalises amplitudes, state it in channel metadata and legends. Separate exploration imagery from the signal used for modelling.

For exact parameters see the [API reference](../../reference/api/en.md), [provider catalogue](../../reference/catalogues/qgis.md) and [practical-handbook cautions](../../handbook/handbook_en.md).

## Related implementation

[basic_processing](../../../terraworkbench_core/basic_processing.py), [grid_tools](../../../terraworkbench_core/grid_tools.py)

---

[Contents](README.md) · [Previous](07_nivelacion_gridding.md) · [Next](09_fft_espectros.md)

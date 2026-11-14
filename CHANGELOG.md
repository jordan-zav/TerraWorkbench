# Changelog

## 1.1.0

Adds axis tick marks to the profile viewer. Improves gridding robustness and warns when the requested grid scale is unsuitable for minimum curvature. Corrects IGRF and tilt processing. Preserves the mean by default in reduction to the pole (RTP), including the live filter preview. Adds live previews for the filter stack and recommends GeoRamp for color ramps.

API change: the optional smooth_least_squares_9x9 entry point now always raises NotImplementedError with EN/ES/PT migration guidance. The GX example coefficient table and its source/coefficient constants have been removed from the distributed Core. Callers must explicitly choose TerraWorkbench smooth_nine_point (binomial smoothing) or circular_median (nonlinear median); these alternatives do not claim numerical equivalence.

The README includes the real QGIS hero capture. Tellus A9 benchmark metadata and its download adapter retain the confirmed CC BY 4.0 attribution. Historical public validation records use the renamed classic_style.py provenance key while preserving all original source digest values and documenting the original record hashes.

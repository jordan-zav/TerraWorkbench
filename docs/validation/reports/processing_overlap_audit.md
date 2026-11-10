# Processing overlap and documentation review

Baseline: main at 475eeab1abf88a75b4c807004e5ae10e812a6019, reviewed 26 October 2026.

The static inventory examined 149 Python files and 339 public module functions.
No substantial identical function bodies were found, including normalization of
local variable names. No two of the 94 registered Core operations pointed to the
same module/function destination. These checks do not establish mathematical
independence, correctness, commercial parity or complete discipline coverage.
The reproducible scanner is scripts/audit_processing_overlap.py; its optional
output argument writes the full candidate inventory. It excludes most class
methods, short wrappers, renamed globals and algebraically equivalent rewrites.

## Similar names with different contracts

| Interfaces or methods | Why they coexist |
| --- | --- |
| Sixteen root compatibility adapters and Core modules | Adapters retain older imports and delegate to Core; they are not separate numerical engines. |
| 95 QGIS Processing algorithms and 94 Core operations | Host forms, raster I/O, CRS, NoData and numerical APIs have different responsibilities. Adding these counts does not count independent methods. |
| Channel filters and grid filters | One operates along contiguous 1D runs; the other on 2D spatial grids. Database is storage, not a transform domain. |
| Circular median and FFT filters | Median is nonlinear and spatial; a frequency transfer function cannot replace it. |
| Exact terrain correction and adaptive DEM attraction | Exact correction returns plate minus attraction on DEM-derived stations. Adaptive returns attraction at explicit stations and a reference plane. It is not a replacement without the reduction terms and matching geometry. |
| Thin-layer apparent properties and 3D inversion | Different geometry, units, assumptions and regularization; neither establishes a unique geological model. |
| Euler, Werner and SPI | Different source models, dimensional constraints, derivative requirements and rank tests. |
| Airy roots, finite-prism attraction and flexure | Thickness, field prediction and elastic response are different quantities and boundary assumptions. |
| Minimum-curvature gridding and well trajectory | The shared name does not imply a shared algorithm or input geometry. |

## Documentation corrections

The active manual contains 15 chapters and 30 method notes in EN/ES/PT. Sources
are now assigned to individual notes and exported from the same content used by
the GUI. Chapter reading is labelled as general context. Werner, SPI, spectral
depth and well surveying have dedicated primary references. lasio documents LAS
I/O, not trajectory mathematics; Euler references do not substantiate Werner.
The roadmap no longer lists existing energy calibration, covariance propagation,
spectral fitting, Wiener inversion and linear uncertainty diagnostics as wholly
unimplemented. Their instrumental and nonlinear limitations remain explicit.

Context citations do not validate local derivations. In particular Barnes and Hut
does not prove the local terrain Hessian bound; Kovesi's broader phase methods
do not certify our limited structural attributes. GMT flexure includes models
beyond the local elastic implementation. Library documentation is not a claim
that TerraWorkbench calls that library for every equation in the note.

Implementation, synthetic tests, independent comparisons, QGIS integration and
field validation are separate evidence states. The historical software/license
inventory is preserved with its own dates; this review does not refresh its
license assertions. Numerical kernels were not changed by this documentation review.

## Remaining limits

This is a static overlap review and documentation correction, not a replay of all
numerical methods on survey data. General-purpose chapter help still contains
several methods; not every operation has a separate derivation. Some citations
provide context rather than a one-to-one derivation of the local equations.
Independent numerical comparisons and field evidence must be recorded per
method before asserting validated equivalence. No private survey data or
acquisition parameters belong in this report or the public package.

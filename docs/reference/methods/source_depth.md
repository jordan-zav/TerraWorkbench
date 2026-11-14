# Source-depth interpretation

terraworkbench_core.source_depth contains independent NumPy/SciPy implementations of Euler deconvolution, thin-sheet Werner deconvolution and model-dependent profile SPI. The backend APIs are exposed through Core forms in QGIS, including a grid parameter form where applicable; this does not mean each API has a separate native Processing algorithm.

All horizontal coordinates, elevations and depths use one consistent projected length unit, normally metres. Elevations and vertical derivatives increase upwards. Source z is an elevation; depth is the positive separation below the observation elevation, not automatically depth below terrain. CRS is preserved as a declaration when exporting; these methods do not reproject inputs.

Grid arrays use shape (y,x) with both coordinate axes strictly increasing. North-up raster arrays commonly store rows in decreasing northing order; reverse the y axis and every corresponding field/derivative row before using these APIs. Profile distance increases within each contiguous profile ID. No input is silently sorted or reoriented.

## Euler

euler_window solves a supplied 3-D observation window. euler_grid applies overlapping windows to field and derivative grids. euler_profile solves the constrained 2-D problem using along-profile distance, elevation and horizontal/upward gradients. Full 3-D Euler rejects rank-deficient windows, including perfectly invariant along-strike data; use the 2-D profile formulation when that geometry is justified.

The structural index must be chosen explicitly. For nonzero N the equation is (r-r0) dot grad(T) = N(B-T). Position and constant background B are solved jointly. At N=0 the separate contact equation estimates an offset A; it cannot recover B. An incorrect index can bias the estimated depth even when a numerical solution exists.

Coordinates and field offsets are centered before fitting. Column-scaled SVD controls rank and conditioning without forming normal equations. Acceptance controls include depth bounds, equation residual, relative depth standard error, gradient support and an optional horizontal-distance limit for gridded solutions. The reported standard error only describes the local equation fit: derivative noise, correlations, geological mismatch and index uncertainty are not included. It is not a confidence interval on true geological depth.

## Werner

werner_profile fits a thin sheet on a level profile using the rational field model (A(x-x0)+B h)/((x-x0)^2+h^2), plus optional polynomial interference. background_degree is -1 for no background, or 0, 1 or 2 for constant, linear or quadratic interference. The polynomial-background extension is solved as a linear least-squares system in normalized coordinates; nonphysical depths, deficient rank, excessive conditioning and poor field reconstruction are rejected. Dip and magnetization are not estimated by this API.

The method requires an isolated source adequately represented by the sheet model. Nearby interfering bodies are not generally equivalent to a low-order polynomial. Conditioning and fit residuals do not prove a correct geological interpretation. Sliding windows yield correlated solutions, not independent discoveries.

## SPI and derivatives

spi_profile takes first horizontal/upward derivatives and optional horizontal-second/cross derivatives. When second derivatives are omitted they are estimated by finite differences within contiguous supported segments. Local wavenumber is the absolute value of (Tx Txz - Tz Txx)/(Tx^2+Tz^2). Depths are reported only at supported local peaks, using (index+1)/K: one for a contact, two for a thin sheet and three for a horizontal cylinder. The selected source model is mandatory in the interpretation, even though contact is the API default. This implementation does not automatically recover the structural index, dip or susceptibility.

profile_fft_derivatives and grid_fft_derivatives provide first/second Fourier derivatives on complete, uniformly spaced, level observations. The vertical multiplier is negative radial angular wavenumber. Padding/tapering reduces boundary discontinuities but cannot eliminate edge artifacts. NoData is rejected rather than filled for FFT calculation. Derivative calculation amplifies high-frequency noise; compare smoothing, spacing, padding and edge exclusions before interpreting depths.

interpret_grid dispatches Euler, Werner or SPI on grids. For Werner and SPI choose direction x or y explicitly. These are parallel 2-D profiles with mapped solution coordinates, assuming sources locally invariant perpendicular to the profiles. They do not track strike automatically and are not a general 3-D SPI solution. Supplied derivative grids allow explicit support masks; automatic FFT derivatives require a complete level grid. Euler can use nonlevel observations only with independently supplied valid derivatives.

## Support, execution and export

Moving windows do not cross profile boundaries, missing observations or large distance gaps. The automatic profile gap threshold is three times the median valid within-profile step; an explicit max_gap is preferable when acquisition constraints are known. Euler grids require complete support by default; min_valid_fraction can explicitly relax it. Unsupported SPI samples remain NaN. Peak support, signal floor, prominence, distance, edge exclusion and depth bounds are explicit controls.

Window and accepted-solution budgets prevent unbounded catalogs. Algorithms fail rather than silently truncate outputs. Cancellation is checked between windows, segments or profiles. Grids are processed window by window without constructing an array containing all windows at once. Retained catalogs still consume memory proportional to accepted solutions.

write_depth_catalog creates a new directory containing solutions.csv and catalog.json; SPI also exports wavenumber.npy. Catalogs retain method parameters, rejection counts, NumPy version, SciPy version when used by SPI, implementation source hash and an optional CRS declaration. Empty catalogs are valid outcomes. Existing directories are never replaced. A source estimate is neither an ore-body outline nor an economic target classification.

## Primary references and validation boundary

- Reid et al. (1990), Magnetic interpretation in three dimensions using Euler deconvolution: https://www.reid-geophys.co.uk/wp-content/uploads/2017/11/Reid-et-al-1990.pdf
- Published Werner rational-model and polynomial-interference formulation: https://pmc.ncbi.nlm.nih.gov/articles/PMC9676560/
- Smith et al. (1998), SPI local-wavenumber source models and geometry dependence: https://files.seequent.com/MySeequent/technical-papers/ispi.pdf
- USGS local-wavenumber method and noise sensitivity: https://pubs.usgs.gov/of/2002/0098/intro.htm

Automated tests use analytic dipoles, contact equations, thin sheets, polynomial backgrounds and complex-gradient source models. They check absolute coordinates, upward sign, source depth, source-model factors, gaps, missing support, rank, conditioning, exports and grid profile directions. These establish synthetic correctness for the implemented formulations. Field-data uncertainty, acquisition-dependent tuning and agreement with proprietary implementations remain separate validation work.

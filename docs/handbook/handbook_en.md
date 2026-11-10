# TerraWorkbench practical handbook

The same chapters, equations and primary links are available in English, Spanish and Portuguese. Historical potential-field references remain available separately. This handbook describes assumptions and QA; it is not a claim of complete discipline coverage or field validation.

## GRD import and filter workflows

Import the grid, verify coordinates and units, choose a filter, edit its parameters, then run the ordered stack. The Geosoft binary GRD reader creates a GeoTIFF at your chosen destination; the source stays unchanged. A GRD extension alone does not identify its encoding. Workflow outputs are temporary when no output directory is selected. A chosen directory receives a separate run folder, recipe and optional intermediate rasters. Save the stack to reuse settings, not to certify identical source data. Check each stage before interpreting the final image.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

Chapter context:

- [GDAL raster data model](https://gdal.org/en/stable/user/raster_data_model.html)

## Coordinates, units and missing data

Assigning a CRS describes existing coordinates; reprojection changes them. Do not assign a new CRS to repair wrongly positioned data. Record horizontal units, elevation reference and whether height means ground, sensor or clearance. A projected metric CRS is required for distance-based grid processing. Grid spacing and sample spacing are different. Check NoData masks, orientation, pixel centres and GDAL scale/offset before comparing rasters. Zero is a measurement, not an automatic missing-data marker. A local projected CRS does not certify a vertical datum conversion.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

Chapter context:

- [GDAL raster data model](https://gdal.org/en/stable/user/raster_data_model.html)

## Databases, channels and provenance

Keep immutable imported channels and create derived versions with explicit units and meaningful names. The survey store combines a SQLite catalogue and column-oriented Parquet data; read selected columns instead of loading every channel. Inspect import delimiter, header row, decimal separator and missing values. Filters must respect line boundaries, gaps and sampling. A segment safety limit is not a total database capacity. Recipes identify channel versions and processing steps. Reusing a recipe after replacing an input must be reviewed. Channel lineage explains processing history, not scientific correctness.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

Chapter context:

- [GDAL raster data model](https://gdal.org/en/stable/user/raster_data_model.html)

## Gridding and line quality control

Correct timing, base station and acquisition effects before crossover leveling and gridding. Examine residuals by line and direction. Grid cell size cannot recover unsampled wavelengths. Compare interpolation methods with spatial holdout, not random neighbouring points that leak spatial information. Record search radius, neighbours, smoothing and blanking distance. A complete rectangle can contain unsupported extrapolation. Mask distant cells and compare alternative spacing. Equivalent sources require source depth, damping and memory controls; they are an interpolating representation, not a unique geological body. Microleveling must not remove real geology aligned with flight lines.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

### Apparent layer properties

Use a complete grid with rows increasing north and columns east. The continuous periodic layer has prescribed top depth and thickness; density contrast is kg/m³ and susceptibility is SI. Magnetic field strength, inclination positive down and declination from grid north are explicit. The inverse removes the observed mean and adds the chosen background. Regularization is in data/property units and gain limits in reciprocal units. Review residuals and spectral recovery strength; missing directions and suppressed frequencies are not recovered geology. This is not the vendor infinite-prism model or cgs susceptibility. No automatic IGRF removal, terrain correction or field certification.

m_hat(k) = conj(K) d(k) / (|K|² + lambda²)

Parameters / quantities: kind, top_depth_m, thickness_m, background, regularization_response, max_inverse_gain, minimum_wavelength_m

Context sources:

- [Harmonica prism gravity: units and coordinate conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)
- [Harmonica prism magnetic field: conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_magnetic.html)

### Phase, texture and feature paths

Basic log-Gabor/Riesz attributes use explicit wavelengths, bandwidth and noise threshold; phase alignment is unweighted and is not full phase congruency or CET equivalence. Quantized entropy depends on window, range and bins. Axial orientation entropy also depends on bin origin and valid support. Skeleton paths require an explicit Boolean mask, projected metre spacing and the centre of the first pixel. Branches and cycles retain pixel geometry without smoothing or gap bridging. These are mathematical features, not interpreted faults or lithologies.

H = -sum(p log2 p)

Parameters / quantities: wavelengths_m, sigma_on_f, noise_threshold, value_range, bin_origin_degrees, feature_mask, origin_xy

Context sources:

- [Monogenic phase attributes](https://peterkovesi.github.io/ImagePhaseCongruency.jl/stable/functions/)
- [scikit-image morphology](https://scikit-image.org/docs/stable/api/skimage.morphology.html)

### Interpolation choices and support

IDW depends on distance power and neighbour selection; nearest neighbour does not add smoothness. Global thin-plate splines and local TPS approximations have different support and cost. The experimental multilevel minimum-curvature solver is a separate method, not a promise of equivalence to a proprietary gridder. Sinc interpolation needs defensible sampling and support. Test against held-out spatial blocks and report distant extrapolation. A smaller cell improves rendering, not acquisition resolution.

IDW: z(x) = sum(w_i z_i)/sum(w_i); w_i = distance_i^(-p)

Parameters / quantities: METHOD, CELL_SIZE, NEIGHBORS, SEARCH_RADIUS, POWER, SMOOTHING

Context sources:

- [Verde spatial cross-validation](https://www.fatiando.org/verde/latest/tutorials/model_selection.html)

### Acquisition corrections and timing

Signed lag changes where an observation is placed along time/trajectory; document its sign and estimate it from repeatable evidence. Interpolate a base station only within accepted time support. Heading coefficients model direction-dependent acquisition response and must not absorb geological differences. Moving gravity needs a consistent drift epoch, explicit tide correction and declared Eötvös sign. Preserve corrected and uncorrected channels. Resampling, gap interpolation and coordinate rotations are separate recorded steps.

Parameters / quantities: LAG, BASE_TIME, BASE_VALUE, HEADING, DRIFT, TIDE, EOTVOS_MODE

Context sources:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### Tie-line leveling and microleveling

Crossovers constrain differences between traverse and tie lines. Examine network connectivity, intersection distance and residuals before fitting constant or polynomial line corrections. Do not fit an unconstrained network as if it had an absolute datum. Directional microleveling targets residual corrugation after primary corrections and crossover adjustment. Compare the removed correction with geological amplitude; inspect both flight-parallel and cross-flight structures. A cleaner image alone is insufficient evidence that leveling improved the measurements.

Parameters / quantities: LINE_ID, LINE_TYPE, TIE_VALUES, POLYNOMIAL_DEGREE, AZIMUTH

Context sources:

- [Minty (1991): Simple Micro-Levelling for Aeromagnetic Data](https://doi.org/10.1071/EG991591)

Chapter context:

- [Verde spatial cross-validation](https://www.fatiando.org/verde/latest/tutorials/model_selection.html)
- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)
- [Monogenic phase attributes](https://peterkovesi.github.io/ImagePhaseCongruency.jl/stable/functions/)
- [scikit-image morphology](https://scikit-image.org/docs/stable/api/skimage.morphology.html)

## FFT filters and parameter selection

Wavelengths and continuation heights use grid CRS units. Compare several cutoffs tied to survey spacing and target scale. Butterworth order controls transition sharpness; a higher order is not inherently better. Mean/plane removal, reflected padding and taper change edge behaviour; record them and compare the interior separately. Upward continuation attenuates short wavelengths. Downward continuation amplifies noise and requires stabilization and gain limits. Restore the removed trend only when physically appropriate. Apply spatial circular median to isolated spikes; it is nonlinear and not a Fourier transfer function. Do not treat database storage as a numerical domain.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

H_up(k, h) = exp(-|k| h); k in rad / length; h > 0

### Detrending, padding and taper

Removing a mean or plane changes the zero/low-wavenumber content. Reflected padding reduces jumps but creates an artificial extension; taper weights that extension before the FFT. The inverse operation crops to the original geometry and restores its mask. Restoring a removed trend is suitable for some smoothing tasks, but generally not for a derivative. Compare border and interior statistics separately and retain the conditioning parameters in the recipe.

k = 2 pi / wavelength; Nyquist per axis = pi / spacing

Parameters / quantities: FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND

Context sources:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

### Butterworth, ideal and cosine bands

The spatial Butterworth kernel is defined directly in radial wavenumber; do not confuse it with the digital time-series design. Long and short cutoff wavelengths correspond inversely to wavenumber. A bandpass multiplies low/high responses; rejection complements that band. Ideal edges create ringing; smooth transitions trade selectivity for less ringing. Compare cutoff and order, not only colour stretch. A Gaussian smoother has a different transfer shape and must not be labelled the same filter.

B_LP = [1+(k/kc)^(2n)]^(-1/2); B_HP = [1+(kc/k)^(2n)]^(-1/2)

Parameters / quantities: WAVELENGTH, LONG_WAVELENGTH, SHORT_WAVELENGTH, ORDER

Context sources:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

### Continuation and inverse derivatives

Upward continuation is a low-pass operation on a potential field. Stabilized downward continuation combines exponential gain, a cap and smoothing; the cap changes the ideal continuation operator. Integrating a horizontal derivative requires a policy at its zero-wavenumber axis; a constant cannot be recovered from derivatives alone. Document the floor or stabilization and inspect spectral amplification. Pseudogravity is conditional on magnetization and scaling, not an absolute gravity observation.

H_up = exp(-|k|h); H_down = min(exp(|k|h),Gmax) B_LP; Ix = 1/(i kx)

Parameters / quantities: HEIGHT, MAX_GAIN, LOWPASS_WAVELENGTH, ORDER

Context sources:

- [Harmonica upward continuation](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.upward_continuation.html)

### Circular median, smoothing and gain

Circular median selects a neighbourhood in pixel distance; its radius is not a physical wavelength. Preserve original missing cells and inspect how isolated targets change. Nine-point smoothing repeatedly applies a normalized local kernel; iteration count changes effective smoothing. Automatic gain control rescales local amplitudes and therefore cannot preserve a calibrated magnetic or gravity scale. Keep a quantitative branch before median clipping or gain enhancement. These nonlinear/adaptive products cannot be combined as a single FFT transfer.

Parameters / quantities: RADIUS, PASSES, GAIN_CAP, RMS_FLOOR

Context sources:

- [SciPy multidimensional image processing](https://docs.scipy.org/doc/scipy/reference/ndimage.html)
- [scikit-image morphology](https://scikit-image.org/docs/stable/api/skimage.morphology.html)

Chapter context:

- [Harmonica upward continuation](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.upward_continuation.html)
- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

## Magnetic derivatives and field direction

DX and DY depend on coordinate orientation; DZ depends on the vertical sign convention. Derivatives amplify short-wavelength noise. Compare horizontal gradient, total gradient amplitude and tilt with the unfiltered anomaly. RTP and RTE require inducing-field direction and an assumed magnetization direction. IGRF also requires date and altitude; do not silently substitute terrain elevation for sensor altitude. Low-inclination RTP may be unstable even with a smooth-looking map. Remanence can invalidate induced-only interpretation. An edge maximum is not proof of a fault, depth or lithology; compare independent geological observations.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

HGM = sqrt(DX² + DY²); TGA = sqrt(DX² + DY² + DZ²); tilt = atan2(DZ, HGM)

### Components and gradient integration

Component conversion assumes a source-free harmonic half-space. Total field means a small-anomaly projection, not an exact vector norm. Input and output components and output mean are explicit. Gradient reconstruction uses east, north and upward derivatives in nT/m with positive relative component weights. The reference mean is prescribed. Gain limits, damping, unresolved directions and excluded even-grid Nyquist axes must be reviewed. A radial gain table uses angular wavenumbers in rad/m, including an explicit DC gain; its final gain is retained beyond the last knot.

dT/dz_up = -k T; T(0) = prescribed mean

Parameters / quantities: input_component, output_component, output_mean_nt, gradient_up, reference_mean_nt, wavenumbers_rad_per_m

Context sources:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### Compact dipole fitting

Positions are ENU metres and moments A·m². Source count, seeds, independent data errors, bounds and minimum sensor distance are prescribed. Fit vector components or a linear total-field projection. A converged optimizer with deficient Jacobian rank is not a successful identifiable fit; local covariance is then unavailable. Review active bounds and residuals. The approximation does not identify target shape, UXO class or explosive content.

B = mu0/(4 pi) [3 r (m·r)/r^5 - m/r^3]

Parameters / quantities: observation_xyz, moments_a_m2, minimum_distance_m, rank_tolerance

Context sources:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)
- [SimPEG](https://docs.simpeg.xyz/latest/)

### Spatial and Fourier derivatives

DX and DY use coordinate spacing, not pixel indices. The first upward derivative changes sign if a downward-positive convention is used. FFT differentiation assumes a regular horizontal observation surface and periodic extension after preprocessing. Compare first and second derivatives separately: a second derivative amplifies high wavenumbers more strongly. Confirm derivative units are field per length, or per length squared. Masked borders and interpolated holes need independent review.

Dx: i kx; Dy: i ky; Dz_up: -|k|; Dzz: |k|²

Parameters / quantities: BAND, ORDER, spacing, padding_cells

Context sources:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### Gradient and angular attributes

Horizontal gradient and total gradient amplitude have physical derivative units; tilt and related normalized attributes are angles or dimensionless ratios. A directional horizontal derivative must state its azimuth reference and coordinate convergence. Normalization can make weak noisy areas visually strong, so inspect an amplitude mask beside angular products. Peaks can shift with source geometry and interference. Never turn an angular threshold into a fault classification without independent evidence.

HGM = sqrt(Tx²+Ty²); TGA = sqrt(Tx²+Ty²+Tz²); tilt = atan2(Tz,HGM)

Parameters / quantities: AZIMUTH, gradient_x, gradient_y, gradient_z

Context sources:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### RTP, RTE and IGRF direction

Distinguish inducing-field direction from source magnetization. Date, altitude and geographic position determine an IGRF direction, not the remanent component. Inspect low-inclination gain stabilization and compare nearby direction assumptions. A transformation does not correct survey leveling or a wrong main-field subtraction. Keep the original anomaly and record manual versus model-derived directions. General direction transforms and pseudogravity remain conditional on the assumed magnetization model.

I > 0: downward; D: clockwise from geographic North

Parameters / quantities: INCLINATION, DECLINATION, MAX_GAIN, SURVEY_YEAR, SURVEY_MONTH, SURVEY_DAY

Context sources:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

Chapter context:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

## Gravity corrections and isostasy

Distinguish observed gravity, gravity disturbance and anomalies. Record latitude, height reference, drift epoch, tides, motion correction and reduction density. Check the sign of every correction before adding it. Terrain correction, Bouguer slab and spherical curvature are not interchangeable. Published complete Bouguer anomalies should not be corrected again as raw observations. Airy isostasy assumes local compensation; elastic flexure permits regional support and requires elastic parameters and boundaries. Density and reference-depth sensitivity should accompany interpretation. A residual is model-dependent, not automatically a measured crustal mass excess.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

CBA = SBA + terrain - Bullard B

### Adaptive finite-DEM attraction

The model uses explicit ENU stations, a complete regular DEM and a prescribed reference plane. Rock above that plane has crust density; material below has water-minus-crust contrast. Near cells retain exact prism kernels. Distant groups preserve signed mass and centroid, and the largest truncation bounds are refined until their sum meets the requested mGal tolerance. This bound excludes floating-point, terrain, density, vertical datum, Earth curvature and missing outer-terrain errors. Output is attraction, not a complete terrain, Bouguer or tide correction. Tight tolerances can still require a dense exact sum; work budgets do not bound RAM or runtime.

E_group <= 12 G 10^5 J / (d - R)^4; d > R

Parameters / quantities: observation_xyz, reference_elevation_m, absolute_tolerance_mgal, leaf_cells, max_prism_evaluations

Context sources:

- [Barnes and Hut: hierarchical force calculation](https://doi.org/10.1038/324446a0)
- [Harmonica prism gravity: units and coordinate conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)

### Normal gravity and height reduction

The local GRS80 algorithm evaluates Somigliana gravity at reference-ellipsoid surface latitude. Its latitude subtraction is not the same as evaluating a normal field at sensor height. The configurable linear free-air term is a separate approximation. Record which reference surface each term uses before calling the result a disturbance or anomaly. A geometric elevation raster must not silently be interpreted as orthometric height. Do not combine incompatible published reduction conventions.

gamma(phi) = gamma_e (1+k sin²(phi))/sqrt(1-e² sin²(phi)); FAA = g_obs-gamma(phi)+a h

Parameters / quantities: ELEVATION, FREE_AIR_GRADIENT, INPUT, BAND

Context sources:

- [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html)

### Bouguer slab, terrain and curvature

The infinite slab removes an idealized mass between a datum and the station. Terrain prisms handle relief relative to the chosen reference; Bullard B accounts for spherical curvature under the implemented land convention. These are distinct signed corrections, not interchangeable filters. Density changes every mass term and must be consistent across the chain. Inspect DEM coverage, receiver clearance, prism singularities and discretization sensitivity. A terrain correction made with incomplete relief is not automatically complete Bouguer gravity.

slab = 2 pi G rho h; SBA = FAA-slab; CBA = SBA+terrain-BullardB

Parameters / quantities: CRUST_DENSITY, WATER_DENSITY, CLEARANCE, DEM, MAX_CELLS

Context sources:

- [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html)

### Airy compensation and elastic support

Airy depth uses a crust/mantle density contrast and reference Moho; its output is an assumed compensating interface, not an observed seismic Moho. Compute its gravity effect before forming an isostatic residual. The elastic plate kernel instead responds to a prescribed pressure load with periodic boundaries. Mean load, domain size and elastic constants must be declared. A thickness scan fits displacement under fixed assumptions; it does not infer geological uncertainty or gravity automatically.

D = E Te³/[12(1-nu²)]; w(k) = q(k)/(D |k|⁴ + delta_rho g)

Parameters / quantities: REFERENCE_MOHO, CRUST_DENSITY, MANTLE_DENSITY, elastic_thickness_m, load_pa

Context sources:

- [GMT grdflexure: elastic and rheological plate models](https://docs.generic-mapping-tools.org/6.5/supplements/potential/grdflexure.html)
- [Harmonica prism gravity: units and coordinate conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)

Chapter context:

- [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html)
- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)
- [Barnes and Hut: hierarchical force calculation](https://doi.org/10.1038/324446a0)

## Radiometry and detector calibration

Separate counts, count rates and calibrated K/eU/eTh. Correct raw observations with survey-specific dead-time, background, stripping, height and sensitivity coefficients; never reuse nominal coefficients blindly. Ratios need denominator guards and compatible masks. Inspect radon, moisture and clearance. Equivalent uranium assumes decay-chain conditions; it is not direct uranium chemistry. Ternary colours are a display, not independent measurements. Keep uncertainty and calibration residuals with the products.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

### Raw counts versus calibrated products

Follow the detector-specific correction chain and keep the original count channels. Non-paralyzable dead time, background subtraction, altitude normalization and spectral stripping act on different quantities. A calibrated concentration grid must not receive the raw-count chain again. Inspect negative corrected values rather than clipping them silently. Height response and sensitivity coefficients require acquisition/calibration evidence. Equivalent uranium and thorium rely on decay-series assumptions; ratios and dose products need compatible units and masks.

Parameters / quantities: DEAD_TIME, BACKGROUND, HEIGHT, ATTENUATION, SENSITIVITY, RESPONSE_MATRIX

Context sources:

- [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf)

### Spectral calibration and covariance

Use several calibration peaks to inspect energy nonlinearity. Rebinning distributes fractional counts and correlates output bins; diagonal variances alone are insufficient. Window overlap also creates covariance. NASVD and MNF need explicit rank/noise assumptions and may produce negative reconstructions. Calibration uncertainty is shared across survey points even when only marginal covariance is returned. Validate calibration on independent records and retain component names, units and response-matrix ordering.

E = offset+gain channel; Cov(Ax) = A Cov(x) Aᵀ

Parameters / quantities: channel_peaks, energy_peaks, input_edges, output_edges, rank, rate_covariance

Context sources:

- [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf)

Chapter context:

- [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf)

## Euler, Werner, SPI and spectral depth

Source-depth estimates depend on an assumed source class, sampling and background. For Euler, vary structural index, window size, derivative method and acceptance limits. Reject poorly conditioned windows and inspect clustered solutions rather than plotting every candidate as a source. Profile Werner/SPI results are not arbitrary 3D inversions. Spectral slopes require a declared frequency interval and statistical support; mixed source populations and edges can bias depth. Compare against synthetic cases, other windows and geology. None of these techniques uniquely determines a body boundary or reserves.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

(x-x0) Tx + (y-y0) Ty + (z-z0) Tz = N (B-T)

### Euler acceptance and profile geometry

Use derivatives in consistent coordinate units and upward-positive z. A structural index of zero cannot identify an arbitrary background field; the window implementation estimates the identifiable contact offset instead. Window conditioning, residual and depth-error criteria are independent acceptance tests. Euler profiles constrain a locally two-dimensional source and do not solve along-strike location. Keep rejected-window counts and compare structural indices, heights and window sizes. Solutions outside the observation domain need explicit review.

(x-x0)Tx+(y-y0)Ty+(z-z0)Tz = N(B-T)

Parameters / quantities: structural_index, window_size, stride, max_condition, max_relative_depth_error, depth_bounds

Context sources:

- [Harmonica Euler deconvolution](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.EulerDeconvolution.html)

### Werner, SPI and spectral fitting

Werner assumes a thin-sheet profile with a declared interference polynomial and level observations. SPI uses local-wavenumber peaks; off-peak samples are not independent depth picks. Its geometry factors differ for contacts, sheets and horizontal cylinders. Spectral depth fitting uses a selected wavenumber interval and geometrical exponent; fitting a line everywhere ignores mixed source populations. Compare peaks, residuals and interval sensitivity. Profile facades do not turn these assumptions into general three-dimensional source reconstruction.

K = abs((Tx Txz-Tz Txx)/(Tx²+Tz²)); SPI depth = (index+1)/K at peaks

Parameters / quantities: background_degree, source_model, peak_distance, fit_range, geometry_exponent

Context sources:

- [Ku and Sharp (1983): Werner deconvolution](https://doi.org/10.1190/1.1441505)
- [Thurston and Smith (1997): SPI method](https://doi.org/10.1190/1.1444190)
- [Spector and Grant (1970): statistical aeromagnetic models](https://doi.org/10.1190/1.1440092)

Chapter context:

- [Harmonica Euler deconvolution](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.EulerDeconvolution.html)

## Inversion, residuals and sensitivity

Choose the physical property, forward operator, mesh, uncertainties, bounds and regularization explicitly. Separate sensor positions from the topographic surface. Repeat with altered cell size, depth, padding, starting/reference model and regularization weight. Inspect observed, predicted and residual data by line and spatial location, not only a scalar misfit. Convergence does not remove non-uniqueness. A cross-gradient promotes structural similarity, not a fixed density–susceptibility relationship. Optional engines and versions belong in provenance. A solver that reaches an iteration limit must not be labelled a converged solution.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

phi(m) = phi_d(m) + beta phi_m(m); r_i = (d_pred_i - d_obs_i) / sigma_i

### Density, susceptibility and MVI

Density inversion estimates a contrast relative to the reduction/reference model. Scalar magnetic inversion assumes a magnetization direction and susceptibility parameterization; vector inversion permits directional components but increases ambiguity. Receiver elevation is not the active-cell topography by default. Mesh padding, depth extent and physical bounds affect recovered structure. Check numerical convergence separately from geological plausibility and compare multiple parameterizations. Exported VTK geometry is a numerical mesh, not an independently mapped geological boundary.

Parameters / quantities: CELL_SIZE, MODEL_DEPTH, MESH_TYPE, TOPOGRAPHY, LOWER_BOUND, UPPER_BOUND

Context sources:

- [SimPEG](https://docs.simpeg.xyz/latest/)
- [SimPEG L2 data misfit](https://docs.simpeg.xyz/latest/content/api/generated/simpeg.data_misfit.L2DataMisfit.html)

### Spherical magnetic vector inversion

A smooth Cartesian initialization is refined in amplitude and periodic angles. Amplitude and angular gradient norms are independent choices; sparse norms require IRLS. Magnitude caps are distinct from Cartesian component limits. Internal elevation is positive upward and azimuth starts at East; outputs retain ENU Cartesian effective susceptibility. Zero amplitude has undefined direction. Compare noise-weighted fit, inner precision and model recovery separately. Geometric support and references are explicit assumptions, not information recovered automatically from magnetic data. Coherent angles do not resolve every depth or volume ambiguity.

m = a[cos(theta)cos(phi), cos(theta)sin(phi), sin(theta)]

Parameters / quantities: mvi_parameterization, mvi_cartesian_iterations, mvi_amplitude_max, mvi_angle_norms, regularization_norms, irls_iterations

Context sources:

- [Fournier, Heagy and Oldenburg (2020), Sparse magnetic vector inversion in spherical coordinates](https://doi.org/10.1190/geo2019-0244.1)
- [SimPEG](https://docs.simpeg.xyz/latest/)

### Uncertainty, IRLS and joint structure

Data uncertainty controls weighting and must reflect measurement/model errors, not an arbitrary target fit. Regularization weight balances fit and model assumptions. Sparse norms and IRLS alter that problem; a covariance derived for a fixed linear Gaussian system does not automatically apply afterward. A cross-gradient favours aligned property gradients without enforcing a density/susceptibility ratio. Test coupling weights, residual distributions and reference models. Keep nonconvergence explicit and do not replace sensitivity experiments with a single attractive model.

phi = phi_d+beta phi_m; cross-gradient = grad(m1) × grad(m2)

Parameters / quantities: UNCERTAINTY, LP_NORM, IRLS_ITERATIONS, beta, regularization, reference

Context sources:

- [SimPEG](https://docs.simpeg.xyz/latest/)

Chapter context:

- [SimPEG L2 data misfit](https://docs.simpeg.xyz/latest/content/api/generated/simpeg.data_misfit.L2DataMisfit.html)
- [SimPEG](https://docs.simpeg.xyz/latest/)

## DC resistivity, IP and self potential

DC resistivity needs electrode geometry, current polarity, potential difference and a compatible geometric factor. Apparent resistivity is not a direct voxel property. Inspect reciprocal error, contact problems and topography. IP and complex conductivity need frequency/time and sign conventions; chargeability units are not interchangeable. Self potential needs a reference electrode and sign; fit source geometry and boundary conditions separately from interpretation. Layered responses assume lateral invariance. PDE forward modelling and inversion require mesh and boundary sensitivity. These experimental Core entries are not a complete instrument-processing system.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

rho_a = K delta_V / I

### ABMN geometry, IP and polarity

ABMN stores electrode indices, not distances; remote B/N uses the documented sentinel. Half-space geometric factors require a compatible electrode plane. Preserve voltage/current signs and flag negative apparent resistivity instead of taking an absolute value. Reciprocal QC distinguishes reversed quadrupoles from same-orientation repeats. Integrated IP is a normalized gate average, not an unnormalized time integral. Cole–Cole resistivity requires its stated phasor convention; conductivity-model parameters are not interchangeable by renaming. Temporal inversion also supports prescribed finite signed current histories, assuming zero polarization before the first event. Supply every switch and choose DC or final pre-switch primary normalization; data and errors are V/V. Stack modeling requires selected off-periods, cycle weights and an explicit mean of ratios or ratio of sums convention. It fits already-stacked V/V data without inferring instrument processing or noise reduction. Unknown prehistory, receiver filters and induction require separate modeling.

K_half = 2 pi/(1/AM-1/BM-1/AN+1/BN); rho_a = K V/I

Parameters / quantities: electrodes, abmn, space, current_a, voltage_v, gate_s

Context sources:

- [SimPEG DC resistivity](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.static.resistivity.html)
- [Spectral induced polarization: frequency domain versus time domain laboratory data, Appendix C](https://doi.org/10.1093/gji/ggab071)
- [Understanding the Fate of H2S Injected in Basalts by Means of Time-Domain Induced Polarization Geophysical Logging](https://doi.org/10.1029/2023JB028316)

### PDE meshes and self-potential sources

Use explicit mesh geometry, active regions, source/receiver positions and boundary assumptions. For prescribed-source SP, the local implementation uses insulating outer faces and individually neutral source templates. That is not an infinite half-space or an automatic electrokinetic interpretation. A source-amplitude fit holds conductivity and geometry fixed. Check electrode distance from boundaries, mesh refinement and reference electrode. Conditional source covariance excludes uncertainty in conductivity, source geometry and hydraulic coupling.

Parameters / quantities: mesh_widths, mesh_origin, conductivity_s_m, source_templates_a_m3, reference_m

Context sources:

- [SimPEG DC resistivity](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.static.resistivity.html)

Chapter context:

- [SimPEG DC resistivity](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.static.resistivity.html)

## FDEM, TEM and magnetotellurics

Record source/receiver geometry, frequency or waveform, component, orientation and normalization. FDEM in-phase/quadrature signs and ppm versus absolute fields matter. TEM gates are finite time integrals; use the recorded waveform and correct time zero. Exclude contaminated or negative-time gates explicitly. MT impedance requires declared electric/magnetic units and Fourier convention before apparent resistivity and phase. A 1D layered earth cannot represent arbitrary lateral structure. Repeat conductivity fits across starting models and bounds; an excellent curve fit alone does not establish depth resolution or geological uniqueness.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

rho_a = |Z_EH|² / (mu0 omega); omega = 2 pi f

### Layered and three-dimensional EM

The layered model uses finite-layer thicknesses followed by a half-space. Source moment, orientation and receiver separation are explicit. Secondary magnetic field in tesla must not be interpreted as ppm without a justified primary normalization. Three-dimensional zone fitting is a bounded local parameter fit with a counted forward budget, not unlimited voxel inversion. Test mesh extent and initial conductivities; LU memory can exceed simple work estimates. Correlated real/imaginary errors need the declared covariance ordering.

Parameters / quantities: frequency_hz, thicknesses_m, source_m, receiver_m, moment_a_m2, data_covariance_t2

Context sources:

- [SimPEG electromagnetic methods](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.html)

### TEM gates and MT impedance

Ideal step-off, finite ramps and recorded transmitter waveforms are different source histories. Integrate finite TEM gates rather than sampling only their centres; test quadrature order. MT impedance must distinguish E/H ohms from E/B field units. Preserve xy/yx signs and do not fold phase silently. The phase tensor can remove an ideal real left-side galvanic distortion, but does not recover apparent-resistivity amplitude or static shift. Layered fits keep thicknesses fixed unless explicitly parameterized otherwise.

rho_a = |Z_EH|²/(mu0 omega); Phi = Re(Z)^(-1) Im(Z)

Parameters / quantities: gates_s, waveform_times_s, quadrature_order, impedance_ohm, thicknesses_m

Context sources:

- [SimPEG electromagnetic methods](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.html)

Chapter context:

- [SimPEG electromagnetic methods](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.html)

## GPR, waveforms and passive seismic

Confirm the sample axis, interval, time zero and trace spacing before filtering. Dewow removes a local time mean; background subtraction removes shared trace content and can also suppress real horizontal reflectors. Bandpass limits must respect Nyquist. Gain changes amplitudes and is not a physical inversion. GPR depth needs a defensible velocity; migration requires the correct geometry and assumptions. For passive spectra, inspect windows, transients, component orientation and smoothing. An H/V peak is not automatically a unique layer thickness. Keep a raw-amplitude branch and compare processed traces, not just enhanced images.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

f_Nyquist = 1 / (2 dt); depth_GPR = velocity time_two_way / 2

### Trace conditioning, picks and depth

Trace arrays use trace-by-time ordering. Dewow requires an odd window fitting the record; background removal acts across traces, not time. Temporal Butterworth filtering must stay below Nyquist and short records need enough samples for its boundary handling. Time-zero shifts, gain and migration each change different information. NMO can stretch signals; mask over-stretched samples and report fold. STA/LTA picks and H/V peaks are indicators to review, not automatic event classifications or unique geological depths.

0 < f_low < f_high < 1/(2 dt); depth = v t_two_way / 2

Parameters / quantities: traces, dt_s, window_samples, low_hz, high_hz, maximum_stretch

Context sources:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

Chapter context:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

## Borehole logs and petrophysical transforms

Read LAS curve mnemonics, units, null values, depth direction and well metadata before selecting curves. Keep measured depth distinct from true vertical depth. Resampling and depth shifts must preserve null intervals and be documented per curve. Petrophysical transforms require formation-specific assumptions, fluid properties and calibration. Archie-type equations are not universal clay corrections. Do not infer porosity units from magnitudes alone. Compare transformed curves with original logs and independent laboratory data. Exporting updated LAS must preserve unmodified curves and source metadata; export success does not validate the geological model.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

### LAS units, trajectory and resampling

LAS curve samples keep original units; the dedicated depth output is converted only from explicit metre/foot units or a recorded override. Updating curve values does not authorize changing the depth column. Trajectory reconstruction needs collar coordinates, measured depths and orientation conventions. Do not confuse measured and true vertical depth. Preserve nulls and reversals for QC before resampling. Depth shifts must reference a defensible matching interval, not merely maximize agreement between unrelated formations.

international foot = 0.3048 m

Parameters / quantities: text, depth_unit_override, curve_values, collar_enu_m, measured_depth_m

Context sources:

- [lasio documentation](https://lasio.readthedocs.io/en/latest/)
- [Taylor (1972): well surveying calculations](https://doi.org/10.2118/3362-PA)

Chapter context:

- [lasio documentation](https://lasio.readthedocs.io/en/latest/)

## Validation, provenance and safe conclusions

Separate unit tests, numerical reference comparisons, GUI tests and field validation. A synthetic pass does not establish commercial-software equivalence. Archive the recipe, input versions or checksums, units, parameters, library versions and residual statistics. Module checksums do not cover transitive dependencies. Distinguish completed, failed, cancelled and not-converged jobs. Output-size guards do not limit solver RAM or runtime. Cancellation may wait for a kernel checkpoint. Review sensitivity to defensible parameter ranges and document unresolved discrepancies. Keep private surveys and acquisition details outside published documentation and packages.

Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.

Chapter context:

- [SimPEG](https://docs.simpeg.xyz/latest/)

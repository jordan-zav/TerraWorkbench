# Actual QGIS provider catalogue

[English](qgis_en.md) · [Español](qgis_es.md) · [Português](qgis_pt.md)

[Contents](../../manuals/en/README.md)

QGIS 3.44.12-Solothurn · 95 · en

IDs and parameters are technical identifiers. Opening a form does not execute or validate a calculation.

| ID | Display name | Parameters |
| --- | --- | --- |
| terraworkbench:airy_isostatic_anomaly | 10 Airy isostatic residual anomaly | INPUT, BAND, OUTPUT, ELEVATION, ELEVATION_BAND, REGIONAL, WATER, DENSITY_WATER, BLOCK_SIZE, MAX_INTERACTIONS, REFERENCE_DEPTH, DENSITY_CRUST, DENSITY_MANTLE, MAX_CELLS |
| terraworkbench:airy_isostatic_anomaly_fft | 11 Airy isostatic residual (periodic FFT) | INPUT, BAND, OUTPUT, REGIONAL, WATER, REFERENCE_DEPTH, DENSITY_CRUST, DENSITY_MANTLE, DENSITY_WATER, HEIGHT, TOLERANCE, MAX_CELLS |
| terraworkbench:airy_isostatic_moho | 09 Airy isostatic Moho depth | INPUT, BAND, OUTPUT, REFERENCE_DEPTH, DENSITY_CRUST, DENSITY_MANTLE |
| terraworkbench:automatic_channel_lag | Automatic channel-lag estimation | INPUT, TIME_FIELD, RESPONSE_FIELD, REFERENCE_FIELD, MAXIMUM_LAG, LAG_STEP, USE_DERIVATIVE, OUTPUT, CURVE |
| terraworkbench:automatic_gain_control | Automatic gain control (local RMS) | INPUT, BAND, OUTPUT, WINDOW, FLOOR, MAX_GAIN |
| terraworkbench:base_station_quality_control | Magnetic base-station QC | INPUT, TIME_FIELD, VALUE_FIELD, UNWRAP, MAX_GAP, SPIKE_WINDOW, SPIKE_SIGMA, MAX_RATE, MAX_DRIFT, OUTPUT, SUMMARY |
| terraworkbench:bouguer_correction | Bouguer correction | INPUT, BAND, OUTPUT, DENSITY_CRUST, DENSITY_WATER |
| terraworkbench:bullard_b_curvature | 05 Earth curvature correction — Bullard B | INPUT, BAND, OUTPUT, DENSITY_CRUST |
| terraworkbench:butterworth_bandpass | Butterworth band-pass | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH, ORDER |
| terraworkbench:butterworth_highpass | Butterworth high-pass | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, WAVELENGTH, ORDER |
| terraworkbench:butterworth_lowpass | Butterworth low-pass | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, WAVELENGTH, ORDER |
| terraworkbench:butterworth_notch | Butterworth notch (band reject) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH, ORDER |
| terraworkbench:circular_median | Circular median (2D disk) | INPUT, BAND, OUTPUT, RADIUS |
| terraworkbench:complete_bouguer_anomaly | 08 Complete Bouguer anomaly — land | INPUT, BAND, OUTPUT, ELEVATION, ELEVATION_BAND, TERRAIN, TERRAIN_BAND, DENSITY_CRUST, DENSITY_WATER, VERTICAL_GRADIENT |
| terraworkbench:correct_magnetic_survey_lines | Magnetic line correction — base, lag, heading and despike | INPUT, VALUE_FIELD, TIME_FIELD, LINE_FIELD, BASE, BASE_TIME_FIELD, BASE_VALUE_FIELD, SIGNED_LAG_SECONDS, HEADING_COSINE, HEADING_SINE, HAMPEL_RADIUS, HAMPEL_THRESHOLD, OUTPUT |
| terraworkbench:correct_moving_gravity_survey | Moving gravity correction — drift, tide field and Eötvös | INPUT, VALUE_FIELD, TIME_FIELD, LINE_FIELD, TIDE_FIELD, DRIFT_RATE, EOTVOS_MODE, OUTPUT |
| terraworkbench:cosine_rolloff_highpass | Cosine roll-off high-pass | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH, DEGREE |
| terraworkbench:cosine_rolloff_lowpass | Cosine roll-off low-pass | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH, DEGREE |
| terraworkbench:crossover_line_leveling | Crossover QC and tie-line leveling | INPUT, VALUE_FIELD, LINE_FIELD, LINE_TYPE_FIELD, ORDER_FIELD, TIE_VALUES, OUTLIER_SIGMA, CORRECTION_ORDER, HIGH_ORDER_DAMPING, CORRECTED, CROSSOVERS, CORRECTIONS |
| terraworkbench:derivative_easting | Derivative — easting (spatial finite difference) | INPUT, BAND, OUTPUT, ORDER |
| terraworkbench:derivative_northing | Derivative — northing (spatial finite difference) | INPUT, BAND, OUTPUT, ORDER |
| terraworkbench:derivative_upward | Derivative — upward (FFT) | INPUT, BAND, OUTPUT, ORDER |
| terraworkbench:directional_cosine_pass | Directional cosine — pass | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, AZIMUTH, DEGREE |
| terraworkbench:directional_cosine_reject | Directional cosine — reject | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, AZIMUTH, DEGREE |
| terraworkbench:downward_continuation | Downward continuation — stabilized | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, HEIGHT, LOWPASS_WAVELENGTH, MAX_GAIN, ORDER |
| terraworkbench:drape_dem_quality_control | Drape and terrain-clearance QC against DEM | INPUT, ALTITUDE_FIELD, DEM, BAND, TARGET, TOLERANCE, MINIMUM, MAXIMUM, OUTPUT, SUMMARY |
| terraworkbench:equivalent_source_continuation | Equivalent sources — fit and continue regular grid | INPUT, BAND, OUTPUT, SOURCE_DEPTH, DAMPING, TARGET_HEIGHT, BLOCK_SIZE, MAX_CELLS, MAX_MATRIX_ELEMENTS, HOLDOUT_PERCENT |
| terraworkbench:fft_derivative_easting | Derivative — easting (FFT) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, ORDER |
| terraworkbench:fft_derivative_northing | Derivative — northing (FFT) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, ORDER |
| terraworkbench:fft_derivative_upward | Derivative — upward (FFT) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, ORDER |
| terraworkbench:field_direction_transform | Transform magnetic field direction | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, FIELD_MODE, INCLINATION, DECLINATION, USE_METADATA_DATE, YEAR, MONTH, DAY, ALTITUDE_KM, MAGNETIZATION_INCLINATION, MAGNETIZATION_DECLINATION, MAX_GAIN, TARGET_INCLINATION, TARGET_DECLINATION |
| terraworkbench:flight_line_quality_control | Flight-line QC — navigation, clearance and channel rate | INPUT, TIME_FIELD, LINE_FIELD, VALUE_FIELD, CLEARANCE_FIELD, MAX_TIME_GAP, MAX_SPACING, MIN_SPEED, MAX_SPEED, MAX_TURN, MIN_CLEARANCE, MAX_CLEARANCE, MAX_VALUE_RATE, OUTPUT, SUMMARY |
| terraworkbench:free_air_anomaly | 04 Free-air anomaly — observed gravity + elevation | INPUT, BAND, OUTPUT, ELEVATION, ELEVATION_BAND, VERTICAL_GRADIENT |
| terraworkbench:free_air_correction | 03 Free-air correction | INPUT, BAND, OUTPUT, VERTICAL_GRADIENT |
| terraworkbench:gaussian_highpass | Gaussian high-pass filter | INPUT, BAND, OUTPUT, WAVELENGTH |
| terraworkbench:gaussian_lowpass | Gaussian low-pass filter | INPUT, BAND, OUTPUT, WAVELENGTH |
| terraworkbench:grav_dx | 01 [SPATIAL] DX — First horizontal derivative X | INPUT, BAND, OUTPUT |
| terraworkbench:grav_dy | 02 [SPATIAL] DY — First horizontal derivative Y | INPUT, BAND, OUTPUT |
| terraworkbench:grav_dz | 03 [FFT] DZ — First vertical derivative | INPUT, BAND, OUTPUT |
| terraworkbench:grav_dz2 | 04 [FFT] DZ2 — Second vertical derivative | INPUT, BAND, OUTPUT |
| terraworkbench:grav_regional | 06 [FFT] Regional — Gaussian low-pass | INPUT, BAND, OUTPUT, WAVELENGTH |
| terraworkbench:grav_residual | 07 [FFT] Residual — Field minus upward continuation | INPUT, BAND, OUTPUT, HEIGHT |
| terraworkbench:grav_tga | 10 [MIXED] TGA — Total gradient amplitude | INPUT, BAND, OUTPUT |
| terraworkbench:grav_thdr | 08 [SPATIAL] THDR — Total horizontal derivative | INPUT, BAND, OUTPUT |
| terraworkbench:grav_tilt | 09 [MIXED] Tilt — Tilt angle | INPUT, BAND, OUTPUT |
| terraworkbench:grav_upward_continuation | 05 [FFT] UC — Upward continuation (configurable) | INPUT, BAND, OUTPUT, HEIGHT |
| terraworkbench:gravity_disturbance_grs80 | 02 Latitude correction — gravity disturbance (GRS80) | INPUT, BAND, OUTPUT |
| terraworkbench:grid_survey_points | Grid survey points to GeoTIFF | INPUT, VALUE_FIELD, TARGET_CRS, METHOD, CELL_SIZE, POWER, NEIGHBORS, SEARCH_RADIUS, TPS_SMOOTHING, TPS_NEIGHBORS, ALLOW_LARGE_MINIMUM_CURVATURE_GRID, RANGRID_TOLERANCE, RANGRID_PASS_TOLERANCE, RANGRID_MAX_ITERATIONS, RANGRID_TENSION, RANGRID_COARSE_GRID, RANGRID_SEARCH_RADIUS, RANGRID_BLANKING, RANGRID_DESAMPLE, RANGRID_WEIGHT_POWER, RANGRID_WEIGHT_SLOPE, SINC_RADIUS, SINC_SPACING, SINC_SPACING_Y, SINC_BLANKING, OUTPUT |
| terraworkbench:horizontal_integration_easting | Horizontal integration — easting | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND |
| terraworkbench:horizontal_integration_northing | Horizontal integration — northing | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND |
| terraworkbench:ideal_band_reject | Ideal band reject | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH |
| terraworkbench:ideal_bandpass | Ideal band-pass | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH |
| terraworkbench:interline_spacing_quality_control | Flight-line spacing and missing-line QC | INPUT, LINE_FIELD, EXPECTED, TOLERANCE, OUTPUT |
| terraworkbench:invert_gravity_density_3d | 3D gravity density inversion (SimPEG) | INPUT, DATA_FIELD, UNCERTAINTY_FIELD, ELEVATION_FIELD, TOPOGRAPHY_FIELD, CELL_XY, MESH_TYPE, REFINEMENT_LEVELS, CELL_Z, DEPTH, PADDING, MAX_CELLS, ITERATIONS, REGULARIZATION_NORM, IRLS_ITERATIONS, REFERENCE_VALUE, LOWER, UPPER, DISK_SENSITIVITIES, OUTPUT |
| terraworkbench:invert_joint_gravity_magnetics_3d | Joint 3D gravity–magnetics inversion (cross-gradient) | GRAVITY_INPUT, GRAVITY_DATA, GRAVITY_SIGMA, GRAVITY_ELEVATION, MAGNETIC_INPUT, MAGNETIC_DATA, MAGNETIC_SIGMA, MAGNETIC_ELEVATION, TOPOGRAPHY_FIELD, CELL_XY, CELL_Z, DEPTH, PADDING, MESH_TYPE, REFINEMENT_LEVELS, MAX_CELLS, ITERATIONS, COUPLING, DENSITY_MIN, DENSITY_MAX, SUSCEPTIBILITY_MIN, SUSCEPTIBILITY_MAX, FIELD_AMPLITUDE, FIELD_INCLINATION, FIELD_DECLINATION, DISK_SENSITIVITIES, OUTPUT |
| terraworkbench:invert_magnetic_susceptibility_3d | 3D magnetic susceptibility inversion (SimPEG) | INPUT, DATA_FIELD, UNCERTAINTY_FIELD, ELEVATION_FIELD, TOPOGRAPHY_FIELD, CELL_XY, MESH_TYPE, REFINEMENT_LEVELS, CELL_Z, DEPTH, PADDING, MAX_CELLS, ITERATIONS, REGULARIZATION_NORM, IRLS_ITERATIONS, REFERENCE_VALUE, LOWER, UPPER, FIELD_AMPLITUDE, FIELD_INCLINATION, FIELD_DECLINATION, DISK_SENSITIVITIES, OUTPUT |
| terraworkbench:invert_magnetic_vector_3d | 3D magnetic vector inversion — MVI (SimPEG) | INPUT, DATA_FIELD, UNCERTAINTY_FIELD, ELEVATION_FIELD, TOPOGRAPHY_FIELD, CELL_XY, MESH_TYPE, REFINEMENT_LEVELS, CELL_Z, DEPTH, PADDING, MAX_CELLS, ITERATIONS, LOWER, UPPER, FIELD_AMPLITUDE, FIELD_INCLINATION, FIELD_DECLINATION, DISK_SENSITIVITIES, OUTPUT |
| terraworkbench:mag_as | 10 [MIXED] AS / ASA — Analytic signal amplitude | INPUT, BAND, OUTPUT |
| terraworkbench:mag_directional_horizontal_gradient | 09 [SPATIAL] HG — Directional horizontal gradient | INPUT, BAND, OUTPUT, AZIMUTH |
| terraworkbench:mag_dx | 01 [SPATIAL] DX — First horizontal derivative X | INPUT, BAND, OUTPUT |
| terraworkbench:mag_dy | 02 [SPATIAL] DY — First horizontal derivative Y | INPUT, BAND, OUTPUT |
| terraworkbench:mag_dz | 03 [FFT] DZ — First vertical derivative | INPUT, BAND, OUTPUT |
| terraworkbench:mag_dz2 | 04 [FFT] DZ2 — Second vertical derivative | INPUT, BAND, OUTPUT |
| terraworkbench:mag_rs | 06 [FFT] RS — Residual enhancement | INPUT, BAND, OUTPUT, HEIGHT |
| terraworkbench:mag_tdx | 11 [MIXED] TDX — Horizontal tilt angle | INPUT, BAND, OUTPUT |
| terraworkbench:mag_thdr | 07 [SPATIAL] THDR — Total horizontal derivative | INPUT, BAND, OUTPUT |
| terraworkbench:mag_theta | 12 [MIXED] Theta — Theta angle map | INPUT, BAND, OUTPUT |
| terraworkbench:mag_tilt | 08 [MIXED] Tilt — Tilt angle | INPUT, BAND, OUTPUT |
| terraworkbench:mag_upward_continuation | 05 [FFT] UC — Upward continuation (configurable) | INPUT, BAND, OUTPUT, HEIGHT |
| terraworkbench:magnetic_pseudogravity | Magnetic pseudogravity — vertical integration of RTP/RTE | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, SCALE |
| terraworkbench:microlevel_grid | Directional microleveling | INPUT, BAND, OUTPUT, AZIMUTH, ACROSS_WAVELENGTH, ALONG_WAVELENGTH, CORRECTION |
| terraworkbench:normal_gravity_grs80 | 01 Normal gravity — GRS80 latitude field | INPUT, BAND, OUTPUT |
| terraworkbench:radiometry_background | 08 Raw counts — aircraft, cosmic and radon background | INPUT, BAND, OUTPUT, AIRCRAFT_BACKGROUND, COSMIC_BACKGROUND, RADON_BACKGROUND |
| terraworkbench:radiometry_channel_qc | 05 Radiometric channel quality report | INPUT, BAND, EXPECTED_MINIMUM, REPORT |
| terraworkbench:radiometry_correct_survey_channels | Radiometric survey correction — raw windows to K/eU/eTh | INPUT, K_WINDOW_FIELD, U_WINDOW_FIELD, TH_WINDOW_FIELD, CLEARANCE_FIELD, TOTAL_COUNT_FIELD, DEAD_TIME_SECONDS, K_BACKGROUND, U_BACKGROUND, TH_BACKGROUND, K_FROM_U, K_FROM_TH, U_FROM_K, U_FROM_TH, TH_FROM_K, TH_FROM_U, REFERENCE_HEIGHT, K_ATTENUATION, U_ATTENUATION, TH_ATTENUATION, K_SENSITIVITY, U_SENSITIVITY, TH_SENSITIVITY, OUTPUT |
| terraworkbench:radiometry_dead_time | 07 Raw counts — dead-time correction | INPUT, BAND, OUTPUT, DEAD_TIME_SECONDS |
| terraworkbench:radiometry_despike | 06 Radiometric despike — local median/MAD | INPUT, BAND, OUTPUT, RADIUS, MAD_THRESHOLD |
| terraworkbench:radiometry_dose_rate | 03 Terrestrial absorbed dose rate | INPUT, BAND, OUTPUT, URANIUM, URANIUM_BAND, THORIUM, THORIUM_BAND, K_COEFFICIENT, U_COEFFICIENT, TH_COEFFICIENT |
| terraworkbench:radiometry_f_parameter | 04 Interpretive F parameter — K × eU / eTh | INPUT, BAND, OUTPUT, URANIUM, URANIUM_BAND, THORIUM, THORIUM_BAND, MINIMUM_THORIUM |
| terraworkbench:radiometry_height_attenuation | 09 Raw counts — height attenuation correction | INPUT, BAND, OUTPUT, HEIGHT, HEIGHT_BAND, REFERENCE_HEIGHT, ATTENUATION_COEFFICIENT |
| terraworkbench:radiometry_ratio | 01 Radiometric ratio — configurable channels | INPUT, BAND, OUTPUT, DENOMINATOR, DENOMINATOR_BAND, MINIMUM_DENOMINATOR |
| terraworkbench:radiometry_sensitivity_calibration | 10 Corrected counts — sensitivity calibration | INPUT, BAND, OUTPUT, SENSITIVITY, OFFSET |
| terraworkbench:radiometry_spectral_unmix | 11 Raw windows — calibrated spectral stripping | INPUT, BAND, OUTPUT, URANIUM_WINDOW, URANIUM_BAND, THORIUM_WINDOW, THORIUM_BAND, K_FROM_U, K_FROM_TH, U_FROM_K, U_FROM_TH, TH_FROM_K, TH_FROM_U |
| terraworkbench:radiometry_ternary | 02 Ternary image — K/eTh/eU | INPUT, BAND, OUTPUT, URANIUM, URANIUM_BAND, THORIUM, THORIUM_BAND, LOWER_PERCENTILE, UPPER_PERCENTILE, NORMALIZE |
| terraworkbench:reduction_to_equator | RTE — automatic IGRF-14 / manual (stabilized) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, FIELD_MODE, INCLINATION, DECLINATION, USE_METADATA_DATE, YEAR, MONTH, DAY, ALTITUDE_KM, MAGNETIZATION_INCLINATION, MAGNETIZATION_DECLINATION, MAX_GAIN |
| terraworkbench:reduction_to_pole | RTP — manual Harmonica | INPUT, BAND, OUTPUT, INCLINATION, DECLINATION, MAGNETIZATION_INCLINATION, MAGNETIZATION_DECLINATION |
| terraworkbench:reduction_to_pole_igrf | RTP — automatic IGRF-14 / manual (stabilized) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, FIELD_MODE, INCLINATION, DECLINATION, USE_METADATA_DATE, YEAR, MONTH, DAY, ALTITUDE_KM, MAGNETIZATION_INCLINATION, MAGNETIZATION_DECLINATION, MAX_GAIN |
| terraworkbench:remove_igrf_main_field | Magnetic anomaly — remove IGRF-14 main field | INPUT, VALUE_FIELD, ALTITUDE_FIELD, ALTITUDE_METRES, YEAR, MONTH, DAY, OUTPUT |
| terraworkbench:repeat_line_quality_control | Repeat-line QC and median offset correction | INPUT, VALUE_FIELD, LINE_FIELD, REPEAT_GROUP_FIELD, MAX_DISTANCE, APPLY_CORRECTION, OUTPUT, SUMMARY |
| terraworkbench:simple_bouguer_anomaly | 06 Simple Bouguer anomaly | INPUT, BAND, OUTPUT, ELEVATION, ELEVATION_BAND, DENSITY_CRUST, DENSITY_WATER, VERTICAL_GRADIENT |
| terraworkbench:sinc_interpolation | Sin(x)/x grid interpolation | INPUT, BAND, OUTPUT, FACTOR_X, FACTOR_Y, LOBES |
| terraworkbench:smooth_nine_point | Nine-point binomial smoothing | INPUT, BAND, OUTPUT, PASSES |
| terraworkbench:terrain_correction_prisms | 07 Terrain correction — DEM prisms | INPUT, BAND, OUTPUT, DENSITY_CRUST, DENSITY_WATER, CLEARANCE, MAX_CELLS |
| terraworkbench:upward_continuation | Upward continuation | INPUT, BAND, OUTPUT, HEIGHT |
| terraworkbench:vertical_integration | Vertical integration | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND |

# Catálogo real do provedor QGIS

[English](qgis_en.md) · [Español](qgis_es.md) · [Português](qgis_pt.md)

[Índice](../../manuals/pt/README.md)

QGIS 3.44.12-Solothurn · 95 · pt

IDs e parâmetros são identificadores técnicos. Abrir formulário não executa nem valida um cálculo.

| ID | Nome visível | Parâmetros |
| --- | --- | --- |
| terraworkbench:airy_isostatic_anomaly | 10 Anomalia residual isostática de Airy | INPUT, BAND, OUTPUT, ELEVATION, ELEVATION_BAND, REGIONAL, WATER, DENSITY_WATER, BLOCK_SIZE, MAX_INTERACTIONS, REFERENCE_DEPTH, DENSITY_CRUST, DENSITY_MANTLE, MAX_CELLS |
| terraworkbench:airy_isostatic_anomaly_fft | 11 Residual isostático Airy (FFT periódica) | INPUT, BAND, OUTPUT, REGIONAL, WATER, REFERENCE_DEPTH, DENSITY_CRUST, DENSITY_MANTLE, DENSITY_WATER, HEIGHT, TOLERANCE, MAX_CELLS |
| terraworkbench:airy_isostatic_moho | 09 Profundidade isostática do Moho de Airy | INPUT, BAND, OUTPUT, REFERENCE_DEPTH, DENSITY_CRUST, DENSITY_MANTLE |
| terraworkbench:automatic_channel_lag | Estimativa automática do lag do canal | INPUT, TIME_FIELD, RESPONSE_FIELD, REFERENCE_FIELD, MAXIMUM_LAG, LAG_STEP, USE_DERIVATIVE, OUTPUT, CURVE |
| terraworkbench:automatic_gain_control | Controle automático de ganho (RMS local) | INPUT, BAND, OUTPUT, WINDOW, FLOOR, MAX_GAIN |
| terraworkbench:base_station_quality_control | QC da estação base magnética | INPUT, TIME_FIELD, VALUE_FIELD, UNWRAP, MAX_GAP, SPIKE_WINDOW, SPIKE_SIGMA, MAX_RATE, MAX_DRIFT, OUTPUT, SUMMARY |
| terraworkbench:bouguer_correction | Correção de Bouguer | INPUT, BAND, OUTPUT, DENSITY_CRUST, DENSITY_WATER |
| terraworkbench:bullard_b_curvature | 05 Correção da curvatura terrestre — Bullard B | INPUT, BAND, OUTPUT, DENSITY_CRUST |
| terraworkbench:butterworth_bandpass | Butterworth passa-banda | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH, ORDER |
| terraworkbench:butterworth_highpass | Butterworth passa-alta | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, WAVELENGTH, ORDER |
| terraworkbench:butterworth_lowpass | Butterworth passa-baixa | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, WAVELENGTH, ORDER |
| terraworkbench:butterworth_notch | Butterworth notch (rejeita-faixa) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH, ORDER |
| terraworkbench:circular_median | Mediana circular (disco 2D) | INPUT, BAND, OUTPUT, RADIUS |
| terraworkbench:complete_bouguer_anomaly | 08 Anomalia Bouguer completa — terrestre | INPUT, BAND, OUTPUT, ELEVATION, ELEVATION_BAND, TERRAIN, TERRAIN_BAND, DENSITY_CRUST, DENSITY_WATER, VERTICAL_GRADIENT |
| terraworkbench:correct_magnetic_survey_lines | Correção de linhas magnéticas — base, lag, rumo e despike | INPUT, VALUE_FIELD, TIME_FIELD, LINE_FIELD, BASE, BASE_TIME_FIELD, BASE_VALUE_FIELD, SIGNED_LAG_SECONDS, HEADING_COSINE, HEADING_SINE, HAMPEL_RADIUS, HAMPEL_THRESHOLD, OUTPUT |
| terraworkbench:correct_moving_gravity_survey | Correção de gravidade móvel — deriva, campo de maré e Eötvös | INPUT, VALUE_FIELD, TIME_FIELD, LINE_FIELD, TIDE_FIELD, DRIFT_RATE, EOTVOS_MODE, OUTPUT |
| terraworkbench:cosine_rolloff_highpass | Passa-alta com transição cossenoidal | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH, DEGREE |
| terraworkbench:cosine_rolloff_lowpass | Passa-baixa com transição cossenoidal | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH, DEGREE |
| terraworkbench:crossover_line_leveling | Controle de cruzamentos e nivelamento por linhas de amarração | INPUT, VALUE_FIELD, LINE_FIELD, LINE_TYPE_FIELD, ORDER_FIELD, TIE_VALUES, OUTLIER_SIGMA, CORRECTION_ORDER, HIGH_ORDER_DAMPING, CORRECTED, CROSSOVERS, CORRECTIONS |
| terraworkbench:derivative_easting | Derivada — leste (diferença finita espacial) | INPUT, BAND, OUTPUT, ORDER |
| terraworkbench:derivative_northing | Derivada — norte (diferença finita espacial) | INPUT, BAND, OUTPUT, ORDER |
| terraworkbench:derivative_upward | Derivada — vertical ascendente (FFT) | INPUT, BAND, OUTPUT, ORDER |
| terraworkbench:directional_cosine_pass | Cosseno direcional — passagem | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, AZIMUTH, DEGREE |
| terraworkbench:directional_cosine_reject | Cosseno direcional — rejeição | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, AZIMUTH, DEGREE |
| terraworkbench:downward_continuation | Continuação descendente — estabilizada | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, HEIGHT, LOWPASS_WAVELENGTH, MAX_GAIN, ORDER |
| terraworkbench:drape_dem_quality_control | QC de drape e altura sobre terreno contra DEM | INPUT, ALTITUDE_FIELD, DEM, BAND, TARGET, TOLERANCE, MINIMUM, MAXIMUM, OUTPUT, SUMMARY |
| terraworkbench:equivalent_source_continuation | Fontes equivalentes — ajustar e continuar grade regular | INPUT, BAND, OUTPUT, SOURCE_DEPTH, DAMPING, TARGET_HEIGHT, BLOCK_SIZE, MAX_CELLS, MAX_MATRIX_ELEMENTS, HOLDOUT_PERCENT |
| terraworkbench:fft_derivative_easting | Derivada — leste (FFT) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, ORDER |
| terraworkbench:fft_derivative_northing | Derivada — norte (FFT) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, ORDER |
| terraworkbench:fft_derivative_upward | Derivada — vertical ascendente (FFT) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, ORDER |
| terraworkbench:field_direction_transform | Transformar a direção do campo magnético | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, FIELD_MODE, INCLINATION, DECLINATION, USE_METADATA_DATE, YEAR, MONTH, DAY, ALTITUDE_KM, MAGNETIZATION_INCLINATION, MAGNETIZATION_DECLINATION, MAX_GAIN, TARGET_INCLINATION, TARGET_DECLINATION |
| terraworkbench:flight_line_quality_control | QC de linhas de voo — navegação, altura e taxa do canal | INPUT, TIME_FIELD, LINE_FIELD, VALUE_FIELD, CLEARANCE_FIELD, MAX_TIME_GAP, MAX_SPACING, MIN_SPEED, MAX_SPEED, MAX_TURN, MIN_CLEARANCE, MAX_CLEARANCE, MAX_VALUE_RATE, OUTPUT, SUMMARY |
| terraworkbench:free_air_anomaly | 04 Anomalia ar-livre — gravidade observada + elevação | INPUT, BAND, OUTPUT, ELEVATION, ELEVATION_BAND, VERTICAL_GRADIENT |
| terraworkbench:free_air_correction | 03 Correção de ar livre | INPUT, BAND, OUTPUT, VERTICAL_GRADIENT |
| terraworkbench:gaussian_highpass | Filtro gaussiano passa-alta | INPUT, BAND, OUTPUT, WAVELENGTH |
| terraworkbench:gaussian_lowpass | Filtro gaussiano passa-baixa | INPUT, BAND, OUTPUT, WAVELENGTH |
| terraworkbench:grav_dx | 01 [ESPACIAL] DX — Primeira derivada horizontal X | INPUT, BAND, OUTPUT |
| terraworkbench:grav_dy | 02 [ESPACIAL] DY — Primeira derivada horizontal Y | INPUT, BAND, OUTPUT |
| terraworkbench:grav_dz | 03 [FFT] DZ — Primeira derivada vertical | INPUT, BAND, OUTPUT |
| terraworkbench:grav_dz2 | 04 [FFT] DZ2 — Segunda derivada vertical | INPUT, BAND, OUTPUT |
| terraworkbench:grav_regional | 06 [FFT] Regional — Passa-baixa gaussiano | INPUT, BAND, OUTPUT, WAVELENGTH |
| terraworkbench:grav_residual | 07 [FFT] Residual — Campo menos continuação ascendente | INPUT, BAND, OUTPUT, HEIGHT |
| terraworkbench:grav_tga | 10 [MISTO] TGA — Amplitude do gradiente total | INPUT, BAND, OUTPUT |
| terraworkbench:grav_thdr | 08 [ESPACIAL] THDR — Derivada horizontal total | INPUT, BAND, OUTPUT |
| terraworkbench:grav_tilt | 09 [MISTO] Tilt — Ângulo tilt | INPUT, BAND, OUTPUT |
| terraworkbench:grav_upward_continuation | 05 [FFT] CA — Continuação ascendente (configurável) | INPUT, BAND, OUTPUT, HEIGHT |
| terraworkbench:gravity_disturbance_grs80 | 02 Correção de latitude — distúrbio de gravidade (GRS80) | INPUT, BAND, OUTPUT |
| terraworkbench:grid_survey_points | Interpolar pontos do levantamento para GeoTIFF | INPUT, VALUE_FIELD, TARGET_CRS, METHOD, CELL_SIZE, POWER, NEIGHBORS, SEARCH_RADIUS, TPS_SMOOTHING, TPS_NEIGHBORS, ALLOW_LARGE_MINIMUM_CURVATURE_GRID, RANGRID_TOLERANCE, RANGRID_PASS_TOLERANCE, RANGRID_MAX_ITERATIONS, RANGRID_TENSION, RANGRID_COARSE_GRID, RANGRID_SEARCH_RADIUS, RANGRID_BLANKING, RANGRID_DESAMPLE, RANGRID_WEIGHT_POWER, RANGRID_WEIGHT_SLOPE, SINC_RADIUS, SINC_SPACING, SINC_SPACING_Y, SINC_BLANKING, OUTPUT |
| terraworkbench:horizontal_integration_easting | Integração horizontal — leste | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND |
| terraworkbench:horizontal_integration_northing | Integração horizontal — norte | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND |
| terraworkbench:ideal_band_reject | Rejeita-faixa ideal | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH |
| terraworkbench:ideal_bandpass | Passa-banda ideal | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, LONG_WAVELENGTH, SHORT_WAVELENGTH |
| terraworkbench:interline_spacing_quality_control | QC de espaçamento e linhas de voo ausentes | INPUT, LINE_FIELD, EXPECTED, TOLERANCE, OUTPUT |
| terraworkbench:invert_gravity_density_3d | Inversão 3D de densidade gravimétrica (SimPEG) | INPUT, DATA_FIELD, UNCERTAINTY_FIELD, ELEVATION_FIELD, TOPOGRAPHY_FIELD, CELL_XY, MESH_TYPE, REFINEMENT_LEVELS, CELL_Z, DEPTH, PADDING, MAX_CELLS, ITERATIONS, REGULARIZATION_NORM, IRLS_ITERATIONS, REFERENCE_VALUE, LOWER, UPPER, DISK_SENSITIVITIES, OUTPUT |
| terraworkbench:invert_joint_gravity_magnetics_3d | Inversão conjunta 3D gravidade–magnetometria (gradiente cruzado) | GRAVITY_INPUT, GRAVITY_DATA, GRAVITY_SIGMA, GRAVITY_ELEVATION, MAGNETIC_INPUT, MAGNETIC_DATA, MAGNETIC_SIGMA, MAGNETIC_ELEVATION, TOPOGRAPHY_FIELD, CELL_XY, CELL_Z, DEPTH, PADDING, MESH_TYPE, REFINEMENT_LEVELS, MAX_CELLS, ITERATIONS, COUPLING, DENSITY_MIN, DENSITY_MAX, SUSCEPTIBILITY_MIN, SUSCEPTIBILITY_MAX, FIELD_AMPLITUDE, FIELD_INCLINATION, FIELD_DECLINATION, DISK_SENSITIVITIES, OUTPUT |
| terraworkbench:invert_magnetic_susceptibility_3d | Inversão 3D de suscetibilidade magnética (SimPEG) | INPUT, DATA_FIELD, UNCERTAINTY_FIELD, ELEVATION_FIELD, TOPOGRAPHY_FIELD, CELL_XY, MESH_TYPE, REFINEMENT_LEVELS, CELL_Z, DEPTH, PADDING, MAX_CELLS, ITERATIONS, REGULARIZATION_NORM, IRLS_ITERATIONS, REFERENCE_VALUE, LOWER, UPPER, FIELD_AMPLITUDE, FIELD_INCLINATION, FIELD_DECLINATION, DISK_SENSITIVITIES, OUTPUT |
| terraworkbench:invert_magnetic_vector_3d | Inversão vetorial magnética 3D — MVI (SimPEG) | INPUT, DATA_FIELD, UNCERTAINTY_FIELD, ELEVATION_FIELD, TOPOGRAPHY_FIELD, CELL_XY, MESH_TYPE, REFINEMENT_LEVELS, CELL_Z, DEPTH, PADDING, MAX_CELLS, ITERATIONS, LOWER, UPPER, FIELD_AMPLITUDE, FIELD_INCLINATION, FIELD_DECLINATION, DISK_SENSITIVITIES, OUTPUT |
| terraworkbench:mag_as | 10 [MISTO] AS / ASA — Amplitude do sinal analítico | INPUT, BAND, OUTPUT |
| terraworkbench:mag_directional_horizontal_gradient | 09 [ESPACIAL] GH — Gradiente horizontal direcional | INPUT, BAND, OUTPUT, AZIMUTH |
| terraworkbench:mag_dx | 01 [ESPACIAL] DX — Primeira derivada horizontal X | INPUT, BAND, OUTPUT |
| terraworkbench:mag_dy | 02 [ESPACIAL] DY — Primeira derivada horizontal Y | INPUT, BAND, OUTPUT |
| terraworkbench:mag_dz | 03 [FFT] DZ — Primeira derivada vertical | INPUT, BAND, OUTPUT |
| terraworkbench:mag_dz2 | 04 [FFT] DZ2 — Segunda derivada vertical | INPUT, BAND, OUTPUT |
| terraworkbench:mag_rs | 06 [FFT] RS — Realce residual | INPUT, BAND, OUTPUT, HEIGHT |
| terraworkbench:mag_tdx | 11 [MISTO] TDX — Ângulo tilt horizontal | INPUT, BAND, OUTPUT |
| terraworkbench:mag_thdr | 07 [ESPACIAL] THDR — Derivada horizontal total | INPUT, BAND, OUTPUT |
| terraworkbench:mag_theta | 12 [MISTO] Theta — Mapa do ângulo theta | INPUT, BAND, OUTPUT |
| terraworkbench:mag_tilt | 08 [MISTO] Tilt — Ângulo tilt | INPUT, BAND, OUTPUT |
| terraworkbench:mag_upward_continuation | 05 [FFT] CA — Continuação ascendente (configurável) | INPUT, BAND, OUTPUT, HEIGHT |
| terraworkbench:magnetic_pseudogravity | Pseudogravidade magnética — integração vertical de RTP/RTE | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, SCALE |
| terraworkbench:microlevel_grid | Micronivelamento direcional | INPUT, BAND, OUTPUT, AZIMUTH, ACROSS_WAVELENGTH, ALONG_WAVELENGTH, CORRECTION |
| terraworkbench:normal_gravity_grs80 | 01 Gravidade normal — campo de latitude GRS80 | INPUT, BAND, OUTPUT |
| terraworkbench:radiometry_background | 08 Contagens brutas — fundo da aeronave, cósmico e radônio | INPUT, BAND, OUTPUT, AIRCRAFT_BACKGROUND, COSMIC_BACKGROUND, RADON_BACKGROUND |
| terraworkbench:radiometry_channel_qc | 05 Relatório de qualidade do canal radiométrico | INPUT, BAND, EXPECTED_MINIMUM, REPORT |
| terraworkbench:radiometry_correct_survey_channels | Correção de levantamento radiométrico — janelas brutas para K/eU/eTh | INPUT, K_WINDOW_FIELD, U_WINDOW_FIELD, TH_WINDOW_FIELD, CLEARANCE_FIELD, TOTAL_COUNT_FIELD, DEAD_TIME_SECONDS, K_BACKGROUND, U_BACKGROUND, TH_BACKGROUND, K_FROM_U, K_FROM_TH, U_FROM_K, U_FROM_TH, TH_FROM_K, TH_FROM_U, REFERENCE_HEIGHT, K_ATTENUATION, U_ATTENUATION, TH_ATTENUATION, K_SENSITIVITY, U_SENSITIVITY, TH_SENSITIVITY, OUTPUT |
| terraworkbench:radiometry_dead_time | 07 Contagens brutas — correção de tempo morto | INPUT, BAND, OUTPUT, DEAD_TIME_SECONDS |
| terraworkbench:radiometry_despike | 06 Despike radiométrico — mediana/MAD local | INPUT, BAND, OUTPUT, RADIUS, MAD_THRESHOLD |
| terraworkbench:radiometry_dose_rate | 03 Taxa de dose absorvida terrestre | INPUT, BAND, OUTPUT, URANIUM, URANIUM_BAND, THORIUM, THORIUM_BAND, K_COEFFICIENT, U_COEFFICIENT, TH_COEFFICIENT |
| terraworkbench:radiometry_f_parameter | 04 Parâmetro F interpretativo — K × eU / eTh | INPUT, BAND, OUTPUT, URANIUM, URANIUM_BAND, THORIUM, THORIUM_BAND, MINIMUM_THORIUM |
| terraworkbench:radiometry_height_attenuation | 09 Contagens brutas — correção de atenuação por altura | INPUT, BAND, OUTPUT, HEIGHT, HEIGHT_BAND, REFERENCE_HEIGHT, ATTENUATION_COEFFICIENT |
| terraworkbench:radiometry_ratio | 01 Razão radiométrica — canais configuráveis | INPUT, BAND, OUTPUT, DENOMINATOR, DENOMINATOR_BAND, MINIMUM_DENOMINATOR |
| terraworkbench:radiometry_sensitivity_calibration | 10 Contagens corrigidas — calibração de sensibilidade | INPUT, BAND, OUTPUT, SENSITIVITY, OFFSET |
| terraworkbench:radiometry_spectral_unmix | 11 Janelas brutas — stripping espectral calibrado | INPUT, BAND, OUTPUT, URANIUM_WINDOW, URANIUM_BAND, THORIUM_WINDOW, THORIUM_BAND, K_FROM_U, K_FROM_TH, U_FROM_K, U_FROM_TH, TH_FROM_K, TH_FROM_U |
| terraworkbench:radiometry_ternary | 02 Imagem ternária — K/eTh/eU | INPUT, BAND, OUTPUT, URANIUM, URANIUM_BAND, THORIUM, THORIUM_BAND, LOWER_PERCENTILE, UPPER_PERCENTILE, NORMALIZE |
| terraworkbench:reduction_to_equator | RTE — IGRF-14 automático / manual (estabilizado) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, FIELD_MODE, INCLINATION, DECLINATION, USE_METADATA_DATE, YEAR, MONTH, DAY, ALTITUDE_KM, MAGNETIZATION_INCLINATION, MAGNETIZATION_DECLINATION, MAX_GAIN |
| terraworkbench:reduction_to_pole | RTP — Harmonica manual | INPUT, BAND, OUTPUT, INCLINATION, DECLINATION, MAGNETIZATION_INCLINATION, MAGNETIZATION_DECLINATION |
| terraworkbench:reduction_to_pole_igrf | RTP — IGRF-14 automático / manual (estabilizado) | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND, FIELD_MODE, INCLINATION, DECLINATION, USE_METADATA_DATE, YEAR, MONTH, DAY, ALTITUDE_KM, MAGNETIZATION_INCLINATION, MAGNETIZATION_DECLINATION, MAX_GAIN |
| terraworkbench:remove_igrf_main_field | Anomalia magnética — remover campo principal IGRF-14 | INPUT, VALUE_FIELD, ALTITUDE_FIELD, ALTITUDE_METRES, YEAR, MONTH, DAY, OUTPUT |
| terraworkbench:repeat_line_quality_control | QC de linhas repetidas e correção por offset mediano | INPUT, VALUE_FIELD, LINE_FIELD, REPEAT_GROUP_FIELD, MAX_DISTANCE, APPLY_CORRECTION, OUTPUT, SUMMARY |
| terraworkbench:simple_bouguer_anomaly | 06 Anomalia Bouguer simples | INPUT, BAND, OUTPUT, ELEVATION, ELEVATION_BAND, DENSITY_CRUST, DENSITY_WATER, VERTICAL_GRADIENT |
| terraworkbench:sinc_interpolation | Interpolação de grade sin(x)/x | INPUT, BAND, OUTPUT, FACTOR_X, FACTOR_Y, LOBES |
| terraworkbench:smooth_nine_point | Suavização binomial de nove pontos | INPUT, BAND, OUTPUT, PASSES |
| terraworkbench:terrain_correction_prisms | 07 Correção de terreno — prismas do MDE | INPUT, BAND, OUTPUT, DENSITY_CRUST, DENSITY_WATER, CLEARANCE, MAX_CELLS |
| terraworkbench:upward_continuation | Continuação ascendente | INPUT, BAND, OUTPUT, HEIGHT |
| terraworkbench:vertical_integration | Integração vertical | INPUT, BAND, OUTPUT, FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND |

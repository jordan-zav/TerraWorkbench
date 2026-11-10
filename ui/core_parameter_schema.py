"""Host-free presentation contracts. Never supplies missing physical values.

API argument names remain the dictionary keys. Labels and editor hints are
presentation only; the scientific implementation remains the final validator.
"""

import inspect
import math

LANGUAGES = ("en", "es", "pt")
UNITS = {
    "_t": "T",
    "_mgal_per_kg_m3": "mGal / (kg/m³)",
    "_kg_m3": "kg/m³",
    "_a_m3": "A/m³",
    "_a_m2": "A·m²",
    "_ohm_m": "Ω·m",
    "_mv_km_nt": "(mV/km)/nT",
    "_m_s2": "m/s²",
    "_m_s": "m/s",
    "_s_m": "S/m",
    "_t_s": "T/s",
    "_t2": "T²",
    "_ohm": "Ω",
    "_mgal": "mGal",
    "_v_v": "V/V",
    "_hz": "Hz",
    "_deg": "°",
    "_pa": "Pa",
    "_nt": "nT",
    "_v": "V",
    "_a": "A",
    "_m": "m",
    "_s": "s",
}

# Complete phrases, not automatic word-by-word machine translation.
BASE_LABELS = {
    "cell_xy": ("Horizontal cell size (m)", "Tamaño horizontal de celda (m)", "Tamanho horizontal da célula (m)"),
    "cell_z": ("Vertical cell size (m)", "Tamaño vertical de celda (m)", "Tamanho vertical da célula (m)"),
    "padding": ("Padding cells per side", "Celdas de extensión por lado", "Células de extensão por lado"),
    "iterations": ("Maximum outer iterations", "Máximo de iteraciones externas", "Máximo de iterações externas"),
    "field_amplitude": ("Inducing field amplitude (nT)", "Amplitud del campo inductor (nT)", "Amplitude do campo indutor (nT)"),
    "field_inclination": ("Inducing field inclination (degrees down)", "Inclinación del campo inductor (grados hacia abajo)", "Inclinação do campo indutor (graus para baixo)"),
    "field_declination": ("Inducing field declination from mesh Y (degrees)", "Declinación del campo desde Y de la malla (grados)", "Declinação do campo a partir de Y da malha (graus)"),
    "vector": (
        "Cartesian vector model",
        "Modelo vectorial cartesiano",
        "Modelo vetorial cartesiano",
    ),
    "cell_centers_enu_m": (
        "ENU cell centers (m)",
        "Centros de celda ENU (m)",
        "Centros das células ENU (m)",
    ),
    "background_value": (
        "Explicit outside background property",
        "Propiedad de fondo exterior explícita",
        "Propriedade de fundo externo explícita",
    ),
    "support_prisms_m": (
        "Geological support boxes (m)",
        "Cajas de soporte geológico (m)",
        "Caixas de suporte geológico (m)",
    ),
    "depth_limits_m": (
        "Allowed depth interval (m)",
        "Intervalo de profundidad permitido (m)",
        "Intervalo de profundidade permitido (m)",
    ),
    "surface_elevation_m": (
        "Explicit surface elevation (m)",
        "Elevación de superficie explícita (m)",
        "Elevação explícita da superfície (m)",
    ),
    "outside_weight": (
        "Outside regularization weight",
        "Peso de regularización exterior",
        "Peso de regularização externo",
    ),
    "mode": ("Constraint mode", "Modo de restricción", "Modo de restrição"),
    "cell_volumes_m3": (
        "Cell volumes (m3)",
        "Volúmenes de celda (m3)",
        "Volumes das células (m3)",
    ),
    "recovered": (
        "Recovered model properties",
        "Propiedades del modelo recuperado",
        "Propriedades do modelo recuperado",
    ),
    "truth": (
        "Independent validation truth",
        "Modelo verdadero de validación independiente",
        "Modelo verdadeiro de validação independente",
    ),
    "criteria": (
        "Predeclared recovery criteria",
        "Criterios de recuperación predeclarados",
        "Critérios de recuperação predeclarados",
    ),
    "connectivity_radius_m": (
        "Center connectivity radius (m)",
        "Radio de conectividad entre centros (m)",
        "Raio de conectividade entre centros (m)",
    ),
    "connectivity_edges": (
        "Cell adjacency index pairs",
        "Pares de índices de celdas adyacentes",
        "Pares de índices de células adjacentes",
    ),
    "mvi_parameterization": ("MVI coordinates", "Coordenadas MVI", "Coordenadas MVI"),
    "mvi_sensitivity_weights": ("Sensitivity prior weights", "Pesos de sensibilidad del prior", "Pesos de sensibilidade do prior"),
    "mvi_irls_update": ("IRLS update strategy", "Estrategia de actualización IRLS", "Estratégia de atualização IRLS"),
    "mvi_cartesian_iterations": ("Cartesian initialization iterations", "Iteraciones de inicialización cartesiana", "Iterações de inicialização cartesiana"),
    "mvi_amplitude_max": ("Maximum effective susceptibility amplitude (SI)", "Amplitud máxima de susceptibilidad efectiva (SI)", "Amplitude máxima de suscetibilidade efetiva (SI)"),
    "mvi_angle_norms": ("Spatial angle norms (x,y,z)", "Normas espaciales de los ángulos (x,y,z)", "Normas espaciais dos ângulos (x,y,z)"),
    "support_fraction": (
        "Scoring fraction of true peak amplitude",
        "Fracción de amplitud máxima verdadera para evaluar",
        "Fração da amplitude máxima verdadeira para avaliar",
    ),
    "max_links": (
        "Maximum connectivity links",
        "Máximo de enlaces de conectividad",
        "Máximo de ligações de conectividade",
    ),
    "observed_mgal": (
        "Observed gravity (mGal)",
        "Gravedad observada (mGal)",
        "Gravidade observada (mGal)",
    ),
    "data_std_mgal": (
        "Gravity standard deviation (mGal)",
        "Desviación estándar de gravedad (mGal)",
        "Desvio padrão da gravidade (mGal)",
    ),
    "observed_nt": (
        "Observed magnetic data (nT)",
        "Datos magnéticos observados (nT)",
        "Dados magnéticos observados (nT)",
    ),
    "data_std_nt": (
        "Magnetic standard deviation (nT)",
        "Desviación estándar magnética (nT)",
        "Desvio padrão magnético (nT)",
    ),
    "gravity_component": (
        "Gravity vertical convention",
        "Convención vertical de gravedad",
        "Convenção vertical da gravidade",
    ),
    "probe_count": (
        "Number of probing vectors",
        "Número de vectores de sondeo",
        "Número de vetores de sondagem",
    ),
    "parameter_indices": (
        "Selected parameter indices (zero based)",
        "Índices de parámetros seleccionados (desde cero)",
        "Índices dos parâmetros selecionados (a partir de zero)",
    ),
    "precision_diagonal": (
        "Positive precision diagonal for preconditioning",
        "Diagonal positiva de precisión para precondicionar",
        "Diagonal positiva de precisão para precondicionamento",
    ),
    "cg_rtol": (
        "CG relative residual tolerance",
        "Tolerancia relativa del residuo CG",
        "Tolerância relativa do resíduo CG",
    ),
    "cg_maxiter": (
        "Maximum CG iterations per solve",
        "Máximo de iteraciones CG por resolución",
        "Máximo de iterações CG por resolução",
    ),
    "max_matvecs": (
        "Maximum operator applications",
        "Máximo de aplicaciones de operadores",
        "Máximo de aplicações dos operadores",
    ),
    "anchor_std_mgal": (
        "Standard deviation per gravity reference (mGal)",
        "Desviación estándar por referencia gravimétrica (mGal)",
        "Desvio padrão por referência gravimétrica (mGal)",
    ),
    "aircraft": (
        "Instrument/aircraft background",
        "Fondo del instrumento o aeronave",
        "Fundo do instrumento ou aeronave",
    ),
    "cosmic": ("Cosmic background", "Fondo cósmico", "Fundo cósmico"),
    "radon": (
        "Calibrated radon background",
        "Fondo calibrado de radón",
        "Fundo calibrado de radônio",
    ),
    "count_rate": (
        "Observed count rate",
        "Tasa de conteo observada",
        "Taxa de contagem observada",
    ),
    "angular_tolerance_deg": (
        "Axial direction tolerance (degrees)",
        "Tolerancia de dirección axial (grados)",
        "Tolerância de direção axial (graus)",
    ),
    "coefficient_covariance": (
        "Calibration coefficient covariance",
        "Covarianza de coeficientes de calibración",
        "Covariância dos coeficientes de calibração",
    ),
    "coefficients": (
        "Calibration coefficients in documented order",
        "Coeficientes de calibración en el orden documentado",
        "Coeficientes de calibração na ordem documentada",
    ),
    "coordinates": (
        "Projected planar coordinates",
        "Coordenadas planas proyectadas",
        "Coordenadas planas projetadas",
    ),
    "downward_th_rate": (
        "Downward thorium-window rate",
        "Tasa de ventana Th inferior",
        "Taxa da janela Th inferior",
    ),
    "fit_offset": (
        "Fit a constant gravity offset",
        "Ajustar una constante gravimétrica",
        "Ajustar uma constante gravimétrica",
    ),
    "lag_edges_m": (
        "Distance-lag bin edges (m)",
        "Límites de clases de distancia (m)",
        "Limites das classes de distância (m)",
    ),
    "max_systems": (
        "Maximum distinct local systems",
        "Máximo de sistemas locales distintos",
        "Máximo de sistemas locais distintos",
    ),
    "model": ("Variogram model", "Modelo de variograma", "Modelo de variograma"),
    "neighbors": (
        "Maximum neighboring observations",
        "Máximo de observaciones vecinas",
        "Máximo de observações vizinhas",
    ),
    "nugget": (
        "Microscale nugget variance",
        "Varianza de efecto pepita",
        "Variância do efeito pepita",
    ),
    "observation_xz_m": (
        "Profile stations: x and upward z (m)",
        "Estaciones del perfil: x y z positiva hacia arriba (m)",
        "Estações do perfil: x e z positiva para cima (m)",
    ),
    "partial_sill": (
        "Structured partial sill (variance)",
        "Meseta parcial estructurada (varianza)",
        "Patamar parcial estruturado (variância)",
    ),
    "polygons_xz_m": (
        "Body vertices: x and upward z (m)",
        "Vértices de cuerpos: x y z positiva hacia arriba (m)",
        "Vértices dos corpos: x e z positiva para cima (m)",
    ),
    "query_coordinates": (
        "Prediction coordinates",
        "Coordenadas de predicción",
        "Coordenadas de predição",
    ),
    "radon_component": (
        "Radon component index (zero-based)",
        "Índice del componente radón (desde cero)",
        "Índice do componente radônio (a partir de zero)",
    ),
    "range_m": (
        "Declared variogram range (m)",
        "Alcance declarado del variograma (m)",
        "Alcance declarado do variograma (m)",
    ),
    "rate_std": (
        "Independent spectral rate standard deviations",
        "Desviaciones estándar independientes de tasas espectrales",
        "Desvios padrão independentes das taxas espectrais",
    ),
    "response_matrix": (
        "Calibrated response matrix",
        "Matriz de respuesta calibrada",
        "Matriz de resposta calibrada",
    ),
    "search_radius_m": (
        "Search radius (m; zero means unlimited)",
        "Radio de búsqueda (m; cero significa sin límite)",
        "Raio de busca (m; zero significa sem limite)",
    ),
    "off_event_indices": (
        "Selected switch-off indices (zero-based)",
        "Índices de apagado seleccionados (desde cero)",
        "Índices de desligamento selecionados (a partir de zero)",
    ),
    "stack_mode": (
        "Stacking convention",
        "Convención de apilado",
        "Convenção de empilhamento",
    ),
    "stack_weights": (
        "Nonnegative weights per selected cycle",
        "Pesos no negativos por ciclo seleccionado",
        "Pesos não negativos por ciclo selecionado",
    ),
    "event_times_s": (
        "Current switch times relative to final switch-off (s)",
        "Tiempos de cambios de corriente relativos al apagado final (s)",
        "Tempos de mudanças de corrente relativos ao desligamento final (s)",
    ),
    "observed_resistivity_ohm_m": (
        "Observed complex resistivity (Ω·m)",
        "Resistividad compleja observada (Ω·m)",
        "Resistividade complexa observada (Ω·m)",
    ),
    "standard_deviation": (
        "Standard deviations in data units",
        "Desviaciones estándar en unidades del dato",
        "Desvios padrão nas unidades dos dados",
    ),
    "pulse_duration_s": (
        "Current on-time before switch-off (s)",
        "Tiempo de corriente antes del apagado (s)",
        "Tempo de corrente antes do desligamento (s)",
    ),
    "normalization": (
        "Primary-voltage normalization",
        "Normalización del voltaje primario",
        "Normalização da tensão primária",
    ),
    "sample_coordinates": (
        "Sample frequencies or time/gate coordinates",
        "Frecuencias o coordenadas de tiempos y ventanas",
        "Frequências ou coordenadas de tempos e janelas",
    ),
    "domain": ("Response domain", "Dominio de la respuesta", "Domínio da resposta"),
    "lower": (
        "Lower parameter bounds",
        "Límites inferiores de los parámetros",
        "Limites inferiores dos parâmetros",
    ),
    "upper": (
        "Upper parameter bounds",
        "Límites superiores de los parámetros",
        "Limites superiores dos parâmetros",
    ),
    "absolute_tolerance_mgal": (
        "Approximation tolerance (mGal)",
        "Tolerancia de aproximación (mGal)",
        "Tolerância de aproximação (mGal)",
    ),
    "reference_elevation_m": (
        "Model reference plane elevation (m)",
        "Elevación del plano de referencia del modelo (m)",
        "Elevação do plano de referência do modelo (m)",
    ),
    "leaf_cells": (
        "Maximum cells per tree leaf",
        "Celdas máximas por hoja del árbol",
        "Células máximas por folha da árvore",
    ),
    "max_tree_nodes": (
        "Maximum tree nodes",
        "Cantidad máxima de nodos del árbol",
        "Quantidade máxima de nós da árvore",
    ),
    "max_node_visits": (
        "Maximum node visits",
        "Visitas máximas a nodos",
        "Visitas máximas aos nós",
    ),
    "max_prism_evaluations": (
        "Maximum exact prism evaluations",
        "Evaluaciones exactas máximas de prismas",
        "Avaliações exatas máximas de prismas",
    ),
    "initial_moments_a_m2": (
        "Initial dipole moments ENU (A·m²)",
        "Momentos dipolares iniciales ENU (A·m²)",
        "Momentos dipolares iniciais ENU (A·m²)",
    ),
    "altitude_km": (
        "Geodetic height (km)",
        "Altura geodésica (km)",
        "Altitude geodésica (km)",
    ),
    "azimuth_degrees": (
        "Axial azimuths (°)",
        "Azimuts axiales (°)",
        "Azimutes axiais (°)",
    ),
    "background": (
        "Prescribed property background",
        "Fondo prescrito de la propiedad",
        "Fundo prescrito da propriedade",
    ),
    "bin_origin_degrees": (
        "Orientation bin origin (°)",
        "Origen de intervalos de orientación (°)",
        "Origem dos intervalos de orientação (°)",
    ),
    "bins": ("Histogram bins", "Intervalos del histograma", "Intervalos do histograma"),
    "chunk_size": ("Points per block", "Puntos por bloque", "Pontos por bloco"),
    "clearance_m": (
        "Observation clearance (m)",
        "Separación de observación (m)",
        "Separação da observação (m)",
    ),
    "component": ("Magnetic component", "Componente magnética", "Componente magnética"),
    "connectivity": (
        "Pixel connectivity (4 or 8)",
        "Conectividad de píxeles (4 u 8)",
        "Conectividade de pixels (4 ou 8)",
    ),
    "damping_wavenumber": (
        "Damping wavenumber (rad/m)",
        "Número de onda de amortiguación (rad/m)",
        "Número de onda de amortecimento (rad/m)",
    ),
    "date": (
        "Survey date (ISO 8601)",
        "Fecha del levantamiento (ISO 8601)",
        "Data do levantamento (ISO 8601)",
    ),
    "declination": (
        "Declination from grid north (°)",
        "Declinación desde el norte de grilla (°)",
        "Declinação a partir do norte da grade (°)",
    ),
    "density_crust": (
        "Crust density (kg/m³)",
        "Densidad de corteza (kg/m³)",
        "Densidade da crosta (kg/m³)",
    ),
    "density_water": (
        "Water density (kg/m³)",
        "Densidad del agua (kg/m³)",
        "Densidade da água (kg/m³)",
    ),
    "easting": ("East axis (m)", "Eje este (m)", "Eixo leste (m)"),
    "northing": ("North axis (m)", "Eje norte (m)", "Eixo norte (m)"),
    "edge_exclusion_cells": (
        "Excluded border cells",
        "Celdas excluidas del borde",
        "Células excluídas da borda",
    ),
    "feature_mask": (
        "Boolean feature mask",
        "Máscara booleana de rasgos",
        "Máscara booleana de feições",
    ),
    "gains": ("Radial gains", "Ganancias radiales", "Ganhos radiais"),
    "gradient_east": (
        "East gradient (nT/m)",
        "Gradiente este (nT/m)",
        "Gradiente leste (nT/m)",
    ),
    "gradient_north": (
        "North gradient (nT/m)",
        "Gradiente norte (nT/m)",
        "Gradiente norte (nT/m)",
    ),
    "gradient_up": (
        "Upward gradient (nT/m)",
        "Gradiente hacia arriba (nT/m)",
        "Gradiente para cima (nT/m)",
    ),
    "moments_a_m2": (
        "Dipole moments ENU (A·m²)",
        "Momentos dipolares ENU (A·m²)",
        "Momentos dipolares ENU (A·m²)",
    ),
    "input_component": (
        "Input magnetic component",
        "Componente magnética de entrada",
        "Componente magnética de entrada",
    ),
    "output_component": (
        "Output magnetic component",
        "Componente magnética de salida",
        "Componente magnética de saída",
    ),
    "latitude": (
        "Geodetic latitude (°)",
        "Latitud geodésica (°)",
        "Latitude geodésica (°)",
    ),
    "longitude": (
        "Longitude, east positive (°)",
        "Longitud, positiva al este (°)",
        "Longitude, positiva a leste (°)",
    ),
    "max_abs_gain": (
        "Maximum absolute filter gain",
        "Ganancia absoluta máxima del filtro",
        "Ganho absoluto máximo do filtro",
    ),
    "max_bin_cells": (
        "Maximum bin-cell work",
        "Trabajo máximo de intervalos por celdas",
        "Trabalho máximo de intervalos por células",
    ),
    "max_forward_calls": (
        "Maximum forward evaluations",
        "Evaluaciones directas máximas",
        "Avaliações diretas máximas",
    ),
    "max_inverse_gain": (
        "Maximum inverse gain",
        "Ganancia inversa máxima",
        "Ganho inverso máximo",
    ),
    "max_nfev": (
        "Maximum solver evaluations",
        "Evaluaciones máximas del optimizador",
        "Avaliações máximas do otimizador",
    ),
    "max_paths": (
        "Maximum paths",
        "Cantidad máxima de caminos",
        "Quantidade máxima de caminhos",
    ),
    "max_points": (
        "Maximum points",
        "Cantidad máxima de puntos",
        "Quantidade máxima de pontos",
    ),
    "max_skeleton_pixels": (
        "Maximum skeleton pixels",
        "Píxeles máximos del esqueleto",
        "Pixels máximos do esqueleto",
    ),
    "max_total_interactions": (
        "Maximum total interactions",
        "Interacciones totales máximas",
        "Interações totais máximas",
    ),
    "minimum_count": (
        "Minimum supporting samples",
        "Mínimo de muestras de soporte",
        "Mínimo de amostras de suporte",
    ),
    "minimum_length_m": (
        "Minimum path length (m)",
        "Longitud mínima del camino (m)",
        "Comprimento mínimo do caminho (m)",
    ),
    "minimum_wavelength_m": (
        "Shortest retained wavelength (m)",
        "Menor longitud de onda conservada (m)",
        "Menor comprimento de onda conservado (m)",
    ),
    "moment_lower": (
        "Lower dipole moment bounds (A·m²)",
        "Límites inferiores de momentos (A·m²)",
        "Limites inferiores dos momentos (A·m²)",
    ),
    "moment_upper": (
        "Upper dipole moment bounds (A·m²)",
        "Límites superiores de momentos (A·m²)",
        "Limites superiores dos momentos (A·m²)",
    ),
    "noise_threshold": (
        "Noise threshold in field units",
        "Umbral de ruido en unidades del campo",
        "Limiar de ruído nas unidades do campo",
    ),
    "observation_xyz": (
        "Observation positions ENU (m)",
        "Posiciones de observación ENU (m)",
        "Posições de observação ENU (m)",
    ),
    "origin_xy": (
        "First pixel centre XY (m)",
        "Centro XY del primer píxel (m)",
        "Centro XY do primeiro pixel (m)",
    ),
    "output_mean_nt": (
        "Prescribed output mean (nT)",
        "Media prescrita de salida (nT)",
        "Média prescrita da saída (nT)",
    ),
    "position_lower": (
        "Lower source position bounds ENU (m)",
        "Límites inferiores de posición ENU (m)",
        "Limites inferiores da posição ENU (m)",
    ),
    "position_upper": (
        "Upper source position bounds ENU (m)",
        "Límites superiores de posición ENU (m)",
        "Limites superiores da posição ENU (m)",
    ),
    "rank_tolerance": (
        "Relative Jacobian rank tolerance",
        "Tolerancia relativa del rango del jacobiano",
        "Tolerância relativa do posto do jacobiano",
    ),
    "reference_mean_nt": (
        "Prescribed reference mean (nT)",
        "Media de referencia prescrita (nT)",
        "Média de referência prescrita (nT)",
    ),
    "regularization_response": (
        "Regularization in response units",
        "Regularización en unidades de respuesta",
        "Regularização em unidades de resposta",
    ),
    "require_valid_center": (
        "Require a valid centre sample",
        "Exigir una muestra central válida",
        "Exigir uma amostra central válida",
    ),
    "sigma_on_f": (
        "Log-Gabor bandwidth ratio",
        "Razón de ancho de banda log-Gabor",
        "Razão de largura de banda log-Gabor",
    ),
    "source_crs": ("Source CRS", "CRS de origen", "SRC de origem"),
    "target_crs": ("Target CRS", "CRS de destino", "SRC de destino"),
    "source_xyz": (
        "Source positions ENU (m)",
        "Posiciones de fuentes ENU (m)",
        "Posições das fontes ENU (m)",
    ),
    "thickness_m": (
        "Layer thickness (m)",
        "Espesor de capa (m)",
        "Espessura da camada (m)",
    ),
    "top_depth_m": (
        "Layer top depth (m)",
        "Profundidad del techo de capa (m)",
        "Profundidade do topo da camada (m)",
    ),
    "value_range": (
        "Quantization range",
        "Intervalo de cuantización",
        "Intervalo de quantização",
    ),
    "wavelengths_m": (
        "Analysis wavelengths (m)",
        "Longitudes de onda de análisis (m)",
        "Comprimentos de onda de análise (m)",
    ),
    "wavenumbers_rad_per_m": (
        "Angular radial wavenumbers (rad/m)",
        "Números de onda radiales angulares (rad/m)",
        "Números de onda radiais angulares (rad/m)",
    ),
    "weights": (
        "Relative component weights",
        "Pesos relativos de componentes",
        "Pesos relativos das componentes",
    ),
    "initial": ("Initial model", "Modelo inicial", "Modelo inicial"),
    "abmn": (
        "ABMN electrode indices",
        "Índices de electrodos ABMN",
        "Índices de eletrodos ABMN",
    ),
    "accepted": (
        "Accepted observations",
        "Observaciones aceptadas",
        "Observações aceitas",
    ),
    "active_cells": (
        "Active-cell mask",
        "Máscara de celdas activas",
        "Máscara de células ativas",
    ),
    "air_conductivity": (
        "Air conductivity",
        "Conductividad del aire",
        "Condutividade do ar",
    ),
    "amplitudes": ("Amplitudes", "Amplitudes", "Amplitudes"),
    "anchors": ("Network anchors", "Anclajes de la red", "Âncoras da rede"),
    "angular_wavenumber": (
        "Angular wavenumber",
        "Número de onda angular",
        "Número de onda angular",
    ),
    "azimuth": ("Azimuth", "Azimut", "Azimute"),
    "background_degree": (
        "Background polynomial degree",
        "Grado polinómico del fondo",
        "Grau polinomial do fundo",
    ),
    "beta": (
        "Regularization weight",
        "Peso de regularización",
        "Peso de regularização",
    ),
    "block_size": ("Block size", "Tamaño de bloque", "Tamanho do bloco"),
    "bounds": ("Parameter bounds", "Límites de parámetros", "Limites de parâmetros"),
    "calibration": (
        "Calibration result",
        "Resultado de calibración",
        "Resultado de calibração",
    ),
    "candidate_thicknesses": (
        "Candidate thicknesses",
        "Espesores candidatos",
        "Espessuras candidatas",
    ),
    "channel_peaks": (
        "Peak channel positions",
        "Posiciones de picos en canales",
        "Posições de picos nos canais",
    ),
    "chargeability": ("Chargeability", "Cargabilidad", "Cargabilidade"),
    "collar_enu": (
        "Collar position, ENU",
        "Posición del collar, ENU",
        "Posição da boca do poço, ENU",
    ),
    "component_names": (
        "Component names",
        "Nombres de componentes",
        "Nomes dos componentes",
    ),
    "concentration_units": (
        "Concentration units",
        "Unidades de concentración",
        "Unidades de concentração",
    ),
    "conductivity": ("Conductivity", "Conductividad", "Condutividade"),
    "coordinates_enu": (
        "Coordinates, east/north/up",
        "Coordenadas, este/norte/arriba",
        "Coordenadas, leste/norte/cima",
    ),
    "count_std": (
        "Count standard deviations",
        "Desviaciones estándar de conteos",
        "Desvios padrão das contagens",
    ),
    "counts": ("Spectral counts", "Conteos espectrales", "Contagens espectrais"),
    "covariance": ("Covariance", "Covarianza", "Covariância"),
    "covariance_down_up": (
        "Downward/upward covariance",
        "Covarianza inferior/superior",
        "Covariância inferior/superior",
    ),
    "cross_xz": ("Mixed x/z derivative", "Derivada mixta x/z", "Derivada mista x/z"),
    "current": ("Current", "Corriente", "Corrente"),
    "curve_values": (
        "Curve sample values",
        "Valores de muestras de curvas",
        "Valores das amostras das curvas",
    ),
    "curves": ("Log curves", "Curvas del registro", "Curvas do perfil"),
    "damping": ("Damping", "Amortiguación", "Amortecimento"),
    "data_covariance": (
        "Data covariance",
        "Covarianza de datos",
        "Covariância dos dados",
    ),
    "data_std": (
        "Data standard deviations",
        "Desviaciones estándar de datos",
        "Desvios padrão dos dados",
    ),
    "decay": ("Decay voltage", "Voltaje de decaimiento", "Tensão de decaimento"),
    "density": ("Density", "Densidad", "Densidade"),
    "depth_bounds": (
        "Depth bounds",
        "Límites de profundidad",
        "Limites de profundidade",
    ),
    "depth": ("Depth", "Profundidad", "Profundidade"),
    "depth_unit_override": (
        "Explicit depth-unit override",
        "Sustitución explícita de unidad de profundidad",
        "Substituição explícita da unidade de profundidade",
    ),
    "depths": ("Depth samples", "Muestras de profundidad", "Amostras de profundidade"),
    "derivative_grids": (
        "Derivative grids",
        "Grillas de derivadas",
        "Grades de derivadas",
    ),
    "detrend": ("Remove trend", "Quitar tendencia", "Remover tendência"),
    "direction": ("Profile direction", "Dirección del perfil", "Direção do perfil"),
    "distance": ("Profile distance", "Distancia del perfil", "Distância do perfil"),
    "downward_radon_response": (
        "Downward radon response",
        "Respuesta inferior al radón",
        "Resposta inferior ao radônio",
    ),
    "downward_std": (
        "Downward detector uncertainty",
        "Incertidumbre del detector inferior",
        "Incerteza do detector inferior",
    ),
    "downward_u_rate": (
        "Downward uranium-window rate",
        "Tasa de ventana U inferior",
        "Taxa da janela U inferior",
    ),
    "drift_degree": (
        "Drift polynomial degree",
        "Grado polinómico de deriva",
        "Grau polinomial da deriva",
    ),
    "dt": ("Sampling interval", "Intervalo de muestreo", "Intervalo de amostragem"),
    "edge_exclusion": (
        "Excluded edge samples",
        "Muestras excluidas en bordes",
        "Amostras excluídas nas bordas",
    ),
    "edges": ("Network edges", "Aristas de la red", "Arestas da rede"),
    "elastic_thickness": (
        "Elastic thickness",
        "Espesor elástico",
        "Espessura elástica",
    ),
    "electrodes": (
        "Electrode coordinates",
        "Coordenadas de electrodos",
        "Coordenadas de eletrodos",
    ),
    "elevation": (
        "Receiver elevation",
        "Elevación del receptor",
        "Elevação do receptor",
    ),
    "energy_edges": (
        "Energy-bin boundaries",
        "Límites de intervalos de energía",
        "Limites dos intervalos de energia",
    ),
    "energy_peaks": ("Peak energies", "Energías de los picos", "Energias dos picos"),
    "energy_std": (
        "Energy standard deviations",
        "Desviaciones estándar de energía",
        "Desvios padrão de energia",
    ),
    "exponent": ("Cole–Cole exponent", "Exponente Cole–Cole", "Expoente Cole–Cole"),
    "exponential_rate": (
        "Exponential gain rate",
        "Tasa de ganancia exponencial",
        "Taxa de ganho exponencial",
    ),
    "exposure": ("Exposure duration", "Duración de exposición", "Duração da exposição"),
    "field": ("Observed field", "Campo observado", "Campo observado"),
    "fit_range": ("Fitting interval", "Intervalo de ajuste", "Intervalo de ajuste"),
    "frequency": ("Frequency", "Frecuencia", "Frequência"),
    "frequency_range": (
        "Frequency interval",
        "Intervalo de frecuencias",
        "Intervalo de frequências",
    ),
    "gate": ("Time gate", "Ventana temporal", "Janela temporal"),
    "gates": ("Time gates", "Ventanas temporales", "Janelas temporais"),
    "geometry_exponent": (
        "Source-geometry exponent",
        "Exponente de geometría de fuente",
        "Expoente da geometria da fonte",
    ),
    "geometry_exponents": (
        "Source-geometry exponents",
        "Exponentes de geometría de fuente",
        "Expoentes da geometria da fonte",
    ),
    "gradient_x": (
        "Eastward derivative",
        "Derivada hacia el este",
        "Derivada para leste",
    ),
    "gradient_y": (
        "Northward derivative",
        "Derivada hacia el norte",
        "Derivada para norte",
    ),
    "gradient_z": ("Upward derivative", "Derivada hacia arriba", "Derivada para cima"),
    "gradients": ("Field gradients", "Gradientes del campo", "Gradientes do campo"),
    "gravity": ("Gravity", "Gravedad", "Gravidade"),
    "gravity_std": (
        "Gravity standard deviations",
        "Desviaciones estándar de gravedad",
        "Desvios padrão de gravidade",
    ),
    "half_width": (
        "Directional half-width",
        "Semiancho direccional",
        "Semilargura direcional",
    ),
    "high": (
        "Upper bandpass frequency",
        "Frecuencia superior del pasabanda",
        "Frequência superior da banda passante",
    ),
    "imag_std": (
        "Imaginary-part standard deviations",
        "Desviaciones estándar de parte imaginaria",
        "Desvios padrão da parte imaginária",
    ),
    "impedance": ("Complex impedance", "Impedancia compleja", "Impedância complexa"),
    "inclination": ("Inclination", "Inclinación", "Inclinação"),
    "input_edges": (
        "Input-bin boundaries",
        "Límites de intervalos de entrada",
        "Limites dos intervalos de entrada",
    ),
    "instrument_ids": (
        "Instrument identifiers",
        "Identificadores de instrumentos",
        "Identificadores dos instrumentos",
    ),
    "kind": ("Response type", "Tipo de respuesta", "Tipo de resposta"),
    "known_concentrations": (
        "Calibration-standard concentrations",
        "Concentraciones de patrones de calibración",
        "Concentrações dos padrões de calibração",
    ),
    "load": (
        "Prescribed pressure load",
        "Carga de presión prescrita",
        "Carga de pressão prescrita",
    ),
    "log_power_std": (
        "Log-power standard deviations",
        "Desviaciones estándar de log-potencia",
        "Desvios padrão da log-potência",
    ),
    "low": (
        "Lower bandpass frequency",
        "Frecuencia inferior del pasabanda",
        "Frequência inferior da banda passante",
    ),
    "lta_energy_floor": (
        "Long-window energy floor",
        "Piso de energía de ventana larga",
        "Piso de energia da janela longa",
    ),
    "lta_samples": (
        "Long-window sample count",
        "Número de muestras de ventana larga",
        "Número de amostras da janela longa",
    ),
    "matrix": (
        "Linear operator matrix",
        "Matriz del operador lineal",
        "Matriz do operador linear",
    ),
    "condition": ("Condition number", "Número de condición", "Número de condição"),
    "data": ("Data records", "Registros de datos", "Registros de dados"),
    "elements": ("Array elements", "Elementos de matrices", "Elementos de matrizes"),
    "evaluations": (
        "Objective evaluations",
        "Evaluaciones del objetivo",
        "Avaliações do objetivo",
    ),
    "forward_evaluations": (
        "Forward-model evaluations",
        "Evaluaciones del modelo directo",
        "Avaliações do modelo direto",
    ),
    "gain": ("Gain", "Ganancia", "Ganho"),
    "gap": ("Profile gap", "Hueco del perfil", "Lacuna do perfil"),
    "horizontal_distance": (
        "Horizontal source distance",
        "Distancia horizontal a la fuente",
        "Distância horizontal à fonte",
    ),
    "interactions": (
        "Source–receiver interactions",
        "Interacciones fuente–receptor",
        "Interações fonte–receptor",
    ),
    "jacobian_elements": (
        "Jacobian elements",
        "Elementos del jacobiano",
        "Elementos do jacobiano",
    ),
    "kernel_elements": (
        "Kernel elements",
        "Elementos del kernel",
        "Elementos do kernel",
    ),
    "output_elements": ("Output elements", "Elementos de salida", "Elementos de saída"),
    "parameters": ("Model parameters", "Parámetros del modelo", "Parâmetros do modelo"),
    "relative_depth_error": (
        "Relative depth error",
        "Error relativo de profundidad",
        "Erro relativo de profundidade",
    ),
    "relative_residual": ("Relative residual", "Residuo relativo", "Resíduo relativo"),
    "samples": ("Sample count", "Número de muestras", "Número de amostras"),
    "solutions": ("Accepted solutions", "Soluciones aceptadas", "Soluções aceitas"),
    "text_characters": (
        "Text characters",
        "Caracteres de texto",
        "Caracteres de texto",
    ),
    "unknowns": (
        "Linear-system unknowns",
        "Incógnitas del sistema lineal",
        "Incógnitas do sistema linear",
    ),
    "weight_elements": (
        "Weight-matrix elements",
        "Elementos de la matriz de pesos",
        "Elementos da matriz de pesos",
    ),
    "windows": (
        "Processing windows",
        "Ventanas de procesamiento",
        "Janelas de processamento",
    ),
    "work": ("Work estimate", "Estimación de trabajo", "Estimativa de trabalho"),
    "noise_condition": (
        "Noise covariance condition",
        "Condición de covarianza del ruido",
        "Condição da covariância do ruído",
    ),
    "stretch": ("NMO stretch", "Estiramiento NMO", "Estiramento NMO"),
    "measured": ("Measured response", "Respuesta medida", "Resposta medida"),
    "measured_depth": ("Measured depth", "Profundidad medida", "Profundidade medida"),
    "mesh_origin": ("Mesh origin", "Origen de malla", "Origem da malha"),
    "mesh_widths": (
        "Cell widths by axis",
        "Anchos de celda por eje",
        "Larguras de célula por eixo",
    ),
    "method": ("Method", "Método", "Método"),
    "amplitude": ("Amplitude", "Amplitud", "Amplitude"),
    "valid_fraction": (
        "Valid-data fraction",
        "Fracción de datos válidos",
        "Fração de dados válidos",
    ),
    "wavenumber": ("Wavenumber", "Número de onda", "Número de onda"),
    "contrast": (
        "Reference contrast",
        "Contraste de referencia",
        "Contraste de referência",
    ),
    "fold": ("Stack fold", "Cobertura del apilado", "Cobertura do empilhamento"),
    "stack": (
        "Stack sample count",
        "Número de muestras del apilado",
        "Número de amostras do empilhamento",
    ),
    "traces": ("Trace matrix", "Matriz de trazas", "Matriz de traços"),
    "gradient": (
        "Gradient magnitude",
        "Magnitud del gradiente",
        "Magnitude do gradiente",
    ),
    "missing_value": (
        "Missing-value code",
        "Código de datos ausentes",
        "Código de dados ausentes",
    ),
    "model_a": (
        "First fitted model",
        "Primer modelo ajustado",
        "Primeiro modelo ajustado",
    ),
    "model_b": (
        "Second fitted model",
        "Segundo modelo ajustado",
        "Segundo modelo ajustado",
    ),
    "moment": ("Dipole moment", "Momento dipolar", "Momento dipolar"),
    "nky": (
        "2.5D wavenumber quadrature count",
        "Número de puntos de cuadratura 2.5D",
        "Número de pontos de quadratura 2.5D",
    ),
    "node_count": (
        "Network node count",
        "Número de nodos de la red",
        "Número de nós da rede",
    ),
    "noise_covariance": (
        "Noise covariance",
        "Covarianza del ruido",
        "Covariância do ruído",
    ),
    "noise_psd": (
        "Noise power spectrum",
        "Espectro de potencia del ruido",
        "Espectro de potência do ruído",
    ),
    "nuisance": (
        "Nuisance design matrix",
        "Matriz de términos auxiliares",
        "Matriz de termos auxiliares",
    ),
    "observation_elevation": (
        "Observation elevation",
        "Elevación de observación",
        "Elevação de observação",
    ),
    "observation_enu": (
        "Observation coordinates, ENU",
        "Coordenadas de observación, ENU",
        "Coordenadas de observação, ENU",
    ),
    "observation": (
        "Observation coordinates",
        "Coordenadas de observación",
        "Coordenadas de observação",
    ),
    "observation_mask": (
        "Observation mask",
        "Máscara de observaciones",
        "Máscara de observações",
    ),
    "observation_std": (
        "Observation standard deviations",
        "Desviaciones estándar de observaciones",
        "Desvios padrão das observações",
    ),
    "observed": ("Observed data", "Datos observados", "Dados observados"),
    "observed_dbdt": (
        "Observed magnetic time derivative",
        "Derivada temporal magnética observada",
        "Derivada temporal magnética observada",
    ),
    "observed_down": (
        "Observed downward displacement",
        "Desplazamiento descendente observado",
        "Deslocamento descendente observado",
    ),
    "observed_resistance": (
        "Observed transfer resistance",
        "Resistencia de transferencia observada",
        "Resistência de transferência observada",
    ),
    "observed_secondary_b_t": (
        "Observed secondary magnetic field (T)",
        "Campo magnético secundario observado (T)",
        "Campo magnético secundário observado (T)",
    ),
    "offsets": (
        "Source–receiver offsets",
        "Separaciones fuente–receptor",
        "Afastamentos fonte–receptor",
    ),
    "order": ("Filter order", "Orden del filtro", "Ordem do filtro"),
    "output_edges": (
        "Output-bin boundaries",
        "Límites de intervalos de salida",
        "Limites dos intervalos de saída",
    ),
    "overlap_samples": (
        "Window overlap in samples",
        "Solapamiento de ventanas en muestras",
        "Sobreposição de janelas em amostras",
    ),
    "padding_cells": ("Padding cells", "Celdas de relleno", "Células de preenchimento"),
    "pairs": ("Node pairs", "Pares de nodos", "Pares de nós"),
    "parameter_labels": (
        "Cell-zone parameter labels",
        "Etiquetas de parámetros por zona",
        "Rótulos dos parâmetros por zona",
    ),
    "peak_distance": (
        "Minimum peak spacing",
        "Separación mínima de picos",
        "Separação mínima dos picos",
    ),
    "plane_tolerance": (
        "Electrode-plane tolerance",
        "Tolerancia del plano de electrodos",
        "Tolerância do plano de eletrodos",
    ),
    "poisson_ratio": (
        "Poisson ratio",
        "Coeficiente de Poisson",
        "Coeficiente de Poisson",
    ),
    "polarity": ("Polarity", "Polaridad", "Polaridade"),
    "positions": (
        "Sample positions",
        "Posiciones de muestras",
        "Posições das amostras",
    ),
    "power": ("Spectral power", "Potencia espectral", "Potência espectral"),
    "prediction_block_size": (
        "Prediction block size",
        "Tamaño de bloque de predicción",
        "Tamanho do bloco de predição",
    ),
    "primary": ("Primary voltage", "Voltaje primario", "Tensão primária"),
    "prisms": ("Prism bounds", "Límites de prismas", "Limites dos prismas"),
    "profile_id": (
        "Profile identifiers",
        "Identificadores de perfiles",
        "Identificadores dos perfis",
    ),
    "prominence": ("Peak prominence", "Prominencia de picos", "Proeminência dos picos"),
    "quadrature_order": (
        "Quadrature order",
        "Orden de cuadratura",
        "Ordem de quadratura",
    ),
    "rank": ("Retained rank", "Rango retenido", "Posto retido"),
    "rate_covariance": (
        "Count-rate covariance",
        "Covarianza de tasas de conteo",
        "Covariância das taxas de contagem",
    ),
    "reading_std": (
        "Reading standard deviations",
        "Desviaciones estándar de lecturas",
        "Desvios padrão das leituras",
    ),
    "readings": (
        "Instrument readings",
        "Lecturas instrumentales",
        "Leituras instrumentais",
    ),
    "real_std": (
        "Real-part standard deviations",
        "Desviaciones estándar de parte real",
        "Desvios padrão da parte real",
    ),
    "receiver_axis": (
        "Receiver orientation",
        "Orientación del receptor",
        "Orientação do receptor",
    ),
    "receiver": (
        "Receiver coordinates",
        "Coordenadas del receptor",
        "Coordenadas do receptor",
    ),
    "reference": ("Reference values", "Valores de referencia", "Valores de referência"),
    "reference_a": (
        "First reference model",
        "Primer modelo de referencia",
        "Primeiro modelo de referência",
    ),
    "reference_b": (
        "Second reference model",
        "Segundo modelo de referencia",
        "Segundo modelo de referência",
    ),
    "reference_coefficients": (
        "Reference source coefficients",
        "Coeficientes de fuentes de referencia",
        "Coeficientes das fontes de referência",
    ),
    "reference_psd_floor": (
        "Reference power-spectrum floor",
        "Piso del espectro de referencia",
        "Piso do espectro de referência",
    ),
    "reference_time": ("Reference time", "Tiempo de referencia", "Tempo de referência"),
    "reference_traces": (
        "Reference-trace mask",
        "Máscara de trazas de referencia",
        "Máscara dos traços de referência",
    ),
    "regularization": (
        "Regularization operator",
        "Operador de regularización",
        "Operador de regularização",
    ),
    "relative_current": (
        "Relative waveform current",
        "Corriente relativa de la forma de onda",
        "Corrente relativa da forma de onda",
    ),
    "resistance": (
        "Transfer resistance",
        "Resistencia de transferencia",
        "Resistência de transferência",
    ),
    "resistance_std": (
        "Resistance standard deviations",
        "Desviaciones estándar de resistencia",
        "Desvios padrão de resistência",
    ),
    "resistivity": ("Resistivity", "Resistividad", "Resistividade"),
    "response": (
        "Response templates",
        "Plantillas de respuesta",
        "Modelos de resposta",
    ),
    "restoring_contrast": (
        "Restoring density contrast",
        "Contraste de densidad restaurador",
        "Contraste de densidade restaurador",
    ),
    "rho_zero": (
        "Zero-frequency resistivity",
        "Resistividad a frecuencia cero",
        "Resistividade em frequência zero",
    ),
    "rotation": (
        "Proper rotation matrix",
        "Matriz de rotación propia",
        "Matriz de rotação própria",
    ),
    "roughness": (
        "Roughness penalty",
        "Penalización de rugosidad",
        "Penalidade de rugosidade",
    ),
    "sample_count": ("Sample count", "Número de muestras", "Número de amostras"),
    "search_window": (
        "Search time interval",
        "Intervalo temporal de búsqueda",
        "Intervalo temporal de busca",
    ),
    "second_x": (
        "Second eastward derivative",
        "Segunda derivada hacia el este",
        "Segunda derivada para leste",
    ),
    "seed": ("Random seed", "Semilla aleatoria", "Semente aleatória"),
    "segment_ids": (
        "Continuous-segment identifiers",
        "Identificadores de tramos continuos",
        "Identificadores dos trechos contínuos",
    ),
    "segment_samples": (
        "Segment length in samples",
        "Longitud de tramo en muestras",
        "Comprimento do trecho em amostras",
    ),
    "sensitivity": (
        "Sensitivity matrix",
        "Matriz de sensibilidad",
        "Matriz de sensibilidade",
    ),
    "signal_psd": (
        "Signal power spectrum",
        "Espectro de potencia de señal",
        "Espectro de potência do sinal",
    ),
    "source_axis": (
        "Source orientation",
        "Orientación de la fuente",
        "Orientação da fonte",
    ),
    "source_density": (
        "Prescribed current-source density",
        "Densidad de fuentes de corriente prescrita",
        "Densidade de fontes de corrente prescrita",
    ),
    "source_enu": (
        "Source coordinates, ENU",
        "Coordenadas de fuente, ENU",
        "Coordenadas da fonte, ENU",
    ),
    "source": ("Source coordinates", "Coordenadas de fuente", "Coordenadas da fonte"),
    "source_model": (
        "Assumed source geometry",
        "Geometría de fuente supuesta",
        "Geometria da fonte assumida",
    ),
    "source_templates": (
        "Current-source templates",
        "Plantillas de fuentes de corriente",
        "Modelos de fontes de corrente",
    ),
    "space": (
        "Half-space or full-space convention",
        "Convención de semiespacio o espacio completo",
        "Convenção de semiespaço ou espaço completo",
    ),
    "spacing": (
        "Sample or grid spacing",
        "Espaciado de muestras o grilla",
        "Espaçamento de amostras ou grade",
    ),
    "spectra": ("Spectral matrix", "Matriz de espectros", "Matriz de espectros"),
    "spectrum": ("Spectrum", "Espectro", "Espectro"),
    "sta_samples": (
        "Short-window sample count",
        "Número de muestras de ventana corta",
        "Número de amostras da janela curta",
    ),
    "station_ids": (
        "Station identifiers",
        "Identificadores de estaciones",
        "Identificadores das estações",
    ),
    "stride": ("Window stride", "Paso entre ventanas", "Passo entre janelas"),
    "structural_index": ("Structural index", "Índice estructural", "Índice estrutural"),
    "target_enu": (
        "Prediction coordinates, ENU",
        "Coordenadas de predicción, ENU",
        "Coordenadas de predição, ENU",
    ),
    "tau": ("Relaxation time", "Tiempo de relajación", "Tempo de relaxação"),
    "tensor": ("Gravity tensor", "Tensor gravimétrico", "Tensor gravimétrico"),
    "text": ("Decoded LAS text", "Texto LAS decodificado", "Texto LAS decodificado"),
    "thicknesses": (
        "Finite-layer thicknesses",
        "Espesores de capas finitas",
        "Espessuras das camadas finitas",
    ),
    "threshold": ("Detection threshold", "Umbral de detección", "Limiar de detecção"),
    "time_std": (
        "Time standard deviations",
        "Desviaciones estándar de tiempos",
        "Desvios padrão dos tempos",
    ),
    "times": ("Sample times", "Tiempos de muestras", "Tempos das amostras"),
    "training_spectra": (
        "Independent training spectra",
        "Espectros de entrenamiento independientes",
        "Espectros de treinamento independentes",
    ),
    "transfer": (
        "Spectral transfer function",
        "Función de transferencia espectral",
        "Função de transferência espectral",
    ),
    "transients": (
        "Transient recordings",
        "Registros transitorios",
        "Registros transientes",
    ),
    "travel_times": ("Travel times", "Tiempos de viaje", "Tempos de viagem"),
    "unit_density_effect": (
        "Unit-density gravity effect",
        "Efecto gravimétrico de densidad unitaria",
        "Efeito gravimétrico de densidade unitária",
    ),
    "upward_ground_response": (
        "Upward terrestrial response",
        "Respuesta superior terrestre",
        "Resposta superior terrestre",
    ),
    "upward_radon_response": (
        "Upward radon response",
        "Respuesta superior al radón",
        "Resposta superior ao radônio",
    ),
    "upward_std": (
        "Upward detector uncertainty",
        "Incertidumbre del detector superior",
        "Incerteza do detector superior",
    ),
    "upward_u_rate": (
        "Upward uranium-window rate",
        "Tasa de ventana U superior",
        "Taxa da janela U superior",
    ),
    "values": ("Input values", "Valores de entrada", "Valores de entrada"),
    "velocities": ("Trial velocities", "Velocidades de prueba", "Velocidades de teste"),
    "velocity_bounds": (
        "Velocity bounds",
        "Límites de velocidad",
        "Limites de velocidade",
    ),
    "velocity": (
        "Propagation velocity",
        "Velocidad de propagación",
        "Velocidade de propagação",
    ),
    "vertical_psd_floor": (
        "Vertical-component power floor",
        "Piso de potencia de componente vertical",
        "Piso de potência da componente vertical",
    ),
    "voltage_std": (
        "Voltage standard deviations",
        "Desviaciones estándar de voltaje",
        "Desvios padrão da tensão",
    ),
    "voltage": ("Measured voltage", "Voltaje medido", "Tensão medida"),
    "waveform_times": (
        "Transmitter waveform times",
        "Tiempos de forma de onda del transmisor",
        "Tempos da forma de onda do transmissor",
    ),
    "window": ("Analysis window", "Ventana de análisis", "Janela de análise"),
    "window_names": (
        "Spectral-window names",
        "Nombres de ventanas espectrales",
        "Nomes das janelas espectrais",
    ),
    "window_rates": (
        "Spectral-window count rates",
        "Tasas de conteo por ventana espectral",
        "Taxas de contagem por janela espectral",
    ),
    "window_samples": (
        "Window length in samples",
        "Longitud de ventana en muestras",
        "Comprimento da janela em amostras",
    ),
    "window_size": ("Window size", "Tamaño de ventana", "Tamanho da janela"),
    "x": ("East coordinates", "Coordenadas este", "Coordenadas leste"),
    "xyz": ("Coordinates, x/y/z", "Coordenadas, x/y/z", "Coordenadas, x/y/z"),
    "y": ("North coordinates", "Coordenadas norte", "Coordenadas norte"),
    "young_modulus": ("Young modulus", "Módulo de Young", "Módulo de Young"),
    "zero_times": (
        "Time-zero shifts",
        "Desplazamientos de tiempo cero",
        "Deslocamentos do tempo zero",
    ),
    "cells": ("Mesh cells", "Celdas de malla", "Células da malha"),
}

PREFIXES = {
    "max_": ("Maximum: ", "Máximo: ", "Máximo: "),
    "maximum_": ("Maximum: ", "Máximo: ", "Máximo: "),
    "min_": ("Minimum: ", "Mínimo: ", "Mínimo: "),
    "minimum_": ("Minimum: ", "Mínimo: ", "Mínimo: "),
    "initial_": ("Initial: ", "Inicial: ", "Inicial: "),
    "reference_": ("Reference: ", "Referencia: ", "Referência: "),
}


FIELD_HINTS = {
    "absolute_tolerance_mgal": (
        "Bounds cover far-field approximation only. Zero uses all exact prisms; DEM, density, datum and curvature errors are separate.",
        "Las cotas cubren solo la aproximación lejana. Cero usa todos los prismas exactos; errores de DEM, densidad, datum y curvatura son independientes.",
        "As cotas cobrem somente a aproximação distante. Zero usa todos os prismas exatos; erros de MDT, densidade, datum e curvatura são separados.",
    ),
    "spacing": (
        "For these grid kernels use (north, east) spacing in metres; rows increase north. Reorient north-up raster rows explicitly.",
        "En estos kernels de grilla usa espaciado (norte, este) en metros; las filas aumentan al norte. Reorienta explícitamente las filas de un raster convencional.",
        "Nestes kernels de grade use espaçamento (norte, leste) em metros; as linhas aumentam ao norte. Reoriente explicitamente as linhas de um raster convencional.",
    ),
    "regularization_response": (
        "Data units per property unit: mGal/(kg/m³) for density, nT/SI for susceptibility. Zero disables damping.",
        "Unidades de datos por unidad de propiedad: mGal/(kg/m³) para densidad, nT/SI para susceptibilidad. Cero desactiva la amortiguación.",
        "Unidades de dados por unidade de propriedade: mGal/(kg/m³) para densidade, nT/SI para suscetibilidade. Zero desativa o amortecimento.",
    ),
    "max_inverse_gain": (
        "Property units per data unit: (kg/m³)/mGal or SI/nT. Clipped frequencies are recorded.",
        "Unidades de propiedad por unidad de datos: (kg/m³)/mGal o SI/nT. Se registran las frecuencias limitadas.",
        "Unidades de propriedade por unidade de dados: (kg/m³)/mGal ou SI/nT. As frequências limitadas são registradas.",
    ),
    "background": (
        "Prescribed density contrast (kg/m³) or susceptibility (SI); never inferred from the observed mean.",
        "Contraste de densidad (kg/m³) o susceptibilidad (SI) prescrito; nunca se infiere de la media observada.",
        "Contraste de densidade (kg/m³) ou suscetibilidade (SI) prescrito; nunca inferido da média observada.",
    ),
    "feature_mask": (
        "Explicit Boolean grid; threshold selection and geological interpretation remain your responsibility.",
        "Grilla booleana explícita; debes definir el umbral y revisar la interpretación geológica.",
        "Grade booleana explícita; defina o limiar e revise a interpretação geológica.",
    ),
    "traces": (
        "Matrix ordered as trace × time sample. Keep a uniform dt.",
        "Matriz ordenada como traza × muestra temporal. Mantén dt uniforme.",
        "Matriz ordenada como traço × amostra temporal. Mantenha dt uniforme.",
    ),
    "xyz": (
        "Rows of x/y/z coordinates, with z positive upward.",
        "Filas de coordenadas x/y/z, con z positiva hacia arriba.",
        "Linhas de coordenadas x/y/z, com z positiva para cima.",
    ),
    "gradients": (
        "One x/y/z derivative row per observation; coordinate and derivative units must agree.",
        "Una fila de derivadas x/y/z por observación; unidades de coordenadas y derivadas consistentes.",
        "Uma linha de derivadas x/y/z por observação; unidades de coordenadas e derivadas consistentes.",
    ),
    "mesh_widths": (
        "Cell-width arrays for each axis, in metres. Do not substitute cell-centre coordinates.",
        "Vectores de anchos de celda por eje, en metros. No sustituyas coordenadas de centros.",
        "Vetores de larguras de célula por eixo, em metros. Não substitua coordenadas de centros.",
    ),
    "abmn": (
        "Integer electrode-index rows A/B/M/N. The remote-electrode sentinel is -1 for B/N.",
        "Filas de índices enteros A/B/M/N. El centinela de electrodo remoto es -1 en B/N.",
        "Linhas de índices inteiros A/B/M/N. O sentinela de eletrodo remoto é -1 em B/N.",
    ),
    "thicknesses_m": (
        "Finite-layer thicknesses; the last layer is a half-space, so supply one fewer thickness than properties.",
        "Espesores de capas finitas; la última es semiespacio: proporciona un espesor menos que propiedades.",
        "Espessuras das camadas finitas; a última é semiespaço: forneça uma espessura a menos que propriedades.",
    ),
    "frequency_hz": (
        "Frequencies in Hz, not angular frequencies. Preserve response-row ordering.",
        "Frecuencias en Hz, no frecuencias angulares. Conserva el orden de filas de respuesta.",
        "Frequências em Hz, não frequências angulares. Preserve a ordem das linhas da resposta.",
    ),
    "structural_index": (
        "Explicit source assumption; compare several justified indices. Zero is a special contact case.",
        "Supuesto explícito de fuente; compara índices justificados. Cero es un caso especial de contacto.",
        "Hipótese explícita de fonte; compare índices justificáveis. Zero é um caso especial de contato.",
    ),
    "data_std": (
        "Externally justified standard deviations in the data units, not variances or arbitrary fitting weights.",
        "Desviaciones estándar justificadas en unidades del dato, no varianzas ni pesos arbitrarios.",
        "Desvios padrão justificáveis nas unidades dos dados, não variâncias nem pesos arbitrários.",
    ),
    "text": (
        "Decoded LAS file contents, not a filename. Loading text does not modify the original file.",
        "Contenido LAS decodificado, no nombre de archivo. Cargar texto no modifica el original.",
        "Conteúdo LAS decodificado, não nome de arquivo. Carregar texto não altera o original.",
    ),
}


def parameter_hint(name, locale):
    values = FIELD_HINTS.get(name)
    return values[LANGUAGES.index(locale)] if values else ""


def parameter_label(name, locale):
    index = LANGUAGES.index(locale)
    if name in BASE_LABELS:
        return BASE_LABELS[name][index]
    for suffix in sorted(UNITS, key=len, reverse=True):
        if name.endswith(suffix):
            return (
                parameter_label(name[: -len(suffix)], locale)
                + " ("
                + UNITS[suffix]
                + ")"
            )
    for prefix, labels in PREFIXES.items():
        if name.startswith(prefix):
            return labels[index] + parameter_label(name[len(prefix) :], locale)
    raise KeyError("Unauthored Core argument label: " + name)


def choices_for(operation_id, name):
    if name == "mvi_parameterization":
        return ("cartesian", "spherical")
    if name == "mvi_sensitivity_weights":
        return ("component_approximation", "mapped_exact")
    if name == "mvi_irls_update":
        return ("adaptive", "lagged")
    if operation_id == "inversion.spatial_constraints" and name == "mode":
        return ("hard", "soft")
    if operation_id == "gravity.prism_density_fit" and name == "gravity_component":
        return ("up", "down")
    if operation_id == "magnetic.prism_magnetization_fit" and name == "component":
        return ("total", "vector")
    if operation_id == "inversion.stochastic_resolution" and name == "method":
        return ("rademacher", "basis")
    if operation_id == "potential.ordinary_kriging" and name == "model":
        return ("spherical", "exponential", "gaussian")
    if operation_id in ("ip.stack_decay", "ip.fit_stack") and name == "stack_mode":
        return ("mean_of_ratios", "ratio_of_sums")
    if (
        operation_id
        in (
            "ip.cole_cole_decay",
            "ip.fit_decay",
            "ip.dispersive_forward",
            "ip.dispersive_inverse",
            "ip.waveform_decay",
            "ip.fit_waveform",
            "ip.spatial_waveform",
            "ip.fit_spatial_waveform",
            "ip.stack_decay",
            "ip.fit_stack",
        )
        and name == "normalization"
    ):
        return ("dc", "pulse")
    if (
        operation_id in ("ip.dispersive_forward", "ip.dispersive_inverse")
        and name == "domain"
    ):
        return ("frequency", "time")
    if (
        operation_id in ("potential.layer_response", "potential.apparent_property")
        and name == "kind"
    ):
        return ("density", "susceptibility")
    if operation_id == "magnetic.components" and name in (
        "input_component",
        "output_component",
    ):
        return ("total", "east", "north", "up", "down")
    if operation_id == "magnetic.dipole_fit" and name == "component":
        return ("vector", "total")
    if operation_id == "structural.phase" and name == "polarity":
        return ("both", "positive", "negative")
    if name in ("source_axis", "receiver_axis", "direction"):
        return ("x", "y", "z") if name != "direction" else ("x", "y")
    if name == "space":
        return ("half", "full")
    if operation_id == "gpr.background" and name == "method":
        return ("mean", "median")
    if operation_id == "depth.interpret_grid" and name == "method":
        return ("euler", "werner", "spi")
    if operation_id == "electrical.pde_inverse" and name == "kind":
        return ("dc", "ip")
    if operation_id == "depth.spi_profile" and name == "source_model":
        return ("contact", "thin_sheet", "horizontal_cylinder")
    return ()


def field_kind(operation_id, parameter):
    name, default = parameter.name, parameter.default
    if (
        name in ("polygons_xz_m", "anchor_std_mgal")
        or (
            operation_id == "radiometry.full_spectrum_radon"
            and name == "component_names"
        )
        or (
            operation_id == "radiometry.background_correction"
            and name in ("aircraft", "cosmic", "radon")
        )
    ):
        return "json"
    if name in ("range_m", "partial_sill", "angular_tolerance_deg"):
        return "number"
    if operation_id in (
        "ip.dispersive_forward",
        "ip.dispersive_inverse",
        "ip.spatial_waveform",
        "ip.fit_spatial_waveform",
        "ip.stack_decay",
        "ip.fit_stack",
    ) and name in (
        "chargeability",
        "tau_s",
        "exponent",
        "sample_coordinates",
        "sensitivity",
        "initial",
        "reference",
        "standard_deviation",
        "data_covariance",
    ):
        return "json"
    if name == "pulse_duration_s":
        return "number"
    if name in ("absolute_tolerance_mgal", "reference_elevation_m"):
        return "number"
    if choices_for(operation_id, name):
        return "choice"
    if name == "text":
        return "text"
    if name in ("date", "source_crs", "target_crs"):
        return "string"
    if name in (
        "background",
        "regularization_response",
        "max_inverse_gain",
        "max_abs_gain",
        "minimum_wavelength_m",
        "top_depth_m",
        "thickness_m",
        "output_mean_nt",
        "reference_mean_nt",
        "sigma_on_f",
        "noise_threshold",
        "bin_origin_degrees",
        "density_crust",
        "density_water",
        "clearance_m",
        "inclination",
        "declination",
        "field_nt",
        "minimum_distance_m",
    ):
        return "number"
    if isinstance(default, bool):
        return "boolean"
    if isinstance(default, int):
        return "integer"
    if isinstance(default, float):
        return "number"
    if isinstance(default, str):
        return "string"
    if name in (
        "dt_s",
        "low_hz",
        "high_hz",
        "structural_index",
        "beta",
        "tau_s",
        "rho_zero",
        "exponent",
    ):
        return "number"
    if name in (
        "window_samples",
        "rank",
        "node_count",
        "sample_count",
        "segment_samples",
        "sta_samples",
        "lta_samples",
    ):
        return "integer"
    return "json"


def validate_scalar(kind, value):
    """Conservative type checks only; never silently clips or coerces booleans."""
    if isinstance(value, dict) and set(value) == {"$array"}:
        return  # explicit NPZ references are resolved and checked by Core
    if value is None:
        return  # some optional arguments explicitly accept JSON null
    if kind in ("number", "integer"):
        try:
            finite = math.isfinite(value)
        except (TypeError, OverflowError):
            finite = False
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not finite:
            raise ValueError("finite_number")
        if kind == "integer" and not isinstance(value, int):
            raise ValueError("integer")
    if kind == "boolean" and not isinstance(value, bool):
        raise ValueError("boolean")
    if kind in ("string", "text", "choice") and not isinstance(value, str):
        raise ValueError("string")


def presentation_signature(function, operation_id):
    """Expose verified Euler/EM forwarding without changing the execution API."""
    signature = inspect.signature(function)
    euler = operation_id in (
        "depth.euler_window",
        "depth.euler_grid",
        "depth.euler_profile",
    )
    geometry_operations = (
        "fdem.fit_conductivity",
        "tem.fit_conductivity",
        "tem.gate_average",
    )
    if not euler and operation_id not in geometry_operations:
        return signature
    module = inspect.getmodule(function)
    helper = (
        module._euler_window
        if euler
        else module.fdem_layered
        if operation_id.startswith("fdem.")
        else module.tem_stepoff_layered
    )
    quality = inspect.signature(helper)
    allowed = (
        None
        if euler
        else {"source_m", "receiver_m", "moment_a_m2", "source_axis", "receiver_axis"}
    )
    parameters = {
        name: p
        for name, p in signature.parameters.items()
        if p.kind != inspect.Parameter.VAR_KEYWORD
    }
    for name, parameter in quality.parameters.items():
        if (
            name not in ("xyz", "field", "gradients")
            and name not in parameters
            and (allowed is None or name in allowed)
        ):
            parameters[name] = parameter.replace(kind=inspect.Parameter.KEYWORD_ONLY)
    parameters.update(
        {
            name: p
            for name, p in signature.parameters.items()
            if p.kind == inspect.Parameter.VAR_KEYWORD
        }
    )
    return signature.replace(parameters=list(parameters.values()))


DEPTH_GRID_INTERNAL_ARGUMENTS = {
    "distance",
    "gradient_x",
    "gradient_y",
    "gradient_z",
    "second_x",
    "cross_xz",
    "observation_elevation",
    "canceled",
}


def depth_grid_options(module, method):
    """Expose only options not already supplied by the grid facade itself."""
    helpers = {"euler": "euler_grid", "werner": "werner_profile", "spi": "spi_profile"}
    if method not in helpers:
        raise ValueError("Unknown grid depth method")
    operation_id = "depth." + helpers[method]
    signature = presentation_signature(getattr(module, helpers[method]), operation_id)
    supplied = {"x", "y", "elevation", "field"} | DEPTH_GRID_INTERNAL_ARGUMENTS
    options = [p for p in signature.parameters.values() if p.name not in supplied]
    if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in options):
        options.append(inspect.Parameter("options", inspect.Parameter.VAR_KEYWORD))
    return operation_id, signature.replace(parameters=options)


def validate_relationships(operation_id, parameters):
    """Only verified waveform invariants, leaving unknown/NPZ values to Core."""
    dt = parameters.get("dt_s")
    if isinstance(dt, (int, float)) and not isinstance(dt, bool) and dt <= 0:
        raise ValueError("positive_dt")
    if operation_id == "waveform.bandpass":
        low, high = parameters.get("low_hz"), parameters.get("high_hz")
        if all(
            isinstance(v, (int, float)) and not isinstance(v, bool)
            for v in (dt, low, high)
        ):
            if not 0 < low < high < 0.5 / dt:
                raise ValueError("nyquist")
    if operation_id == "gpr.dewow":
        count = parameters.get("window_samples")
        if isinstance(count, int) and (count < 3 or count % 2 == 0):
            raise ValueError("odd_window")
        traces = parameters.get("traces")
        if (
            isinstance(traces, list)
            and traces
            and isinstance(traces[0], list)
            and isinstance(count, int)
        ):
            if count > len(traces[0]):
                raise ValueError("window_length")

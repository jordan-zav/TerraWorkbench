"""Localized presentation only; stable scientific operation IDs are unchanged."""

from html import escape

from .i18n import language
from .knowledge_content import chapter_text, chapter_html

DOMAIN_TITLES = {
    "space/model-parameter": (
        "Space / model parameters",
        "Espacio / parámetros del modelo",
        "Espaço / parâmetros do modelo",
    ),
    "time-energy": ("Time / energy", "Tiempo / energía", "Tempo / energia"),
    "space-time-frequency": (
        "Space / time / frequency",
        "Espacio / tiempo / frecuencia",
        "Espaço / tempo / frequência",
    ),
    "model-parameter": (
        "Model / parameter",
        "Modelo / parámetro",
        "Modelo / parâmetro",
    ),
    "depth-space": ("Depth / space", "Profundidad / espacio", "Profundidade / espaço"),
    "measurement-space": (
        "Measurement space",
        "Espacio de mediciones",
        "Espaço de medições",
    ),
    "time/station-network": (
        "Time / station network",
        "Tiempo / red de estaciones",
        "Tempo / rede de estações",
    ),
    "space": ("Space", "Espacio", "Espaço"),
    "distance": ("Distance", "Distancia", "Distância"),
    "time": ("Time", "Tiempo", "Tempo"),
    "frequency": ("Frequency", "Frecuencia", "Frequência"),
    "depth": ("Depth", "Profundidad", "Profundidade"),
    "calibration": ("Calibration", "Calibración", "Calibração"),
    "channel": ("Channel", "Canal", "Canal"),
    "frequency-calibration": (
        "Frequency / calibration",
        "Frecuencia / calibración",
        "Frequência / calibração",
    ),
    "space-wavenumber": (
        "Space / wavenumber",
        "Espacio / número de onda",
        "Espaço / número de onda",
    ),
    "frequency-space": (
        "Frequency / space",
        "Frecuencia / espacio",
        "Frequência / espaço",
    ),
    "time-frequency": ("Time / frequency", "Tiempo / frecuencia", "Tempo / frequência"),
    "time-space": ("Time / space", "Tiempo / espacio", "Tempo / espaço"),
    "time-distance": ("Time / distance", "Tiempo / distancia", "Tempo / distância"),
    "space-time": ("Space / time", "Espacio / tiempo", "Espaço / tempo"),
    "photon-energy/spectra": (
        "Photon energy / spectra",
        "Energía de fotones / espectros",
        "Energia de fótons / espectros",
    ),
    "spatial-frequency": (
        "Spatial frequency",
        "Frecuencia espacial",
        "Frequência espacial",
    ),
    "photon-energy": ("Photon energy", "Energía de fotones", "Energia de fótons"),
    "electrode-geometry": (
        "Electrode geometry",
        "Geometría de electrodos",
        "Geometria de eletrodos",
    ),
    "electrode-network": (
        "Electrode network",
        "Red de electrodos",
        "Rede de eletrodos",
    ),
    "network": ("Network", "Red", "Rede"),
    "parameter": ("Parameter", "Parámetro", "Parâmetro"),
    "model": ("Model", "Modelo", "Modelo"),
    "ensemble": ("Ensemble", "Conjunto", "Conjunto"),
    "uncertainty": ("Uncertainty", "Incertidumbre", "Incerteza"),
}


def domain_label(domain):
    return DOMAIN_TITLES[domain][("en", "es", "pt").index(language())]


# Titles are authored, not inferred by replacing pieces of API identifiers.
OPERATION_TITLES = {
    "gravity.polygon_forward": (
        "2D polygon gravity",
        "Gravedad de polígonos 2D",
        "Gravidade de polígonos 2D",
    ),
    "gravity.polygon_density_fit": (
        "Fit polygon density contrasts",
        "Ajustar contrastes de densidad poligonales",
        "Ajustar contrastes de densidade poligonais",
    ),
    "radiometry.upward_window_radon": (
        "Calibrated upward-window radon",
        "Radón calibrado con ventana superior",
        "Radônio calibrado com janela superior",
    ),
    "radiometry.window_radon": (
        "Calibrated four-window radon separation",
        "Separación calibrada de radón con cuatro ventanas",
        "Separação calibrada de radônio com quatro janelas",
    ),
    "radiometry.full_spectrum_radon": (
        "Full-spectrum radon separation",
        "Separación de radón de espectro completo",
        "Separação de radônio de espectro completo",
    ),
    "radiometry.background_correction": (
        "Time-varying radiometric backgrounds",
        "Fondos radiométricos variables en el tiempo",
        "Fundos radiométricos variáveis no tempo",
    ),
    "potential.empirical_variogram": (
        "Empirical planar variogram",
        "Variograma plano empírico",
        "Variograma plano empírico",
    ),
    "potential.ordinary_kriging": (
        "Local ordinary kriging",
        "Kriging ordinario local",
        "Krigagem ordinária local",
    ),
    "gravity.terrain_adaptive": (
        "Adaptive DEM gravity at stations",
        "Atracción del DEM en estaciones (adaptativa)",
        "Atração do MDT nas estações (adaptativa)",
    ),
    "magnetic.components": (
        "Magnetic component conversion",
        "Conversión de componentes magnéticas",
        "Conversão de componentes magnéticas",
    ),
    "magnetic.gradient_tmi": (
        "TMI from measured gradients",
        "Campo magnético total desde gradientes",
        "Campo magnético total a partir de gradientes",
    ),
    "potential.radial_filter": (
        "Tabulated radial filter",
        "Filtro radial tabulado",
        "Filtro radial tabelado",
    ),
    "potential.layer_response": (
        "Finite-layer property response",
        "Respuesta de propiedades de una capa finita",
        "Resposta de propriedades de uma camada finita",
    ),
    "potential.apparent_property": (
        "Apparent density or susceptibility",
        "Densidad o susceptibilidad aparente",
        "Densidade ou suscetibilidade aparente",
    ),
    "magnetic.dipole_forward": (
        "Compact magnetic dipole response",
        "Respuesta de dipolos magnéticos compactos",
        "Resposta de dipolos magnéticos compactos",
    ),
    "magnetic.dipole_fit": (
        "Fit compact magnetic dipoles",
        "Ajustar dipolos magnéticos compactos",
        "Ajustar dipolos magnéticos compactos",
    ),
    "structural.phase": (
        "Multiscale phase attributes",
        "Atributos de fase multiescala",
        "Atributos de fase multiescala",
    ),
    "structural.texture": (
        "Local grid texture",
        "Textura local de grilla",
        "Textura local da grade",
    ),
    "structural.orientation_entropy": (
        "Axial orientation entropy",
        "Entropía de orientaciones axiales",
        "Entropia de orientações axiais",
    ),
    "structural.skeleton_paths": (
        "Trace feature skeleton paths",
        "Trazar caminos del esqueleto de rasgos",
        "Traçar caminhos do esqueleto de feições",
    ),
    "magnetic.igrf": (
        "IGRF reference field",
        "Campo de referencia IGRF",
        "Campo de referência IGRF",
    ),
    "potential.reproject_xy": (
        "Reproject horizontal coordinates",
        "Reproyectar coordenadas horizontales",
        "Reprojetar coordenadas horizontais",
    ),
    "gravity.terrain_prisms": (
        "Finite-prism terrain correction",
        "Corrección de terreno con prismas finitos",
        "Correção de terreno com prismas finitos",
    ),
    "depth.euler_window": ("Euler window", "Ventana Euler", "Janela Euler"),
    "depth.euler_grid": ("Euler grid", "Euler en grilla", "Euler em grade"),
    "depth.euler_profile": ("Euler profile", "Euler en perfil", "Euler em perfil"),
    "depth.werner_profile": ("Werner profile", "Werner en perfil", "Werner em perfil"),
    "depth.spi_profile": (
        "Source parameter imaging",
        "Imagen de parámetros de fuente",
        "Imagem de parâmetros de fonte",
    ),
    "depth.interpret_grid": (
        "Grid source-depth interpretation",
        "Interpretación de profundidad en grilla",
        "Interpretação de profundidade em grade",
    ),
    "sp.pde_forward": (
        "PDE self-potential forward model",
        "Modelo directo PDE de potencial espontáneo",
        "Modelo direto PDE de potencial espontâneo",
    ),
    "sp.pde_source_fit": (
        "PDE source fitting",
        "Ajuste de fuentes PDE",
        "Ajuste de fontes PDE",
    ),
    "radiometry.fit_response": (
        "Detector response calibration",
        "Calibración de respuesta del detector",
        "Calibração da resposta do detector",
    ),
    "radiometry.calibrated_concentrations": (
        "Calibrated concentrations",
        "Concentraciones calibradas",
        "Concentrações calibradas",
    ),
    "em.fit_complex_response": (
        "Fit complex instrument response",
        "Ajustar respuesta instrumental compleja",
        "Ajustar resposta instrumental complexa",
    ),
    "em.apply_complex_response": (
        "Apply complex response calibration",
        "Aplicar calibración de respuesta compleja",
        "Aplicar calibração de resposta complexa",
    ),
    "regional.elastic_flexure": (
        "Elastic plate flexure",
        "Flexura de placa elástica",
        "Flexura de placa elástica",
    ),
    "regional.elastic_thickness_scan": (
        "Elastic thickness sensitivity",
        "Sensibilidad al espesor elástico",
        "Sensibilidade à espessura elástica",
    ),
    "fdem.3d_forward": (
        "3D frequency-domain EM",
        "EM 3D en frecuencia",
        "EM 3D em frequência",
    ),
    "fdem.3d_zone_fit": (
        "Fit 3D conductivity zones",
        "Ajustar zonas de conductividad 3D",
        "Ajustar zonas de condutividade 3D",
    ),
    "radiometry.paired_radon": (
        "Paired-detector radon estimation",
        "Estimación de radón con detectores pareados",
        "Estimativa de radônio com detectores pareados",
    ),
    "borehole.read_las": ("Read LAS logs", "Leer registros LAS", "Ler perfis LAS"),
    "borehole.update_las": (
        "Update LAS curves",
        "Actualizar curvas LAS",
        "Atualizar curvas LAS",
    ),
    "electrical.pde_forward": (
        "DC resistivity PDE forward model",
        "Modelo directo PDE de resistividad DC",
        "Modelo direto PDE de resistividade DC",
    ),
    "electrical.pde_inverse": (
        "DC resistivity PDE inversion",
        "Inversión PDE de resistividad DC",
        "Inversão PDE de resistividade DC",
    ),
    "waveform.bandpass": (
        "Trace bandpass",
        "Pasabanda de trazas",
        "Banda passante de traços",
    ),
    "gpr.dewow": (
        "Remove low-frequency drift",
        "Quitar deriva de baja frecuencia",
        "Remover deriva de baixa frequência",
    ),
    "gpr.background": (
        "Remove shared trace background",
        "Quitar fondo compartido entre trazas",
        "Remover fundo compartilhado entre traços",
    ),
    "gpr.time_zero": (
        "Trace time-zero correction",
        "Corrección de tiempo cero por traza",
        "Correção do tempo zero por traço",
    ),
    "gpr.time_gain": (
        "Time-dependent trace gain",
        "Ganancia de trazas dependiente del tiempo",
        "Ganho de traços dependente do tempo",
    ),
    "gpr.hyperbola_fit": (
        "Diffraction hyperbola fitting",
        "Ajuste de hipérbola de difracción",
        "Ajuste de hipérbole de difração",
    ),
    "seismic.nmo_stack": (
        "Normal-moveout stack",
        "Apilado con corrección NMO",
        "Empilhamento com correção NMO",
    ),
    "seismic.sta_lta_picks": (
        "STA/LTA event picks",
        "Detección de eventos STA/LTA",
        "Detecção de eventos STA/LTA",
    ),
    "passive.hvsr": (
        "Horizontal/vertical spectral ratio",
        "Razón espectral horizontal/vertical",
        "Razão espectral horizontal/vertical",
    ),
    "passive.phase_velocity": (
        "Phase-velocity scan",
        "Barrido de velocidad de fase",
        "Varredura de velocidade de fase",
    ),
    "sp.prescribed_source_forward": (
        "Prescribed-source self potential",
        "Potencial espontáneo de fuentes prescritas",
        "Potencial espontâneo de fontes prescritas",
    ),
    "sp.current_inverse": (
        "Self-potential current inversion",
        "Inversión de corriente de potencial espontáneo",
        "Inversão de corrente de potencial espontâneo",
    ),
    "sp.reference_network": (
        "Reference-electrode network",
        "Red de electrodos de referencia",
        "Rede de eletrodos de referência",
    ),
    "borehole.trajectory": (
        "Borehole trajectory",
        "Trayectoria del pozo",
        "Trajetória do poço",
    ),
    "borehole.depth_qc": (
        "Log depth quality control",
        "Control de calidad de profundidad",
        "Controle de qualidade de profundidade",
    ),
    "inversion.linear_ensemble": (
        "Linear inversion ensemble",
        "Conjunto de inversiones lineales",
        "Conjunto de inversões lineares",
    ),
    "spectra.matched_layers": (
        "Matched spectral layers",
        "Capas espectrales ajustadas",
        "Camadas espectrais ajustadas",
    ),
    "regional.admittance_coherence": (
        "Admittance and coherence",
        "Admitancia y coherencia",
        "Admitância e coerência",
    ),
    "radiometry.mnf": (
        "Minimum-noise-fraction denoising",
        "Reducción de ruido por fracción mínima de ruido",
        "Redução de ruído por fração mínima de ruído",
    ),
    "tem.waveform_forward": (
        "Recorded-waveform TEM forward model",
        "Modelo directo TEM con forma de onda",
        "Modelo direto TEM com forma de onda",
    ),
    "tem.fit_conductivity": (
        "Fit TEM conductivity",
        "Ajustar conductividad TEM",
        "Ajustar condutividade TEM",
    ),
    "tem.stack_transients": (
        "Stack recorded transients",
        "Apilar transitorios registrados",
        "Empilhar transientes registrados",
    ),
    "tem.integrate_recorded_gates": (
        "Integrate recorded time gates",
        "Integrar ventanas temporales registradas",
        "Integrar janelas temporais registradas",
    ),
    "potential.equivalent_sources": (
        "Equivalent-source prediction",
        "Predicción mediante fuentes equivalentes",
        "Predição por fontes equivalentes",
    ),
    "spectra.grid_psd": (
        "Grid power spectrum",
        "Espectro de potencia de grilla",
        "Espectro de potência da grade",
    ),
    "spectra.directional_bins": (
        "Directional spectral bins",
        "Intervalos espectrales direccionales",
        "Intervalos espectrais direcionais",
    ),
    "spectra.depth_fit": (
        "Spectral depth fitting",
        "Ajuste de profundidad espectral",
        "Ajuste de profundidade espectral",
    ),
    "spectra.wiener_inverse": (
        "Wiener inverse transfer",
        "Transferencia inversa Wiener",
        "Transferência inversa Wiener",
    ),
    "gravity.tensor_invariants": (
        "Gravity tensor invariants",
        "Invariantes del tensor gravimétrico",
        "Invariantes do tensor gravimétrico",
    ),
    "gravity.rotate_tensor": (
        "Rotate gravity tensor",
        "Rotar tensor gravimétrico",
        "Rotacionar tensor gravimétrico",
    ),
    "gravity.prism_tensor": (
        "Prism gravity tensor",
        "Tensor gravimétrico de prismas",
        "Tensor gravimétrico de prismas",
    ),
    "gravity.network_adjustment": (
        "Gravity network adjustment",
        "Ajuste de red gravimétrica",
        "Ajuste da rede gravimétrica",
    ),
    "gravity.density_fit": (
        "Fit reduction density",
        "Ajustar densidad de reducción",
        "Ajustar densidade de redução",
    ),
    "radiometry.energy_calibration": (
        "Spectrum energy calibration",
        "Calibración energética del espectro",
        "Calibração energética do espectro",
    ),
    "radiometry.energy_rebin": (
        "Rebin energy channels",
        "Reagrupar canales de energía",
        "Reagrupar canais de energia",
    ),
    "radiometry.nasvd": (
        "Noise-adjusted SVD",
        "SVD ajustada por ruido",
        "SVD ajustada por ruído",
    ),
    "radiometry.integrate_windows": (
        "Integrate spectral windows",
        "Integrar ventanas espectrales",
        "Integrar janelas espectrais",
    ),
    "radiometry.covariance_transform": (
        "Propagate spectral covariance",
        "Propagar covarianza espectral",
        "Propagar covariância espectral",
    ),
    "radiometry.full_spectrum_fit": (
        "Full-spectrum fitting",
        "Ajuste de espectro completo",
        "Ajuste de espectro completo",
    ),
    "electrical.validate_abmn": (
        "Validate electrode arrays",
        "Validar arreglos de electrodos",
        "Validar arranjos de eletrodos",
    ),
    "electrical.geometric_factor": (
        "Electrode geometric factor",
        "Factor geométrico de electrodos",
        "Fator geométrico de eletrodos",
    ),
    "electrical.apparent_resistivity": (
        "Apparent resistivity",
        "Resistividad aparente",
        "Resistividade aparente",
    ),
    "electrical.reciprocal_qc": (
        "Reciprocal measurement QC",
        "Control de mediciones recíprocas",
        "Controle de medições recíprocas",
    ),
    "electrical.layered_forward": (
        "Layered-earth DC response",
        "Respuesta DC de tierra estratificada",
        "Resposta DC de terra estratificada",
    ),
    "electrical.fit_resistivity": (
        "Fit layered DC resistivity",
        "Ajustar resistividad DC estratificada",
        "Ajustar resistividade DC estratificada",
    ),
    "ip.integrated_chargeability": (
        "Integrated chargeability",
        "Cargabilidad integrada",
        "Cargabilidade integrada",
    ),
    "sip.cole_cole_resistivity": (
        "Cole–Cole complex resistivity",
        "Resistividad compleja Cole–Cole",
        "Resistividade complexa Cole–Cole",
    ),
    "sip.fit_cole_cole": (
        "Fit Cole–Cole spectrum",
        "Ajustar espectro Cole–Cole",
        "Ajustar espectro Cole–Cole",
    ),
    "ip.stack_decay": (
        "IP stack from selected off-periods",
        "Apilado IP de intervalos sin corriente seleccionados",
        "Empilhamento IP de intervalos sem corrente selecionados",
    ),
    "ip.fit_stack": (
        "IP inversion with explicit stacking",
        "Inversión IP con apilado explícito",
        "Inversão IP com empilhamento explícito",
    ),
    "ip.waveform_decay": (
        "IP decay from a prescribed current history",
        "Decaimiento IP con historial de corriente prescrito",
        "Decaimento IP com histórico de corrente prescrito",
    ),
    "ip.fit_waveform": (
        "IP inversion with a prescribed current history",
        "Inversión IP con historial de corriente prescrito",
        "Inversão IP com histórico de corrente prescrito",
    ),
    "ip.spatial_waveform": (
        "Spatial IP response with a prescribed current history",
        "Respuesta IP espacial con historial de corriente prescrito",
        "Resposta IP espacial com histórico de corrente prescrito",
    ),
    "ip.fit_spatial_waveform": (
        "Spatial IP inversion with a prescribed current history",
        "Inversión IP espacial con historial de corriente prescrito",
        "Inversão IP espacial com histórico de corrente prescrito",
    ),
    "ip.cole_cole_decay": (
        "Cole–Cole pulse decay",
        "Decaimiento de pulso Cole–Cole",
        "Decaimento de pulso Cole–Cole",
    ),
    "ip.fit_decay": (
        "Invert IP decay",
        "Invertir decaimiento IP",
        "Inverter decaimento IP",
    ),
    "ip.sensitivity": (
        "Static IP spatial sensitivity",
        "Sensibilidad espacial de IP estática",
        "Sensibilidade espacial de IP estática",
    ),
    "ip.dispersive_forward": (
        "Dispersive IP spatial response",
        "Respuesta espacial de IP dispersiva",
        "Resposta espacial de IP dispersiva",
    ),
    "ip.dispersive_inverse": (
        "Dispersive IP spatial inversion",
        "Inversión espacial de IP dispersiva",
        "Inversão espacial de IP dispersiva",
    ),
    "fdem.layered_forward": (
        "Layered-earth FDEM response",
        "Respuesta FDEM de tierra estratificada",
        "Resposta FDEM de terra estratificada",
    ),
    "fdem.fit_conductivity": (
        "Fit FDEM conductivity",
        "Ajustar conductividad FDEM",
        "Ajustar condutividade FDEM",
    ),
    "tem.stepoff_forward": (
        "TEM step-off response",
        "Respuesta TEM al apagado",
        "Resposta TEM ao desligamento",
    ),
    "tem.gate_average": (
        "TEM gate averages",
        "Promedios de ventanas TEM",
        "Médias de janelas TEM",
    ),
    "mt.layered_forward": (
        "Layered-earth MT response",
        "Respuesta MT de tierra estratificada",
        "Resposta MT de terra estratificada",
    ),
    "mt.apparent_resistivity_phase": (
        "MT apparent resistivity and phase",
        "Resistividad aparente y fase MT",
        "Resistividade aparente e fase MT",
    ),
    "mt.impedance_units": (
        "MT impedance unit conversion",
        "Conversión de unidades de impedancia MT",
        "Conversão de unidades de impedância MT",
    ),
    "mt.phase_tensor": ("MT phase tensor", "Tensor de fase MT", "Tensor de fase MT"),
    "mt.fit_resistivity": (
        "Fit MT resistivity",
        "Ajustar resistividad MT",
        "Ajustar resistividade MT",
    ),
    "inversion.linear_resolution": (
        "Linear model resolution",
        "Resolución del modelo lineal",
        "Resolução do modelo linear",
    ),
    "inversion.stochastic_resolution": (
        "Matrix-free linear uncertainty and resolution",
        "Incertidumbre y resolución lineal sin matriz completa",
        "Incerteza e resolução linear sem matriz completa",
    ),
    "inversion.point_spread": (
        "Selected linear point-spread columns",
        "Columnas seleccionadas de resolución puntual lineal",
        "Colunas selecionadas de resolução pontual linear",
    ),
    "inversion.spatial_constraints": (
        "Explicit geological support and depth priors",
        "Restricciones geológicas explícitas de soporte y profundidad",
        "Restrições geológicas explícitas de suporte e profundidade",
    ),
    "inversion.recovery_metrics": (
        "Truth-based model recovery assessment",
        "Evaluación de recuperación frente a un modelo verdadero",
        "Avaliação de recuperação frente a um modelo verdadeiro",
    ),
    "gravity.prism_density_fit": (
        "Fixed-prism density inversion",
        "Inversión de densidad de prismas fijos",
        "Inversão de densidade de prismas fixos",
    ),
    "magnetic.prism_magnetization_fit": (
        "Fixed-prism magnetization inversion",
        "Inversión de magnetización de prismas fijos",
        "Inversão de magnetização de prismas fixos",
    ),
    "inversion.reference_doi": (
        "Reference-model depth of investigation",
        "Profundidad de investigación por modelo de referencia",
        "Profundidade de investigação por modelo de referência",
    ),
}

CHAPTER_BY_FAMILY = {
    "magnetic": "magnetics",
    "structural": "gridding",
    "depth": "depth",
    "sp": "electrical",
    "radiometry": "radiometry",
    "em": "em",
    "fdem": "em",
    "tem": "em",
    "mt": "em",
    "regional": "gravity",
    "gravity": "gravity",
    "borehole": "borehole",
    "electrical": "electrical",
    "ip": "electrical",
    "sip": "electrical",
    "waveform": "waveforms",
    "gpr": "waveforms",
    "seismic": "waveforms",
    "passive": "waveforms",
    "inversion": "inversion",
    "potential": "gridding",
    "spectra": "depth",
}


def operation_title(operation_id):
    return OPERATION_TITLES[operation_id][("en", "es", "pt").index(language())]


OPERATION_NOTES = {
    "inversion.spatial_constraints": (
        "Support/depth windows are caller-supplied hypotheses. Hard mode fixes the outside background; soft mode adds regularization weights. Membership uses cell centers. Cartesian MVI limits constrain components, not amplitude or angular cones.",
        "Las ventanas de soporte/profundidad son hipótesis aportadas por el usuario. El modo duro fija el fondo exterior; el modo suave añade pesos de regularización. La pertenencia usa centros de celda. Los límites MVI restringen componentes, no amplitud ni conos angulares.",
        "As janelas de suporte/profundidade são hipóteses fornecidas pelo usuário. O modo rígido fixa o fundo externo; o modo suave adiciona pesos de regularização. A inclusão usa centros de célula. Os limites MVI restringem componentes, não amplitude nem cones angulares.",
    ),
    "inversion.recovery_metrics": (
        "Requires independently known truth and predeclared tolerances. Location, volume, support, contrast and direction are assessed separately from fitting anomalies. Truth is used for scoring only; passing synthetic cases does not certify a field model.",
        "Requiere una verdad conocida independientemente y tolerancias predeclaradas. Evalúa ubicación, volumen, soporte, contraste y dirección por separado del ajuste de anomalías. La verdad solo se usa para puntuar; aprobar casos sintéticos no certifica un modelo de campo.",
        "Requer verdade conhecida independentemente e tolerâncias predeclaradas. Avalia localização, volume, suporte, contraste e direção separadamente do ajuste de anomalias. A verdade é usada apenas na avaliação; aprovar casos sintéticos não certifica um modelo de campo.",
    ),
    "gravity.prism_density_fit": (
        "Requires known prism geometry and independent absolute errors. Signed density contrasts are kg/m3; mGal gravity follows the explicit up/down component. Covariance excludes geometry uncertainty.",
        "Requiere geometría de prismas conocida y errores absolutos independientes. Los contrastes de densidad con signo están en kg/m3; la gravedad en mGal sigue la componente explícita arriba/abajo. La covarianza excluye incertidumbre geométrica.",
        "Requer geometria dos prismas conhecida e erros absolutos independentes. Os contrastes de densidade com sinal estão em kg/m3; a gravidade em mGal segue a componente explícita cima/baixo. A covariância exclui incerteza geométrica.",
    ),
    "magnetic.prism_magnetization_fit": (
        "Known geometry only: estimates physical ENU magnetization in A/m, not susceptibility. Total-field data use a small-anomaly projection with explicit inducing I/D. Background offsets are optional; covariance excludes shape and calibration errors.",
        "Solo para geometría conocida: estima magnetización física ENU en A/m, no susceptibilidad. Los datos de campo total usan una proyección de anomalía pequeña con I/D inductor explícito. Los fondos son opcionales; la covarianza excluye errores de forma y calibración.",
        "Somente para geometria conhecida: estima magnetização física ENU em A/m, não suscetibilidade. Os dados de campo total usam uma projeção de pequena anomalia com I/D indutor explícito. Os fundos são opcionais; a covariância exclui erros de forma e calibração.",
    ),
    "inversion.stochastic_resolution": (
        "Fixed unconstrained Gaussian model only. Probing errors describe Monte Carlo variability, not geological uncertainty; negative variance estimates remain flagged. Native Python also accepts sparse matrices and operators with true adjoints.",
        "Solo para un modelo gaussiano fijo sin restricciones. Los errores de sondeo describen variabilidad Monte Carlo, no incertidumbre geológica; las estimaciones negativas de varianza permanecen señaladas. Python también acepta matrices dispersas y operadores con adjuntos correctos.",
        "Somente para um modelo gaussiano fixo sem restrições. Os erros de sondagem descrevem variabilidade Monte Carlo, não incerteza geológica; estimativas negativas de variância permanecem sinalizadas. Python também aceita matrizes esparsas e operadores com adjuntos corretos.",
    ),
    "inversion.point_spread": (
        "Outputs are model-coordinate columns of covariance and resolution, conditional on fixed G, noise, beta and prior. A point-spread column is not an averaging-kernel row or geological DOI.",
        "Las salidas son columnas de covarianza y resolución en coordenadas del modelo, condicionadas a G, ruido, beta y prior fijos. Una columna de resolución puntual no es una fila de promediado ni un DOI geológico.",
        "As saídas são colunas de covariância e resolução nas coordenadas do modelo, condicionadas a G, ruído, beta e prior fixos. Uma coluna de resolução pontual não é uma linha de promediação nem um DOI geológico.",
    ),
    "gravity.polygon_forward": (
        "Infinite-strike 2D polygons: x and upward z in metres, density contrast in kg/m3, downward gravity in mGal. Finite-end corrections are excluded.",
        "Polígonos 2D de extensión infinita: x y z positiva hacia arriba en metros, contraste de densidad en kg/m3 y gravedad hacia abajo en mGal. No incluye correcciones de extremos finitos.",
        "Polígonos 2D de extensão infinita: x e z positiva para cima em metros, contraste de densidade em kg/m3 e gravidade para baixo em mGal. Não inclui correções de extremos finitos.",
    ),
    "gravity.polygon_density_fit": (
        "Geometry remains fixed. Signed density contrasts and optional offset use known reading errors; covariance is conditional on the supplied geometry and noise.",
        "La geometría permanece fija. Los contrastes de densidad con signo y el desplazamiento opcional usan errores conocidos; la covarianza depende de la geometría y del ruido indicados.",
        "A geometria permanece fixa. Os contrastes de densidade com sinal e o deslocamento opcional usam erros conhecidos; a covariância depende da geometria e do ruído indicados.",
    ),
    "gravity.network_adjustment": (
        "References are exact unless anchor standard deviations are supplied for every reference. Independent uncertain references propagate shared datum covariance.",
        "Las referencias son exactas salvo que se indiquen desviaciones estándar para todas. Las referencias inciertas independientes propagan la covarianza común del datum.",
        "As referências são exatas salvo quando são indicados desvios padrão para todas. As referências incertas independentes propagam a covariância comum do datum.",
    ),
    "radiometry.upward_window_radon": (
        "IAEA equation 5.7 requires six measured calibration coefficients and rate covariance. Signed estimates are retained; this does not infer atmospheric Bq/m3. Shared calibration correlations between records are not materialized.",
        "La ecuación 5.7 de IAEA requiere seis coeficientes de calibración medidos y covarianza de tasas. Conserva estimaciones con signo; no infiere Bq/m3 atmosféricos. No materializa correlaciones entre registros por calibración compartida.",
        "A equação 5.7 da IAEA requer seis coeficientes de calibração medidos e covariância das taxas. Mantém estimativas com sinal; não infere Bq/m3 atmosféricos. Não materializa correlações entre registros por calibração compartilhada.",
    ),
    "radiometry.window_radon": (
        "Supply a calibrated four-window response and full rate covariance. Radon subtraction includes its correlation with the input windows. An arbitrary low-energy window is not a calibrated spectral-ratio correction.",
        "Indica una respuesta calibrada de cuatro ventanas y la covarianza completa de tasas. La sustracción de radón incluye su correlación con las ventanas de entrada. Una ventana de baja energía arbitraria no constituye una corrección calibrada por cociente espectral.",
        "Indique uma resposta calibrada de quatro janelas e a covariância completa das taxas. A subtração de radônio inclui sua correlação com as janelas de entrada. Uma janela arbitrária de baixa energia não constitui uma correção calibrada por razão espectral.",
    ),
    "radiometry.full_spectrum_radon": (
        "Supply calibrated response templates and independent channel errors. Signed components, residual misfit and same-spectrum subtraction variance remain visible. Template and energy-calibration errors are excluded.",
        "Indica plantillas de respuesta calibradas y errores independientes por canal. Conserva componentes con signo, desajuste residual y varianza de sustracción del mismo espectro. Excluye errores de plantillas y calibración energética.",
        "Indique modelos de resposta calibrados e erros independentes por canal. Mantém componentes com sinal, desajuste residual e variância de subtração do mesmo espectro. Exclui erros dos modelos e da calibração energética.",
    ),
    "radiometry.background_correction": (
        "Aircraft, cosmic and radon backgrounds may be scalar or time varying in matching rate units. Negative corrected rates and missing NaN values are retained.",
        "Los fondos de aeronave, cósmico y radón pueden ser escalares o variables en el tiempo, en las mismas unidades de tasa. Conserva tasas corregidas negativas y valores faltantes NaN.",
        "Os fundos da aeronave, cósmico e de radônio podem ser escalares ou variáveis no tempo, nas mesmas unidades de taxa. Mantém taxas corrigidas negativas e valores ausentes NaN.",
    ),
    "potential.empirical_variogram": (
        "Use projected metres and explicit lag edges. Above the pair budget, draws use replacement and a recorded seed; sampled pair counts do not establish independent uncertainty. Axial azimuth is clockwise from north.",
        "Usa metros proyectados y límites de intervalos explícitos. Sobre el presupuesto de pares, el muestreo usa reemplazo y semilla registrada; el conteo no establece incertidumbre independiente. El azimut axial se mide desde el norte en sentido horario.",
        "Use metros projetados e limites de intervalos explícitos. Acima do limite de pares, a amostragem usa reposição e semente registrada; a contagem não estabelece incerteza independente. O azimute axial é medido do norte no sentido horário.",
    ),
    "potential.ordinary_kriging": (
        "Use projected metres and explicit variogram parameters. Nugget is process variance, not measurement-error smoothing. Exact observations are preserved; zero search radius permits extrapolation. Reported variance conditions on the selected model.",
        "Usa metros proyectados y parámetros de variograma explícitos. El efecto pepita representa varianza del proceso, no suavizado por error de medición. Conserva observaciones exactas; radio cero permite extrapolar. La varianza depende del modelo elegido.",
        "Use metros projetados e parâmetros de variograma explícitos. O efeito pepita representa variância do processo, não suavização por erro de medição. Mantém observações exatas; raio zero permite extrapolar. A variância depende do modelo escolhido.",
    ),
}


def operation_guidance(operation_id):
    text = chapter_text(CHAPTER_BY_FAMILY[operation_id.split(".")[0]], language())
    notes = OPERATION_NOTES.get(operation_id)
    return (
        text + "\n\n" + notes[("en", "es", "pt").index(language())] if notes else text
    )


def operation_guidance_html(operation_id):
    text = chapter_html(CHAPTER_BY_FAMILY[operation_id.split(".")[0]], language())
    notes = OPERATION_NOTES.get(operation_id)
    return (
        text + "<p>" + escape(notes[("en", "es", "pt").index(language())]) + "</p>"
        if notes
        else text
    )

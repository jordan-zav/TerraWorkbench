# Manual práctico de TerraWorkbench

Los mismos capítulos, ecuaciones y enlaces primarios están disponibles en inglés, español y portugués. Las referencias históricas de campos potenciales se conservan por separado. Este manual documenta supuestos y controles; no afirma cobertura completa ni validación de campo.

## Importación GRD y flujos de filtros

Importa la grilla, verifica coordenadas y unidades, elige un filtro, edita sus parámetros y ejecuta la secuencia. El lector GRD binario Geosoft crea un GeoTIFF en la ubicación elegida; no cambia el original. La extensión GRD por sí sola no identifica la codificación. Las salidas del flujo son temporales si no eliges carpeta. Una carpeta elegida recibe una subcarpeta por ejecución, receta e intermedios opcionales. Guardar la pila permite reutilizar parámetros, no certifica datos de entrada idénticos. Revisa cada etapa antes de interpretar la imagen final.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

Contexto del capítulo:

- [GDAL raster data model](https://gdal.org/en/stable/user/raster_data_model.html)

## Coordenadas, unidades y datos ausentes

Asignar un SRC describe coordenadas existentes; reproyectar las cambia. No asignes otro SRC para reparar datos mal ubicados. Registra unidades horizontales, referencia de elevación y si la altura corresponde al terreno, sensor o separación sobre el terreno. El procesamiento basado en distancias requiere un SRC proyectado métrico. El tamaño de celda y el espaciado de muestras son distintos. Comprueba máscaras NoData, orientación, centros de píxel y escala/desplazamiento GDAL al comparar rásteres. Cero es una medición, no un marcador automático de ausencia. Un SRC local no certifica una transformación de datum vertical.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

Contexto del capítulo:

- [GDAL raster data model](https://gdal.org/en/stable/user/raster_data_model.html)

## Bases de datos, canales y trazabilidad

Conserva canales importados inmutables y crea versiones derivadas con unidades explícitas y nombres coherentes. El almacén combina un catálogo SQLite y datos Parquet por columnas; lee solo los canales necesarios. Revisa separador, fila de encabezados, separador decimal y ausencias al importar. Los filtros deben respetar líneas, huecos y muestreo. Un límite de seguridad por tramo no equivale a capacidad total de la base. Las recetas identifican versiones y pasos. Reutilizar una receta después de reemplazar una entrada exige revisión. El linaje documenta la historia, no garantiza corrección científica.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

Contexto del capítulo:

- [GDAL raster data model](https://gdal.org/en/stable/user/raster_data_model.html)

## Interpolación y control de líneas

Corrige tiempos, estación base y efectos de adquisición antes de nivelar cruces e interpolar. Examina residuos por línea y dirección. El tamaño de celda no recupera longitudes de onda no muestreadas. Compara métodos con validación espacial, no con vecinos aleatorios que filtran información espacial. Registra radio, vecinos, suavizado y distancia de exclusión. Un rectángulo completo puede contener extrapolación sin soporte. Enmascara celdas distantes y compara otros espaciados. Las fuentes equivalentes requieren profundidad, amortiguación y controles de memoria; son una representación interpolante, no un cuerpo geológico único. La micronivelación no debe eliminar geología paralela al vuelo.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

### Propiedades aparentes de capa

Usa una grilla completa con filas que aumentan al norte y columnas al este. La capa continua periódica tiene profundidad del techo y espesor prescritos; el contraste de densidad es kg/m³ y la susceptibilidad es SI. Intensidad magnética, inclinación positiva hacia abajo y declinación desde el norte de grilla son explícitas. La inversa elimina la media observada y añade el fondo elegido. La regularización usa unidades de datos/propiedad y los límites de ganancia sus recíprocas. Revisa residuales y recuperación espectral; las direcciones ausentes y frecuencias suprimidas no son geología recuperada. No es el modelo propietario de prismas infinitos ni susceptibilidad cgs. No elimina IGRF, corrige terreno ni certifica datos automáticamente.

m_hat(k) = conj(K) d(k) / (|K|² + lambda²)

Parámetros / cantidades: kind, top_depth_m, thickness_m, background, regularization_response, max_inverse_gain, minimum_wavelength_m

Fuentes de contexto:

- [Harmonica prism gravity: units and coordinate conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)
- [Harmonica prism magnetic field: conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_magnetic.html)

### Fase, textura y caminos de rasgos

Los atributos básicos log-Gabor/Riesz usan longitudes de onda, ancho de banda y ruido explícitos; el alineamiento no está ponderado y no equivale a congruencia de fase completa ni CET. La entropía cuantizada depende de ventana, intervalo e histograma. La entropía axial también depende del origen de intervalos y soporte válido. Los caminos requieren máscara booleana explícita, espaciado proyectado en metros y centro del primer píxel. Ramificaciones y ciclos conservan geometría de píxel sin suavizado ni unión de huecos. Son rasgos matemáticos, no fallas ni litologías interpretadas.

H = -sum(p log2 p)

Parámetros / cantidades: wavelengths_m, sigma_on_f, noise_threshold, value_range, bin_origin_degrees, feature_mask, origin_xy

Fuentes de contexto:

- [Monogenic phase attributes](https://peterkovesi.github.io/ImagePhaseCongruency.jl/stable/functions/)
- [scikit-image morphology](https://scikit-image.org/docs/stable/api/skimage.morphology.html)

### Métodos de interpolación y soporte

IDW depende de potencia de distancia y vecinos; el vecino más cercano no añade suavidad. Los splines globales de placa delgada y aproximaciones TPS locales difieren en soporte y costo. El solver multinivel experimental de mínima curvatura es otro método, no una promesa de equivalencia propietaria. La interpolación sinc requiere muestreo y soporte defendibles. Evalúa bloques espaciales reservados y documenta extrapolación distante. Una celda menor mejora visualización, no resolución de adquisición.

IDW: z(x) = sum(w_i z_i)/sum(w_i); w_i = distance_i^(-p)

Parámetros / cantidades: METHOD, CELL_SIZE, NEIGHBORS, SEARCH_RADIUS, POWER, SMOOTHING

Fuentes de contexto:

- [Verde spatial cross-validation](https://www.fatiando.org/verde/latest/tutorials/model_selection.html)

### Correcciones de adquisición y tiempos

El lag con signo cambia la ubicación de una observación en tiempo/trayectoria; documenta signo y estimación con evidencia repetible. Interpola estación base solo dentro del soporte temporal aceptado. Los coeficientes de rumbo modelan respuesta de adquisición y no deben absorber diferencias geológicas. La gravedad móvil requiere época de deriva consistente, marea explícita y signo Eötvös declarado. Conserva canales corregidos y originales. Remuestreo, interpolación de huecos y rotaciones son pasos separados con registro.

Parámetros / cantidades: LAG, BASE_TIME, BASE_VALUE, HEADING, DRIFT, TIDE, EOTVOS_MODE

Fuentes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### Nivelación con amarres y micronivelación

Los cruces restringen diferencias entre líneas de vuelo y amarre. Revisa conectividad, distancia de intersección y residuos antes de ajustar correcciones constantes o polinómicas. No trates una red sin anclaje como si tuviera datum absoluto. La micronivelación direccional trata corrugación residual después de correcciones primarias y cruces. Compara la corrección retirada con amplitud geológica; examina estructuras paralelas y transversales al vuelo. Una imagen más limpia no demuestra por sí sola mejores mediciones.

Parámetros / cantidades: LINE_ID, LINE_TYPE, TIE_VALUES, POLYNOMIAL_DEGREE, AZIMUTH

Fuentes de contexto:

- [Minty (1991): Simple Micro-Levelling for Aeromagnetic Data](https://doi.org/10.1071/EG991591)

Contexto del capítulo:

- [Verde spatial cross-validation](https://www.fatiando.org/verde/latest/tutorials/model_selection.html)
- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)
- [Monogenic phase attributes](https://peterkovesi.github.io/ImagePhaseCongruency.jl/stable/functions/)
- [scikit-image morphology](https://scikit-image.org/docs/stable/api/skimage.morphology.html)

## Filtros FFT y selección de parámetros

Las longitudes de onda y alturas de continuación usan unidades del SRC. Compara cortes relacionados con el muestreo y la escala objetivo. El orden Butterworth controla la transición; un orden mayor no es necesariamente mejor. Quitar media/plano, añadir relleno reflejado y suavizar bordes modifica el comportamiento marginal; regístralo y compara también el interior. La continuación ascendente atenúa ondas cortas. La descendente amplifica ruido y requiere estabilización y límites de ganancia. Restaura la tendencia solo cuando corresponda físicamente. La mediana circular espacial trata picos aislados; es no lineal y no es una transferencia Fourier. La base de datos no es un dominio numérico.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

H_up(k, h) = exp(-|k| h); k in rad / length; h > 0

### Tendencia, relleno y suavizado marginal

Quitar media o plano cambia el contenido de número de onda cero/bajo. El relleno reflejado reduce saltos pero crea una extensión artificial; el suavizado pondera esa extensión antes de FFT. La inversa recorta a la geometría original y recupera su máscara. Restaurar tendencia puede corresponder a suavizados, pero generalmente no a una derivada. Compara estadísticas de borde e interior por separado y conserva los parámetros de acondicionamiento en la receta.

k = 2 pi / wavelength; Nyquist per axis = pi / spacing

Parámetros / cantidades: FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND

Fuentes de contexto:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

### Bandas Butterworth, ideales y coseno

El kernel Butterworth espacial se define directamente en número de onda radial; no lo confundas con el diseño digital temporal. Los cortes de longitud de onda larga y corta se corresponden inversamente con número de onda. El pasabanda multiplica respuestas baja/alta; el rechazo complementa la banda. Los bordes ideales generan oscilaciones; transiciones suaves intercambian selectividad por menor oscilación. Compara corte y orden, no solo colores. El gaussiano tiene otra transferencia y no debe nombrarse como el mismo filtro.

B_LP = [1+(k/kc)^(2n)]^(-1/2); B_HP = [1+(kc/k)^(2n)]^(-1/2)

Parámetros / cantidades: WAVELENGTH, LONG_WAVELENGTH, SHORT_WAVELENGTH, ORDER

Fuentes de contexto:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

### Continuación e integración de derivadas

La continuación ascendente es un paso bajo de campo potencial. La descendente estabilizada combina ganancia exponencial, límite y suavizado; limitar ganancia cambia el operador ideal. Integrar una derivada horizontal necesita una política en su eje de número de onda cero; una constante no se recupera solo con derivadas. Documenta piso o estabilización y revisa amplificación espectral. La pseudogravedad depende de magnetización y escala; no es una observación gravimétrica absoluta.

H_up = exp(-|k|h); H_down = min(exp(|k|h),Gmax) B_LP; Ix = 1/(i kx)

Parámetros / cantidades: HEIGHT, MAX_GAIN, LOWPASS_WAVELENGTH, ORDER

Fuentes de contexto:

- [Harmonica upward continuation](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.upward_continuation.html)

### Mediana circular, suavizado y ganancia

La mediana circular usa una vecindad por distancia en píxeles; su radio no es una longitud de onda física. Conserva ausencias originales y revisa cambios en blancos aislados. El suavizado de nueve puntos aplica repetidamente un kernel local normalizado; las iteraciones cambian el suavizado efectivo. El control automático de ganancia reescala amplitudes locales y no conserva una escala magnética o gravimétrica calibrada. Mantén una rama cuantitativa antes de realces. Estos productos no lineales/adaptativos no equivalen a una única transferencia FFT.

Parámetros / cantidades: RADIUS, PASSES, GAIN_CAP, RMS_FLOOR

Fuentes de contexto:

- [SciPy multidimensional image processing](https://docs.scipy.org/doc/scipy/reference/ndimage.html)
- [scikit-image morphology](https://scikit-image.org/docs/stable/api/skimage.morphology.html)

Contexto del capítulo:

- [Harmonica upward continuation](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.upward_continuation.html)
- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

## Derivadas magnéticas y dirección del campo

DX y DY dependen de la orientación de coordenadas; DZ depende del signo vertical. Las derivadas amplifican ruido de onda corta. Compara gradiente horizontal, amplitud de gradiente total y tilt con la anomalía original. RTP y RTE requieren dirección del campo y una dirección de magnetización supuesta. IGRF necesita fecha y altitud; no sustituyas silenciosamente altitud del sensor por elevación del terreno. RTP a baja inclinación puede ser inestable aunque el mapa parezca suave. La remanencia puede invalidar una interpretación solo inducida. Un máximo no demuestra falla, profundidad ni litología; contrasta observaciones independientes.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

HGM = sqrt(DX² + DY²); TGA = sqrt(DX² + DY² + DZ²); tilt = atan2(DZ, HGM)

### Componentes e integración de gradientes

La conversión de componentes supone un semiespacio armónico sin fuentes. Campo total significa proyección de anomalía pequeña, no norma vectorial exacta. Componentes de entrada y salida y media de salida son explícitas. La reconstrucción usa derivadas este, norte y hacia arriba en nT/m, con pesos relativos positivos. La media de referencia es prescrita. Revisa ganancias, amortiguación, direcciones no resueltas y ejes de Nyquist excluidos en grillas pares. Una tabla radial usa números de onda angulares en rad/m y ganancia DC explícita; conserva su ganancia final después del último nodo.

dT/dz_up = -k T; T(0) = prescribed mean

Parámetros / cantidades: input_component, output_component, output_mean_nt, gradient_up, reference_mean_nt, wavenumbers_rad_per_m

Fuentes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### Ajuste de dipolos compactos

Las posiciones son ENU en metros y los momentos A·m². Cantidad de fuentes, semillas, errores independientes, límites y distancia mínima al sensor son prescritos. Ajusta componentes vectoriales o proyección lineal de campo total. Un optimizador convergente con jacobiano de rango deficiente no es un ajuste identificable exitoso; no se entrega covarianza local en ese caso. Revisa límites activos y residuales. La aproximación no identifica forma, clase UXO ni contenido explosivo.

B = mu0/(4 pi) [3 r (m·r)/r^5 - m/r^3]

Parámetros / cantidades: observation_xyz, moments_a_m2, minimum_distance_m, rank_tolerance

Fuentes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)
- [SimPEG](https://docs.simpeg.xyz/latest/)

### Derivadas espaciales y Fourier

DX y DY usan espaciado de coordenadas, no índices de píxel. La primera derivada hacia arriba cambia de signo si se adopta vertical positiva hacia abajo. La diferenciación FFT supone una superficie horizontal regular y extensión periódica después del preprocesamiento. Compara por separado primera y segunda derivada: la segunda amplifica más los números de onda altos. Verifica unidades de campo por longitud o longitud al cuadrado. Revisa independientemente bordes enmascarados y huecos interpolados.

Dx: i kx; Dy: i ky; Dz_up: -|k|; Dzz: |k|²

Parámetros / cantidades: BAND, ORDER, spacing, padding_cells

Fuentes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### Atributos de gradiente y angulares

El gradiente horizontal y la amplitud de gradiente total tienen unidades físicas de derivada; tilt y atributos normalizados son ángulos o razones adimensionales. Una derivada horizontal direccional debe declarar referencia del azimut y convergencia de coordenadas. Normalizar puede realzar visualmente áreas débiles y ruidosas; examina una máscara de amplitud junto a los atributos angulares. Los picos se desplazan con geometría e interferencia de fuentes. Un umbral angular no clasifica fallas sin evidencia independiente.

HGM = sqrt(Tx²+Ty²); TGA = sqrt(Tx²+Ty²+Tz²); tilt = atan2(Tz,HGM)

Parámetros / cantidades: AZIMUTH, gradient_x, gradient_y, gradient_z

Fuentes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### RTP, RTE y dirección IGRF

Distingue dirección del campo inductor y magnetización de fuente. Fecha, altitud y posición geográfica determinan una dirección IGRF, no la componente remanente. Examina estabilización de ganancia a baja inclinación y compara direcciones próximas. La transformación no corrige nivelación ni una sustracción incorrecta del campo principal. Conserva la anomalía original y registra direcciones manuales o calculadas. Las transformaciones generales y la pseudogravedad dependen del modelo de magnetización supuesto.

I > 0: downward; D: clockwise from geographic North

Parámetros / cantidades: INCLINATION, DECLINATION, MAX_GAIN, SURVEY_YEAR, SURVEY_MONTH, SURVEY_DAY

Fuentes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

Contexto del capítulo:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

## Correcciones gravimétricas e isostasia

Distingue gravedad observada, perturbación y anomalías. Registra latitud, referencia de altura, época de deriva, mareas, corrección por movimiento y densidad de reducción. Verifica el signo antes de sumar cada corrección. Terreno, placa Bouguer y curvatura esférica no son intercambiables. No corrijas otra vez anomalías Bouguer completas publicadas como si fueran observaciones crudas. La isostasia Airy supone compensación local; la flexura admite soporte regional y requiere parámetros elásticos y bordes. Acompaña la interpretación con sensibilidad a densidad y profundidad de referencia. El residual depende del modelo; no mide automáticamente un exceso de masa cortical.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

CBA = SBA + terrain - Bullard B

### Atracción adaptativa de un DEM finito

El modelo usa estaciones ENU explícitas, un DEM regular completo y un plano de referencia prescrito. La roca sobre ese plano tiene densidad de corteza; debajo se usa contraste agua menos corteza. Las celdas cercanas conservan prismas exactos. Los grupos lejanos conservan masa con signo y centroide; se refinan las mayores cotas hasta que su suma cumple la tolerancia en mGal. La cota excluye errores numéricos, de terreno, densidad, datum vertical, curvatura terrestre y terreno externo ausente. La salida es atracción, no corrección completa de terreno, Bouguer o mareas. Una tolerancia estricta puede exigir suma exacta densa; los presupuestos no limitan RAM ni duración.

E_group <= 12 G 10^5 J / (d - R)^4; d > R

Parámetros / cantidades: observation_xyz, reference_elevation_m, absolute_tolerance_mgal, leaf_cells, max_prism_evaluations

Fuentes de contexto:

- [Barnes and Hut: hierarchical force calculation](https://doi.org/10.1038/324446a0)
- [Harmonica prism gravity: units and coordinate conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)

### Gravedad normal y reducción de altura

El algoritmo GRS80 local evalúa Somigliana en la latitud de la superficie elipsoidal de referencia. Su sustracción de latitud no equivale a evaluar el campo normal a la altura del sensor. El término lineal configurable de aire libre es una aproximación separada. Registra la superficie de referencia de cada término antes de llamar perturbación o anomalía al resultado. Una elevación geométrica no debe interpretarse silenciosamente como altura ortométrica. No combines convenciones incompatibles de productos publicados.

gamma(phi) = gamma_e (1+k sin²(phi))/sqrt(1-e² sin²(phi)); FAA = g_obs-gamma(phi)+a h

Parámetros / cantidades: ELEVATION, FREE_AIR_GRADIENT, INPUT, BAND

Fuentes de contexto:

- [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html)

### Placa Bouguer, terreno y curvatura

La placa infinita retira una masa idealizada entre datum y estación. Los prismas de terreno representan relieve respecto a la referencia; Bullard B trata curvatura esférica bajo la convención terrestre implementada. Son correcciones con signo distintas, no filtros intercambiables. La densidad afecta cada término de masa y debe ser consistente en la cadena. Examina cobertura DEM, separación del receptor, singularidades y sensibilidad de discretización. Una corrección con relieve incompleto no produce automáticamente Bouguer completa.

slab = 2 pi G rho h; SBA = FAA-slab; CBA = SBA+terrain-BullardB

Parámetros / cantidades: CRUST_DENSITY, WATER_DENSITY, CLEARANCE, DEM, MAX_CELLS

Fuentes de contexto:

- [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html)

### Compensación Airy y soporte elástico

La profundidad Airy usa contraste de densidad corteza/manto y Moho de referencia; produce una interfaz compensadora supuesta, no un Moho sísmico observado. Calcula su efecto gravimétrico antes del residual isostático. El kernel de placa elástica responde a presión prescrita con bordes periódicos. Declara carga media, tamaño de dominio y constantes elásticas. Un barrido de espesores ajusta desplazamientos bajo supuestos fijos; no infiere automáticamente incertidumbre geológica ni gravedad.

D = E Te³/[12(1-nu²)]; w(k) = q(k)/(D |k|⁴ + delta_rho g)

Parámetros / cantidades: REFERENCE_MOHO, CRUST_DENSITY, MANTLE_DENSITY, elastic_thickness_m, load_pa

Fuentes de contexto:

- [GMT grdflexure: elastic and rheological plate models](https://docs.generic-mapping-tools.org/6.5/supplements/potential/grdflexure.html)
- [Harmonica prism gravity: units and coordinate conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)

Contexto del capítulo:

- [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html)
- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)
- [Barnes and Hut: hierarchical force calculation](https://doi.org/10.1038/324446a0)

## Radiometría y calibración del detector

Separa conteos, tasas y K/eU/eTh calibrados. Corrige observaciones crudas con coeficientes del levantamiento para tiempo muerto, fondo, stripping, altura y sensibilidad; no reutilices coeficientes nominales sin revisión. Las razones requieren protección del denominador y máscaras compatibles. Examina radón, humedad y altura. El uranio equivalente supone condiciones de la cadena de decaimiento; no es química directa de uranio. El ternario es visualización, no mediciones independientes. Conserva incertidumbre y residuos de calibración.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

### Conteos crudos frente a productos calibrados

Sigue la cadena específica del detector y conserva canales de conteo originales. Tiempo muerto no paralizable, sustracción de fondo, normalización de altura y stripping actúan sobre cantidades distintas. Una grilla de concentraciones calibradas no debe recibir de nuevo la cadena cruda. Examina valores corregidos negativos sin recortarlos silenciosamente. Respuesta de altura y sensibilidad requieren evidencia de calibración/adquisición. Uranio y torio equivalentes dependen de supuestos de series de decaimiento; razones y dosis requieren unidades y máscaras compatibles.

Parámetros / cantidades: DEAD_TIME, BACKGROUND, HEIGHT, ATTENUATION, SENSITIVITY, RESPONSE_MATRIX

Fuentes de contexto:

- [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf)

### Calibración espectral y covarianza

Usa varios picos de calibración para examinar no linealidad energética. Reagrupar distribuye conteos fraccionarios y correlaciona intervalos; las varianzas diagonales no bastan. El solapamiento de ventanas también produce covarianza. NASVD y MNF requieren supuestos explícitos de rango/ruido y pueden producir reconstrucciones negativas. La incertidumbre de calibración es compartida entre puntos aunque solo se devuelva covarianza marginal. Valida con registros independientes y conserva nombres, unidades y orden de la matriz de respuesta.

E = offset+gain channel; Cov(Ax) = A Cov(x) Aᵀ

Parámetros / cantidades: channel_peaks, energy_peaks, input_edges, output_edges, rank, rate_covariance

Fuentes de contexto:

- [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf)

Contexto del capítulo:

- [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf)

## Euler, Werner, SPI y profundidad espectral

Las profundidades dependen del tipo de fuente supuesto, muestreo y fondo. En Euler varía índice estructural, ventana, derivadas y límites de aceptación. Descarta ventanas mal condicionadas y examina agrupaciones, no todos los candidatos como fuentes. Werner/SPI de perfil no equivalen a una inversión 3D arbitraria. Las pendientes espectrales necesitan un intervalo de frecuencias declarado y soporte estadístico; fuentes mezcladas y bordes sesgan la profundidad. Compara casos sintéticos, otras ventanas y geología. Estas técnicas no determinan de forma única el límite de un cuerpo ni reservas.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

(x-x0) Tx + (y-y0) Ty + (z-z0) Tz = N (B-T)

### Aceptación Euler y geometría de perfiles

Usa derivadas y coordenadas en unidades consistentes y z positiva hacia arriba. Un índice estructural cero no identifica un fondo arbitrario; la implementación estima el desplazamiento de contacto identificable. Condición, residuo y error de profundidad son criterios de aceptación independientes. Euler de perfil supone fuente localmente bidimensional y no resuelve ubicación a lo largo del rumbo. Conserva conteos de rechazos y compara índices, alturas y tamaños de ventana. Revisa explícitamente soluciones externas al dominio observado.

(x-x0)Tx+(y-y0)Ty+(z-z0)Tz = N(B-T)

Parámetros / cantidades: structural_index, window_size, stride, max_condition, max_relative_depth_error, depth_bounds

Fuentes de contexto:

- [Harmonica Euler deconvolution](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.EulerDeconvolution.html)

### Werner, SPI y ajuste espectral

Werner supone lámina delgada, polinomio de interferencia declarado y observaciones a nivel. SPI usa picos de número de onda local; las muestras fuera de picos no son profundidades independientes. Sus factores geométricos difieren entre contactos, láminas y cilindros horizontales. La profundidad espectral usa intervalo y exponente geométrico elegidos; ajustar una recta a todo ignora poblaciones mezcladas. Compara picos, residuos y sensibilidad del intervalo. Las fachadas por perfiles no convierten estos supuestos en reconstrucción tridimensional general.

K = abs((Tx Txz-Tz Txx)/(Tx²+Tz²)); SPI depth = (index+1)/K at peaks

Parámetros / cantidades: background_degree, source_model, peak_distance, fit_range, geometry_exponent

Fuentes de contexto:

- [Ku and Sharp (1983): Werner deconvolution](https://doi.org/10.1190/1.1441505)
- [Thurston and Smith (1997): SPI method](https://doi.org/10.1190/1.1444190)
- [Spector and Grant (1970): statistical aeromagnetic models](https://doi.org/10.1190/1.1440092)

Contexto del capítulo:

- [Harmonica Euler deconvolution](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.EulerDeconvolution.html)

## Inversión, residuos y sensibilidad

Elige explícitamente propiedad física, operador directo, malla, incertidumbres, límites y regularización. Separa posiciones del sensor y superficie topográfica. Repite variando celda, profundidad, extensión, modelo inicial/de referencia y peso de regularización. Inspecciona observados, predichos y residuos por línea y ubicación, no solo un desajuste escalar. Convergencia no elimina no unicidad. El gradiente cruzado favorece similitud estructural, no una relación fija densidad–susceptibilidad. Motores opcionales y versiones deben quedar en la trazabilidad. Un solver que alcanza el máximo de iteraciones no debe etiquetarse como solución convergente.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

phi(m) = phi_d(m) + beta phi_m(m); r_i = (d_pred_i - d_obs_i) / sigma_i

### Densidad, susceptibilidad y MVI

La inversión de densidad estima contraste respecto a reducción/referencia. La inversión magnética escalar supone dirección de magnetización y parametrización de susceptibilidad; la vectorial admite componentes direccionales pero aumenta ambigüedad. La elevación del receptor no es por defecto la topografía de celdas activas. Extensión, profundidad y límites físicos afectan estructura recuperada. Revisa convergencia separadamente de plausibilidad geológica y compara parametrizaciones. La geometría VTK es una malla numérica, no un límite geológico cartografiado independientemente.

Parámetros / cantidades: CELL_SIZE, MODEL_DEPTH, MESH_TYPE, TOPOGRAPHY, LOWER_BOUND, UPPER_BOUND

Fuentes de contexto:

- [SimPEG](https://docs.simpeg.xyz/latest/)
- [SimPEG L2 data misfit](https://docs.simpeg.xyz/latest/content/api/generated/simpeg.data_misfit.L2DataMisfit.html)

### Inversión magnética vectorial esférica

Un arranque cartesiano suave se refina en amplitud y ángulos periódicos. Las normas de amplitud y de gradientes angulares se eligen por separado; las normas dispersas requieren IRLS. Los límites de magnitud son distintos de los límites de componentes cartesianas. La elevación interna es positiva hacia arriba y el azimut parte del Este; las salidas conservan susceptibilidad efectiva cartesiana ENU. La dirección es indefinida cuando la amplitud es cero. Compara ajuste ponderado por ruido, precisión interna y recuperación del modelo por separado. El soporte geométrico y las referencias son supuestos explícitos, no información recuperada automáticamente de los datos magnéticos. Ángulos coherentes no resuelven toda ambigüedad de profundidad o volumen.

m = a[cos(theta)cos(phi), cos(theta)sin(phi), sin(theta)]

Parámetros / cantidades: mvi_parameterization, mvi_cartesian_iterations, mvi_amplitude_max, mvi_angle_norms, regularization_norms, irls_iterations

Fuentes de contexto:

- [Fournier, Heagy and Oldenburg (2020), Sparse magnetic vector inversion in spherical coordinates](https://doi.org/10.1190/geo2019-0244.1)
- [SimPEG](https://docs.simpeg.xyz/latest/)

### Incertidumbre, IRLS y estructura conjunta

La incertidumbre controla pesos y debe reflejar errores de medición/modelo, no un ajuste objetivo arbitrario. El peso regularizador balancea ajuste y supuestos. Normas dispersas e IRLS cambian el problema; una covarianza lineal gaussiana fija no se aplica automáticamente después. El gradiente cruzado favorece gradientes alineados sin imponer razón densidad/susceptibilidad. Prueba pesos de acoplamiento, distribuciones residuales y referencias. Mantén explícita la falta de convergencia; un modelo atractivo no reemplaza experimentos de sensibilidad.

phi = phi_d+beta phi_m; cross-gradient = grad(m1) × grad(m2)

Parámetros / cantidades: UNCERTAINTY, LP_NORM, IRLS_ITERATIONS, beta, regularization, reference

Fuentes de contexto:

- [SimPEG](https://docs.simpeg.xyz/latest/)

Contexto del capítulo:

- [SimPEG L2 data misfit](https://docs.simpeg.xyz/latest/content/api/generated/simpeg.data_misfit.L2DataMisfit.html)
- [SimPEG](https://docs.simpeg.xyz/latest/)

## Resistividad DC, IP y potencial espontáneo

La resistividad DC necesita geometría de electrodos, polaridad de corriente, diferencia de potencial y factor geométrico compatible. La resistividad aparente no es una propiedad directa del vóxel. Examina reciprocidad, contactos y topografía. IP y conductividad compleja necesitan convenciones de frecuencia/tiempo y signo; las unidades de cargabilidad no son intercambiables. El potencial espontáneo requiere electrodo de referencia y signo; separa el ajuste de fuentes y bordes de la interpretación. Los modelos estratificados suponen invariancia lateral. Modelado e inversión PDE requieren sensibilidad de malla y bordes. Estas entradas experimentales no son un sistema instrumental completo.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

rho_a = K delta_V / I

### Geometría ABMN, IP y polaridad

ABMN guarda índices, no distancias; B/N remoto usa el centinela documentado. El factor de semiespacio requiere plano de electrodos compatible. Conserva signos de voltaje/corriente y marca resistividad aparente negativa, sin valor absoluto. El control recíproco distingue cuadripolos invertidos y repeticiones de igual orientación. IP integrada es promedio normalizado de ventana, no integral temporal sin normalizar. Cole–Cole de resistividad requiere su convención fasorial; los parámetros de conductividad no se intercambian renombrándolos. La inversión temporal también admite historiales finitos prescritos de corriente con signo, suponiendo polarización nula antes del primer evento. Indica cada cambio y elige normalización DC o por el primario previo al apagado final; datos y errores son V/V. El modelado de apilados exige seleccionar intervalos sin corriente, pesos y una convención explícita de media de cocientes o cociente de sumas. Ajusta datos V/V ya apilados sin inferir procesamiento instrumental ni reducción de ruido. Prehistoria desconocida, filtros del receptor e inducción requieren modelado separado.

K_half = 2 pi/(1/AM-1/BM-1/AN+1/BN); rho_a = K V/I

Parámetros / cantidades: electrodes, abmn, space, current_a, voltage_v, gate_s

Fuentes de contexto:

- [SimPEG DC resistivity](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.static.resistivity.html)
- [Spectral induced polarization: frequency domain versus time domain laboratory data, Appendix C](https://doi.org/10.1093/gji/ggab071)
- [Understanding the Fate of H2S Injected in Basalts by Means of Time-Domain Induced Polarization Geophysical Logging](https://doi.org/10.1029/2023JB028316)

### Mallas PDE y fuentes de potencial espontáneo

Usa geometría de malla, regiones activas, fuentes/receptores y bordes explícitos. En SP de fuentes prescritas, la implementación usa caras exteriores aislantes y plantillas individualmente neutras. No equivale a semiespacio infinito ni interpretación electrocinética automática. El ajuste de amplitudes mantiene fijas conductividad y geometría. Revisa distancia a bordes, refinamiento y electrodo de referencia. La covarianza condicional excluye incertidumbre de conductividad, geometría de fuentes y acoplamiento hidráulico.

Parámetros / cantidades: mesh_widths, mesh_origin, conductivity_s_m, source_templates_a_m3, reference_m

Fuentes de contexto:

- [SimPEG DC resistivity](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.static.resistivity.html)

Contexto del capítulo:

- [SimPEG DC resistivity](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.static.resistivity.html)

## FDEM, TEM y magnetotelúrica

Registra geometría fuente/receptor, frecuencia o forma de onda, componente, orientación y normalización. Importan los signos en fase/cuadratura y ppm frente a campo absoluto en FDEM. Las ventanas TEM son integrales temporales finitas; usa la forma de onda registrada y el tiempo cero correcto. Excluye explícitamente ventanas contaminadas o negativas. La impedancia MT requiere unidades eléctricas/magnéticas y convención Fourier antes de resistividad aparente y fase. Un modelo 1D no representa estructura lateral arbitraria. Repite ajustes de conductividad con otros modelos iniciales y límites; un ajuste excelente no demuestra resolución en profundidad ni unicidad geológica.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

rho_a = |Z_EH|² / (mu0 omega); omega = 2 pi f

### EM estratificado y tridimensional

El modelo estratificado usa espesores de capas finitas y un semiespacio final. Momento, orientación y separación de receptor son explícitos. Campo secundario en tesla no equivale a ppm sin normalización primaria justificada. Ajustar zonas 3D es un ajuste local acotado con presupuesto de modelados directos, no inversión ilimitada de vóxeles. Prueba extensión y conductividades iniciales; la memoria LU puede exceder estimaciones simples. Los errores real/imaginario correlacionados requieren el orden de covarianza declarado.

Parámetros / cantidades: frequency_hz, thicknesses_m, source_m, receiver_m, moment_a_m2, data_covariance_t2

Fuentes de contexto:

- [SimPEG electromagnetic methods](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.html)

### Ventanas TEM e impedancia MT

Apagado ideal, rampas finitas y formas de onda registradas son historias de fuente distintas. Integra ventanas TEM finitas, no solo sus centros; prueba orden de cuadratura. La impedancia MT debe distinguir ohmios E/H y unidades E/B. Conserva signos xy/yx y no pliegues fase silenciosamente. El tensor de fase elimina una distorsión galvánica ideal real por izquierda, pero no recupera amplitud de resistividad ni desplazamiento estático. Los ajustes estratificados mantienen espesores fijos salvo parametrización explícita distinta.

rho_a = |Z_EH|²/(mu0 omega); Phi = Re(Z)^(-1) Im(Z)

Parámetros / cantidades: gates_s, waveform_times_s, quadrature_order, impedance_ohm, thicknesses_m

Fuentes de contexto:

- [SimPEG electromagnetic methods](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.html)

Contexto del capítulo:

- [SimPEG electromagnetic methods](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.html)

## Georradar, formas de onda y sísmica pasiva

Confirma eje de muestras, intervalo, tiempo cero y espaciado de trazas antes de filtrar. Dewow resta una media temporal local; quitar fondo compartido puede suprimir reflectores horizontales reales. El pasabanda debe respetar Nyquist. La ganancia cambia amplitudes y no es inversión física. La profundidad de georradar necesita velocidad defendible; migración requiere geometría y supuestos correctos. En espectros pasivos revisa ventanas, transitorios, orientación y suavizado. Un pico H/V no equivale automáticamente a un espesor único. Conserva una rama de amplitudes originales y compara trazas, no solo imágenes realzadas.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

f_Nyquist = 1 / (2 dt); depth_GPR = velocity time_two_way / 2

### Acondicionamiento de trazas, detecciones y profundidad

Las matrices usan orden traza por tiempo. Dewow necesita ventana impar que quepa en el registro; quitar fondo actúa entre trazas, no en tiempo. Butterworth temporal debe quedar bajo Nyquist y necesita muestras suficientes para bordes. Tiempo cero, ganancia y migración cambian información distinta. NMO estira señales; enmascara estiramientos excesivos y documenta cobertura. Las detecciones STA/LTA y picos H/V son indicadores a revisar, no clasificaciones automáticas ni profundidades geológicas únicas.

0 < f_low < f_high < 1/(2 dt); depth = v t_two_way / 2

Parámetros / cantidades: traces, dt_s, window_samples, low_hz, high_hz, maximum_stretch

Fuentes de contexto:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

Contexto del capítulo:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

## Registros de pozo y transformaciones petrofísicas

Revisa mnemónicos LAS, unidades, valores nulos, sentido de profundidad y metadatos antes de elegir curvas. Separa profundidad medida y vertical verdadera. Remuestreo y desplazamientos deben preservar intervalos nulos y documentarse por curva. Las transformaciones petrofísicas requieren supuestos de formación, fluidos y calibración. Las ecuaciones tipo Archie no corrigen universalmente arcillas. No infieras unidades de porosidad solo por magnitudes. Compara curvas transformadas con originales y laboratorio independiente. Exportar LAS actualizado debe preservar curvas no modificadas y metadatos; una exportación correcta no valida el modelo geológico.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

### Unidades LAS, trayectoria y remuestreo

Las muestras LAS conservan unidades originales; la salida de profundidad solo convierte unidades metro/pie explícitas o una sustitución registrada. Actualizar curvas no autoriza cambiar la columna de profundidad. Reconstruir trayectoria requiere collar, profundidades medidas y convenciones de orientación. No confundas profundidad medida y vertical verdadera. Conserva nulos e inversiones para control antes de remuestrear. Los desplazamientos deben usar intervalos de correlación defendibles, no solo maximizar coincidencia entre formaciones distintas.

international foot = 0.3048 m

Parámetros / cantidades: text, depth_unit_override, curve_values, collar_enu_m, measured_depth_m

Fuentes de contexto:

- [lasio documentation](https://lasio.readthedocs.io/en/latest/)
- [Taylor (1972): well surveying calculations](https://doi.org/10.2118/3362-PA)

Contexto del capítulo:

- [lasio documentation](https://lasio.readthedocs.io/en/latest/)

## Validación, trazabilidad y conclusiones prudentes

Separa pruebas unitarias, comparación numérica, pruebas de GUI y validación de campo. Aprobar un caso sintético no establece equivalencia comercial. Archiva receta, versiones o hashes de entradas, unidades, parámetros, versiones de librerías y estadísticas residuales. El hash de un módulo no cubre dependencias transitivas. Distingue tareas completadas, fallidas, canceladas y sin converger. Los límites de salida no limitan RAM ni tiempo del solver. Cancelar puede esperar un punto de control. Revisa sensibilidad en rangos defendibles y documenta diferencias pendientes. Mantén levantamientos privados y adquisición fuera de documentación y paquetes públicos.

Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.

Contexto del capítulo:

- [SimPEG](https://docs.simpeg.xyz/latest/)

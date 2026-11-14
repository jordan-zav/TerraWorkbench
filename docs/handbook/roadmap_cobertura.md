# Mapa de cobertura y brechas

Investigación original del 22 de octubre de 2026; estado revisado el 26 de octubre de 2026. Ver la [expansión multidisciplinaria](../research/geophysics_expansion.md) y su [catálogo estructurado](../research/geophysics_backlog.json). Los identificadores de propuestas no certifican que todos sus requisitos estén implementados.

Este mapa ordena la expansión científica. No promete fechas y no convierte una
idea en algoritmo existente. La cobertura implementada detallada está en la
[referencia técnica](geofisica_potencial_referencia.md).

## Base actual consolidada

- Importación abierta de grillas y puntos, recuperación de metadatos y puente
  opcional para bases Geosoft.
- QC de vuelo por intervalo, espaciamiento, velocidad, rumbo verdadero, altura y
  tasa del canal; lag automático con curva de correlación; QC de estación base;
  espaciamiento entre líneas/líneas faltantes; drape contra DEM; comparación de
  líneas repetidas y remoción IGRF-14 por punto.
- Gridding, crossovers, nivelación traverse/tie y microleveling direccional.
- Realces MAG/GRAV espaciales, FFT y mixtos con dominio declarado.
- RTP, RTE, transformación direccional e IGRF-14.
- Filtros espectrales configurables y Filter Stack reproducible.
- Cadena gravimétrica desde GRS80 hasta Bouguer completa, terreno e isostasia Airy.
- Inversión de densidad, susceptibilidad, MVI y conjunta GRAV–MAG.
- Inversión escalar con regularización Lp, IRLS y modelo de referencia configurable.
- Conversión explícita entre norte verdadero y norte de grilla, CRS físicos en metros
  e historial de convergencia de inversión.
- Radiometría K–eU–eTh: razones, ternario, dosis, parámetro F, QC y correcciones
  crudas parametrizadas de tiempo muerto, fondos, altura, sensibilidad y stripping.

## Radiometría — estado y brechas

El procesamiento sobre grillas calibradas está implementado; esto no acredita
validación de campo para cada flujo. Las herramientas
de conteos crudos no inventan coeficientes: exigen los valores del informe de
calibración del levantamiento. Core incluye ajuste lineal de energía desde picos
identificados, remuestreo energético, NASVD/MNF, integración de ventanas y
propagación de covarianza mediante operadores fijos. También incluye calibración
de respuesta y concentración con incertidumbre de primer orden. Esto no equivale
a identificación automática de picos, estabilización completa de adquisición ni
a covarianza entre todos los registros que comparten calibración. La estimación
temporal de radón ascendente y la validación instrumental de pads/strips requieren
canales, geometría y estándares reales. No pueden reconstruirse desde una grilla
K/eU/eTh terminada.

## Prioridad A — cerrar el flujo 2D de producción

El alcance inmediato de sustitución del procesamiento básico está definido en
[Procesamiento básico](../guides/basic_processing_migration.md): mínima
curvatura, controles de gridding, suavizado, filtros y exportación. TPS global/local,
suavizado binomial de nueve puntos y AGC RMS tienen una primera implementación;
la equivalencia con referencias históricas sigue pendiente. Excluye pseudogradientes, crosshatch
y experimentos arqueológicos.

| Familia | Brecha candidata | Referencias iniciales | Validación mínima |
| --- | --- | --- | --- |
| Nivelación MAG | implementada: corrección base, lag firmado y estimación automática, heading armónico, despike Hampel, IGRF por punto, QC de estación base/vuelo/repetición/espaciamiento/drape y nivelación robusta constante, lineal o cuadrática; falta ajuste conjunto de líneas sin red tie defendible | PyGMI, literatura de levantamientos | líneas sintéticas + survey con base conocida |
| Nivelación GRAV | implementada: deriva lineal con época global, marea externa y Eötvös sobre ejes verdaderos; falta modelo de marea interno | Boule, ICGEM/USGS y literatura geodésica | circuito cerrado y benchmark publicado |
| Gridding físico | fuentes equivalentes con guardia de Jacobiano y holdout; faltan superficies topográficas variables | Harmonica, Verde | holdout espacial y campo sintético armónico |
| MAG transform | pseudogravedad, propiedades aparentes de capa finita y componentes magnéticas implementadas; persisten restricciones del modelo y contraste independiente pendiente | ver manual práctico y contratos Core | prisma/dipolo con solución directa; no confundir propiedad aparente con inversión 3D |
| Profundidad | Euler 2D/3D por ventanas, Werner y SPI por perfiles tienen implementacion en Core; falta contraste de campo y ampliaciones avanzadas | ver [metodos y limites](../reference/methods/source_depth.md) | familias de SI, ruido, fuentes interferentes y alturas de referencia |
| Espectro | PSD, bins direccionales, ajuste espectral de profundidad y capas espectrales implementados; el error de ajuste no incluye toda la incertidumbre geológica | manual práctico y bibliografía por ficha | capas sintéticas y sensibilidad a ventanas, bandas y fuentes |
| FFT avanzado | Wiener inverso implementado con transferencia y regularización explícitas; no equivale a recuperar señal perdida ni cierra toda la propuesta FFT | contratos Core y manual práctico | respuesta impulsional y comparación espectral independiente |

## Prioridad B — inversión científicamente robusta

| Familia | Brecha candidata | Referencias iniciales | Validación mínima |
| --- | --- | --- | --- |
| Regularización | Lp, IRLS, referencia acotada e historial implementados para inversión escalar; falta diagnóstico sistemático de sensibilidad | SimPEG | cubo sintético, curva de convergencia y sensibilidad a beta |
| Petrofísica | bounds espaciales, modelos de referencia y unidades explícitas | SimPEG, PyGIMLi | recuperación bajo varios priors |
| Incertidumbre | resolución lineal, DOI por referencia y ensemble gaussiano lineal implementados; no describen toda inversión no lineal ni incertidumbre geológica | contratos Core, SimPEG y literatura | no presentar una sola inversión como verdad |
| Joint inversion | alternativas a cross-gradient y pesos normalizados | SimPEG, PyGIMLi | casos compatible e incompatible |
| Forward/QC | predicción independiente, residual espacial y espectral | Choclo, geoana, Harmonica | cierre forward-inverse con tolerancias |
| Geología 3D | restricciones desde GemPy/LoopStructural | GemPy, LoopStructural | geometría sintética versionada y trazabilidad de priors |

## Prioridad C — producto y reproducibilidad

- biblioteca de datasets sintéticos pequeños con resultados esperados;
- recetas versionadas de flujos completos y migración de esquemas JSON;
- reporte HTML/PDF de parámetros, dependencias, CRS, unidades y advertencias;
- comparación automatizada TerraWorkbench/Harmonica/GMT/SimPEG (CI QGIS ya ejecuta el catálogo compatible con Filter Stack);
- caché y ejecución en background con cancelación segura en QGIS;
- perfiles “rápido”, “conservador” y “publicación”, sin ocultar parámetros;
- traducción consistente español/inglés de algoritmos y ayuda contextual.

## Criterio de completitud por familia

Una familia no se considera completa por tener muchos nombres en el menú. Debe
cubrir adquisición/QC, transformación, interpretación, validación y exportación.
Para filtros FFT se exige además documentar detrend, relleno, padding, taper,
normalización, ganancia, longitud de onda, unidades del CRS y borde útil. Para
inversiones se exige malla, topografía, incertidumbre, regularización, bounds,
modelo inicial/referencia, convergencia y no unicidad.

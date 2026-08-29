# Mapa de cobertura y brechas

Este mapa ordena la expansión científica. No promete fechas y no convierte una
idea en algoritmo existente. La cobertura implementada detallada está en la
[referencia técnica](geofisica_potencial_referencia.md).

## Base actual consolidada

- Importación abierta de grillas y puntos, recuperación de metadatos y puente
  opcional para bases Geosoft.
- Gridding, crossovers, nivelación traverse/tie y microleveling direccional.
- Realces MAG/GRAV espaciales, FFT y mixtos con dominio declarado.
- RTP, RTE, transformación direccional e IGRF-14.
- Filtros espectrales configurables y Filter Stack reproducible.
- Cadena gravimétrica desde GRS80 hasta Bouguer completa, terreno e isostasia Airy.
- Inversión de densidad, susceptibilidad, MVI y conjunta GRAV–MAG.

## Prioridad A — cerrar el flujo 2D de producción

| Familia | Brecha candidata | Referencias iniciales | Validación mínima |
| --- | --- | --- | --- |
| Nivelación MAG | corrección diurna/base station, lag, heading y despike | PyGMI, literatura de levantamientos | líneas sintéticas + survey con base conocida |
| Nivelación GRAV | deriva instrumental, mareas, Eötvös y control de estaciones | Boule, ICGEM/USGS y literatura geodésica | circuito cerrado y benchmark publicado |
| Gridding físico | fuentes equivalentes y reducción a superficie común | Harmonica, Verde | holdout espacial y campo sintético armónico |
| MAG transform | pseudogravedad, componente vertical y conversión de componentes | SGTool, GMT, Blakely | prisma/dipolo con solución directa |
| Profundidad | Euler por ventanas e inversión Euler moderna | Harmonica, euler-inversion | familias de SI, ruido y fuentes interferentes |
| Espectro | espectro radial y estimación de profundidad con incertidumbre | GMT y bibliografía | dos capas sintéticas y análisis de sensibilidad |
| FFT avanzado | Wiener/depth filter, operador radial general y decorrugación espectral | GMT, MAGMAP público, papers | respuesta impulsional + comparación espectral |

## Prioridad B — inversión científicamente robusta

| Familia | Brecha candidata | Referencias iniciales | Validación mínima |
| --- | --- | --- | --- |
| Regularización | IRLS y normas Lp para modelos compactos/enfocados | SimPEG | cubo sintético, curva de convergencia y sensibilidad a beta |
| Petrofísica | bounds espaciales, modelos de referencia y unidades explícitas | SimPEG, PyGIMLi | recuperación bajo varios priors |
| Incertidumbre | resolución, sensibilidad, DOI y conjuntos de modelos | SimPEG, literatura | no presentar una sola inversión como verdad |
| Joint inversion | alternativas a cross-gradient y pesos normalizados | SimPEG, PyGIMLi | casos compatible e incompatible |
| Forward/QC | predicción independiente, residual espacial y espectral | Choclo, geoana, Harmonica | cierre forward-inverse con tolerancias |
| Geología 3D | restricciones desde GemPy/LoopStructural | GemPy, LoopStructural | geometría sintética versionada y trazabilidad de priors |

## Prioridad C — producto y reproducibilidad

- biblioteca de datasets sintéticos pequeños con resultados esperados;
- recetas versionadas de flujos completos y migración de esquemas JSON;
- reporte HTML/PDF de parámetros, dependencias, CRS, unidades y advertencias;
- comparación automatizada TerraWorkbench/Harmonica/GMT/SimPEG;
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


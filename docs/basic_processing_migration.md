# Procesamiento básico sin Oasis: alcance y plan

Estado: primera implementación independiente, validada el 20-09-2026.
Este documento no certifica equivalencia numérica con Oasis.

## Implementado

- `circular_median`: mediana espacial 2D en un disco de radio entero de 1 a 50
  píxeles. Usa vecinos con `dx² + dy² <= radio²`, ignora NoData y el exterior,
  y conserva las celdas originalmente ausentes. Radio 1 incluye cinco celdas,
  no una ventana cuadrada de nueve. Usa NumPy con bloques de trabajo acotados.
  Es una mediana de amplitudes sobre un disco, no una estadística angular ni
  un filtro Fourier. Con píxeles rectangulares el disco se vuelve elíptico en
  unidades de mapa. Se conservan el CRS y la georreferenciación del ráster.
- El catálogo de filtros permite separar operaciones espaciales, de frecuencia
  (Fourier 2D), mixtas y de modelos físicos, combinando dominio y búsqueda.
  El catálogo, inspector y panel principal son redimensionables; los parámetros
  tienen desplazamiento vertical. Las librerías siguen en el botón `i`.

- `grid_survey_points` conserva IDW (0) y nearest (1); añade TPS global (2)
  y TPS local (3). El global admite hasta 2000 puntos únicos por su coste de
  memoria; el local usa 64 vecinos por defecto y es una aproximación explícita.
- TPS usa `scipy.interpolate.RBFInterpolator`, kernel `thin_plate_spline`,
  polinomio afín y escala isotrópica. Promedia duplicados. El parámetro de
  suavizado no es tensión; el radio enmascara la salida por distancia al punto
  más cercano, sin restringir los puntos usados para ajustar TPS.
- `smooth_nine_point`: kernel binomial `[1,2,1] ⊗ [1,2,1]`, pesos válidos
  normalizados, pasadas configurables y conservación de NoData.
- `automatic_gain_control`: RMS global/RMS local, ventana cuadrada impar en
  píxeles, piso RMS y ganancia máxima. No resta la media. Conserva NoData y
  modifica amplitudes; no usar su salida como campo físico para inversión.
- Ambos filtros raster están registrados en Processing y son compatibles con
  Filter Stack. Incluyen información de dependencias y textos ES/EN/PT.

Referencias de implementación: [RBFInterpolator de SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.RBFInterpolator.html).
Pendientes: solver global escalable con tensión, controles iterativos de
convergencia, extensión/origen configurables y validación contra referencias
históricas. No se exponen controles ficticios para operaciones no implementadas.

## Alcance acordado

Puntos y canales → gridding → suavizado y filtros → exportación GeoTIFF.
La ejecución de esta cadena no debe necesitar Oasis Montaj. Un lector opcional
de GDB puede mantenerse separado, sin convertirlo en requisito para entradas
abiertas. No confundir independencia de la aplicación con ausencia de cualquier
biblioteca Geosoft.

Quedan fuera: pseudogradientes, crosshatch, fusión entre vuelos, máscaras de
comparación entre alturas y demás experimentos arqueológicos. Su presencia en
los scripts revisados no los convierte en funcionalidades solicitadas.

## Cobertura y prioridades

| Prioridad | Operación | Estado actual | Trabajo pendiente |
| --- | --- | --- | --- |
| P0 | Mínima curvatura | TPS global y aproximación TPS local, además de IDW/nearest | Validar frente a referencias; solver global escalable con tensión pendiente |
| P0 | Controles de gridding | Existen controles para los métodos actuales | Definir celda, extensión/origen, búsqueda, enmascaramiento, tensión, tolerancia e iteraciones del nuevo método; documentar qué parámetros no son trasladables |
| P1 | Suavizado de nueve puntos | Kernel binomial implementado y máscara preservada | Comparar con referencias; sin equivalencia propietaria certificada |
| P1 | AGC | RMS local con piso y límite de ganancia implementado | Comparar con referencias; separar realce visual de amplitud física |
| P1 | Derivadas, THDR, tilt y señal analítica | Candidatos en `algorithms/magnetic_filters.py` | Comparar signos, unidades, bordes, padding y máscaras con referencias |
| P1 | Continuación ascendente | Candidatos en `algorithms/transforms.py` y `algorithms/magnetic_filters.py` | Verificar altura, respuesta espectral y convenciones |
| P2 | Entrada de puntos/canales y exportación | Infraestructura existente | Encadenar entrada abierta, selección de canal, procesamiento y GeoTIFF sin ejecutar Oasis |
| P2 | Recetas y procedencia | Infraestructura de workflow existente | Integrar los nuevos algoritmos sin cambiar IDs ni romper recetas guardadas |

## Evidencia de los scripts revisados

ARCHIE, `archie_injector.py`, genera llamadas de creación/importación de GDB
(`NewGDB`, `impasc.gx`, `selall.gx`, `setchprj.gx`, `newxy.gx`, `closegdb.gx`),
gridding (`GridUtils.GriddingTool`, parámetros `RANGRID`), suavizado
(`gridflt9.gx`) y exportación (`CopyConvertMultiGrids`). Sus cadenas incluyen
`gridvd.gx`, `tiltdrv.gx`, `uxdxdydz.gx` + `gridmath.gx`, `gridasig.gx`,
`gridagc.gx` y continuación mediante `magmap.gx` o `FFT2D.MAGMAPFiltering`.

Los pipelines de trabajo reutilizan ese inyector para gridding y ensayos de
radio de búsqueda. El script `grid_moving_median_gdb_channels.py` también
comprueba el canal y el radio escritos en la macro. La escritura de canales
GDB mediante `gxpy` en `run_moving_median_on_clean_gdb.py` es una dependencia
de almacenamiento distinta del cálculo numérico; no es necesario reproducir
ese experimento para completar el alcance básico.

Parámetros históricos observados, útiles como casos de comparación, **no como
valores universales recomendados**: celda 0,25 m; radio 5 u 8 m; 100 iteraciones;
blank distance 3; tensión 0; tolerancia 0,01258. No asumir que búsqueda y blanking
tienen idénticas unidades o semántica en otro backend. ARCHIE incluye suavizado
de dos pasadas, mientras algunas cadenas de trabajo lo desactivan: debe ser un
paso opcional, no una alteración silenciosa del gridding.

## Orden de implementación

1. Establecer fixtures sintéticos y referencias de gridding: mismos puntos,
   canal, CRS, unidades, origen, extensión y máscara. Conservar originales.
2. Seleccionar y verificar el backend de mínima curvatura: licencia,
   distribución en QGIS/Windows, dependencias, convergencia y coste de memoria.
   No seleccionar una biblioteca únicamente porque tenga un método parecido.
3. Implementar núcleo y adaptador Processing; conservar IDW/nearest como
   opciones explícitas. Reportar falta de convergencia y parámetros efectivos.
4. Añadir suavizado de nueve puntos y AGC como procesos independientes,
   incluyendo salidas constantes, bordes y NoData en sus pruebas.
5. Validar las transformaciones existentes y conectar la receta completa con
   entradas abiertas y salida GeoTIFF. La comparación con resultados históricos
   no debe introducir Oasis como dependencia de ejecución ni de CI.

## Criterios de aceptación

- Pruebas de campo constante, plano, anomalía sintética, puntos duplicados,
  cobertura irregular, huecos, borde, datos no finitos y entradas insuficientes.
- Comprobar CRS, resolución, alineación, unidades, NoData y cobertura por
  separado de las diferencias de amplitud. No crear soporte fuera de la máscara
  acordada por rellenar huecos para una FFT.
- Comparar error medio, RMSE, máximos, amplitud y desplazamiento de anomalías;
  evaluar interior y borde por separado. Definir tolerancias antes de aceptar
  equivalencia; compartir un nombre no basta.
- Registrar backend y versión, parámetros efectivos y advertencias. Declarar
  dependencias/licencias y mostrarlas discretamente en la información de cada
  proceso. Etiquetas y ayuda nuevas en español, inglés y portugués.
- Una ejecución limpia con puntos de formato abierto debe completar toda la
  receta sin invocar Oasis, macros GX ni requerir una GDB intermedia.

## Límites de esta revisión

No se ejecutaron los pipelines históricos ni se reprodujeron sus resultados.
Las pruebas sintéticas están en `tests/test_basic_processing.py`; la integración
QGIS se verifica con `tests/qgis_basic_processing_smoke.py`.
No se certifica equivalencia propietaria de mínima curvatura, suavizado o AGC.
No se modificaron datos ni scripts de ARCHIE o del trabajo arqueológico.

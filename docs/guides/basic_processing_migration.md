# Procesamiento básico: alcance y plan

Estado: primera implementación independiente, validada el 20-09-2026.

## Implementado

- <code>circular_median</code>: mediana espacial 2D en un disco de radio entero de 1 a 50
  píxeles. Usa vecinos con <code>dx² + dy² &lt;= radio²</code>, ignora NoData y el exterior,
  y conserva las celdas originalmente ausentes. Radio 1 incluye cinco celdas,
  no una ventana cuadrada de nueve. Usa NumPy con bloques de trabajo acotados.
  Es una mediana de amplitudes sobre un disco, no una estadística angular ni
  un filtro Fourier. Con píxeles rectangulares el disco se vuelve elíptico en
  unidades de mapa. Se conservan el CRS y la georreferenciación del ráster.
- El catálogo de filtros permite separar operaciones espaciales, de frecuencia
  (Fourier 2D), mixtas y de modelos físicos, combinando dominio y búsqueda.
  El catálogo, inspector y panel principal son redimensionables; los parámetros
  tienen desplazamiento vertical. Las librerías siguen en el botón <code>i</code>.

- <code>grid_survey_points</code> conserva IDW (0) y nearest (1); añade TPS global (2)
  y TPS local (3). El global admite hasta 2000 puntos únicos por su coste de
  memoria; el local usa 64 vecinos por defecto y es una aproximación explícita.
- TPS usa <code>scipy.interpolate.RBFInterpolator</code>, kernel <code>thin_plate_spline</code>,
  polinomio afín y escala isotrópica. Promedia duplicados. El parámetro de
  suavizado no es tensión; el radio enmascara la salida por distancia al punto
  más cercano, sin restringir los puntos usados para ajustar TPS.
- <code>smooth_nine_point</code>: kernel binomial <code>[1,2,1] ⊗ [1,2,1]</code>, pesos válidos
  normalizados, pasadas configurables y conservación de NoData.
- <code>automatic_gain_control</code>: RMS global/RMS local, ventana cuadrada impar en
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
El lector opcional de archivos GDB de Geosoft se utiliza para importar ese formato.

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
| P1 | Derivadas, THDR, tilt y señal analítica | Candidatos en <code>algorithms/magnetic_filters.py</code> | Comparar signos, unidades, bordes, padding y máscaras con referencias |
| P1 | Continuación ascendente | Candidatos en <code>algorithms/transforms.py</code> y <code>algorithms/magnetic_filters.py</code> | Verificar altura, respuesta espectral y convenciones |
| P2 | Entrada de puntos/canales y exportación | Infraestructura existente | Encadenar entrada abierta, selección de canal, procesamiento y GeoTIFF |
| P2 | Recetas y procedencia | Infraestructura de workflow existente | Integrar los nuevos algoritmos sin cambiar IDs ni romper recetas guardadas |

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
   entradas abiertas y salida GeoTIFF.

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
  receta con entradas y salidas abiertas.

## Límites de esta revisión

No se ejecutaron los pipelines históricos ni se reprodujeron sus resultados.
Las pruebas sintéticas están en <code>tests/test_basic_processing.py</code>; la integración
QGIS se verifica con <code>tests/qgis_basic_processing_smoke.py</code>.
No se certifica equivalencia propietaria de mínima curvatura, suavizado o AGC.
No se modificaron datos ni scripts de ARCHIE o del trabajo arqueológico.

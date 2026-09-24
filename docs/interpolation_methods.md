# Interpoladores independientes

Actualizado el 24 de septiembre de 2026. El método de mínima curvatura predeterminado usa diferencias finitas, restricciones fuera de nodo y refinamiento multirresolución. Es independiente y experimental; no se certifica equivalencia exacta con RANGRID. Sin(x)/x interpola muestras regulares mediante una ventana Lanczos explícita.

## Uso

En Interpolar puntos de levantamiento a GeoTIFF se conservan los índices: 0 IDW, 1 vecino cercano, 2 TPS global, 3 TPS local, 4 sin(x)/x regular y 5 mínima curvatura experimental.

Para puntos GPS dispersos, usar un interpolador de puntos. El método sinc exige una retícula regular y los espaciados originales X/Y; rechaza puntos irregulares. Para expandir una grilla arqueológica, usar sinc_interpolation, con FACTOR_X, FACTOR_Y y LOBES. Conserva centros y valores de muestras originales y no extrapola más allá de los centros extremos. Reducir el tamaño de celda no aumenta la resolución medida.

## Mínima curvatura

El método vigente aplica la ecuación biharmónica en nodos libres y sustituye la ecuación del nodo más próximo a cada dato de trabajo por una restricción de Taylor de segundo orden. Incluye derivadas axiales y mixtas. Esa aproximación reproduce polinomios cuadráticos; no constituye interpolación exacta de cualquier superficie continua.

Los datos se agrupan por celdas centradas en nodos. Se conservan el centroide XY y el promedio del canal; esto ocurre incluso con desmuestreo 1. En cada nivel se selecciona como máximo un dato de trabajo por nodo. No se afirma que la grilla pase por cada observación original individualmente.

La semilla inicial utiliza distancia inversa dentro del radio de búsqueda, con la potencia seleccionada. Si no hay vecinos, usa el promedio de los datos de trabajo. Después se realizan pasadas Gauss-Seidel por factores 16, 8, 4, 2 y 1, empezando en el factor elegido. La cota de iteraciones por nivel es el máximo final dividido por el factor, con mínimo una pasada. La superficie previa se prolonga bilinealmente. El dominio se redondea a intervalos de la malla inicial, añade una franja de un nodo por nivel y se recorta al final. El plano retirado antes del cálculo se restaura al terminar.

Los nodos libres emplean el operador derivado de la energía discreta ||Dxx u||² + 2||Dxy u||² + ||Dyy u||², con bordes naturales discretos. Al sustituir filas para imponer observaciones fuera de nodo, el sistema es de colocación: no es el sistema variacional con fuerzas adjuntas distribuidas. La formulación, los bordes y la escala de tensión son propios y no están certificados como idénticos a Oasis.

Se comprueban tres porcentajes por pasada: cambio de nodos, residuo de ecuación dividido por su diagonal y residuo en los datos de trabajo. Solo se declara convergencia si los tres alcanzan el porcentaje exigido dentro de la tolerancia. Un límite de iteraciones alcanzado se informa explícitamente. No se confunde cumplimiento de restricciones con coincidencia frente a Oasis.

Radio inicial, malla gruesa, potencia y porcentaje de paso están conectados al solver multirresolución. Pendiente de ponderación distinta de cero sigue rechazada por falta de implementación verificada. El blanking utiliza la distancia a las observaciones originales, después de resolver. Hay una cota de 250.000 nodos de trabajo, incluidos márgenes. No hay validación de rendimiento con ocho millones de observaciones.

El backend conserva solver="variational" para comparaciones explícitas con la versión del 23 de septiembre. Resuelve directamente el sistema de mínima energía con multiplicadores de Lagrange y verifica sus residuos. Ese modo registra como no utilizados los controles de semilla y porcentaje de paso. La operación QGIS predeterminada usa el modo multirresolución.

## Diagnóstico Woodlawn

Se usó un ASC de 602.595 observaciones, canal anomaly_mm_bw, transformado por GDAL/PROJ al CRS de referencia. La comparación usa nodos del GRD: la exportación histórica a GeoTIFF coloca el origen del nodo en la esquina del píxel y desplazaba la comparación 0,125 m en cada eje. Los GeoTIFF nuevos sitúan correctamente sus centros en los nodos. Ningún original se modifica.

El 24 de septiembre se ejecutó Oasis 2025.2.1.53 sobre una copia de la GDB. Con 100 iteraciones reprodujo exactamente los valores del GeoTIFF histórico. Con 1.000 iteraciones, manteniendo los demás controles, cambió respecto a esa referencia con RMSE 2,943783 nT; en nodos a más de un metro de los datos, ese cambio fue 11,189114 nT. Esto demuestra que el límite iterativo influye en la referencia, especialmente donde faltan datos; no prueba por sí solo todas las diferencias de implementación.

Se compararon todos los modelos sobre la misma máscara de 63.270 celdas. No se excluyeron los bordes de las métricas globales.

| Versión | RMSE global nT | MAE global nT | RMSE interior a más de 3 m del borde nT |
| --- | ---: | ---: | ---: |
| Solver anterior con nodos corregidos | 8,110017 | 2,919229 | 8,070605 |
| Variacional del 23 de septiembre | 10,511783 | 2,101339 | 0,872975 |
| Multirresolución corregida del 24 de septiembre | 2,069831 | 0,566924 | 0,642314 |

La última corrección reduce el RMSE global un 80,3 % respecto a la versión variacional. En la franja de hasta un metro del límite de cobertura, el RMSE baja de 35,182824 a 5,890672 nT. Esa franja contiene 4.059 celdas, el 6,42 % de la comparación; en la versión variacional concentraba el 71,87 % del error cuadrático. El 5,25 % de celdas a más de un metro del dato más cercano concentraba el 83,33 % del error. No hay huecos internos en la máscara comparada; los focos se sitúan en el norte y en los límites irregulares noroeste y sureste.

La distancia al borde es euclídea sobre la máscara común, tratando simétricamente los cuatro lados de la matriz mediante un marco externo. No equivale a erosionar doce veces con una cruz: por eso el subconjunto interior y sus métricas difieren ligeramente del informe del 23 de septiembre. El interior actual contiene 51.360 celdas. Los subconjuntos sirven para diagnosticar, no reemplazan la métrica global.

Ampliar solo el margen rectangular dejó RMSE entre 10,00 y 10,37 nT en las pruebas. Resolver exactamente las ecuaciones por colocación, sin refinamiento iterativo, dio 12,31 nT. La mejora principal se obtuvo al combinar restricciones fuera de nodo con el procedimiento multirresolución limitado por iteraciones. No se aplicó recorte de amplitudes ni una corrección ajustada a los valores de Oasis.

La salida tiene 322 × 239 celdas; la correlación global es 0,999200. El núcleo tarda aproximadamente 2,67 s, sin importación ni escritura. Con 100 iteraciones todavía se alcanza el límite: pasan el criterio de cambio el 96,75 % de los nodos y la tolerancia de datos el 99,986 %. El residuo máximo de datos es 0,016931 nT. La máscara completa aún difiere de Oasis: hay 446 celdas exclusivas de Terra y 68 exclusivas de Oasis. Estas limitaciones impiden afirmar paridad o convergencia completa con esa receta.

## Sin(x)/x y pruebas

Sinc usa sinc(t) = sin(πt)/(πt), con valor 1 en cero, multiplicada por sinc(t/a) dentro del soporte a. El argumento usa el espaciado ORIGINAL de muestras. Se normalizan pesos en bordes truncados. Si falta una muestra interior necesaria, la salida queda NoData. Los duplicados se promedian y las muestras originales se conservan. No se certifica equivalencia con Geoplot.

La expansión Woodlawn produjo 643 × 477 muestras conservando los valores originales dentro de 1e-8. Pasaron 168 pruebas unitarias, Ruff y la validación de empaquetado. La prueba real QGIS verificó TPS, mínima curvatura, sinc, expansión anisótropa y georreferenciación. Las pruebas del solver incluyen polinomios fuera de nodo, residuos de ecuación, falta de convergencia, cancelación y controles de semilla.

## Artefactos reproducibles

- Resultado y GeoTIFF: E:/0. Projects/0. Other Projects/TerraWorkbench_validation/woodlawn_multilevel_20260924_01/report.json.
- Mapas, errores GeoTIFF y contribuciones por zona: E:/0. Projects/0. Other Projects/TerraWorkbench_validation/woodlawn_edges_20260924_deliverable/spatial_report.json. error_1 corresponde al solver anterior; error_2 al variacional; error_3 a la corrección actual.
- Copia de GDB, macros, salidas y registros de las dos ejecuciones Oasis: E:/0. Projects/0. Other Projects/TerraWorkbench_validation/woodlawn_edges_20260924_01/oasis_iterations.
- Scripts en el repositorio: validate_woodlawn_interpolation.py y diagnose_woodlawn_edges.py, bajo scripts. La carpeta de diagnóstico conserva además las sondas de hipótesis y el ejecutor Oasis. Los informes registran hashes y comprobaciones de originales intactos.

## Fuentes

- [RANGRID: parámetros públicos](https://help.seequent.com/Oasismontaj/2025.2/Content/gxhelp/r/rangrid_gx.htm).
- [Archivo de control RANGRID](https://help.seequent.com/Oasismontaj/2025.2/Content/gxhelp/r/rangrid_control_file.htm).
- [Geosoft: Topics in Gridding, páginas 4–6](https://files.seequent.com/MySeequent/technical-papers/topicsingriddingworkshop.pdf): inicialización, refinamiento y efectos de detener las iteraciones.
- [GMT surface](https://docs.generic-mapping-tools.org/dev/surface.html): referencia pública de mínima curvatura, tensión y bordes naturales; no demuestra cómo implementa Oasis sus bordes.
- [Geoplot: interpolación sin(x)/x](https://www.geoscan-research.co.uk/Gp300Proc3.pdf).

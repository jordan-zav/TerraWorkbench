# Validación con Milligan South

El dataset contiene una GDB Geosoft de 64.149 puntos, 55 líneas y 32 canales, ocho grids nativos GRD y sus metadatos ISO. El inventario se obtuvo mediante el runtime público de Geosoft instalado en Windows, porque GDAL no reconoce directamente la GDB ni los GRD nativos. A partir del CSV exportado, el gridding y la comparación fueron ejecutados por TerraWorkbench, QGIS, GDAL y Harmonica.

La GDB declara un levantamiento aéreo de 1993 en British Columbia, con plataforma de ala fija, altura media de sensor de 120 m, líneas de producción con separación de 500 m y CRS NAD27 / UTM zone 10N, EPSG:26710. Los puntos contienen longitud, latitud, f_mtf, f_adrn, f_pot, f_rtk, f_ruk, f_rut, f_tho y f_ura, entre otros canales.

## Procedimiento

Para cada canal se creó una capa QGIS desde Milligan South_all_channels.csv usando p_long y p_lat en EPSG:4326. TerraWorkbench ejecutó su interpolación IDW con 12 vecinos, potencia 2, celda de 100 m y radio de búsqueda de 1.000 m en EPSG:26710. El producto se comparó con el GRD entregado del mismo canal.

El origen de puntos no coincide con el origen de los GRD. Por eso cada celda producida se asoció a la celda de referencia más cercana, siempre que la diferencia de cada eje fuese menor que media celda. Esto evita presentar como igualdad exacta una comparación con distinto origen de malla. El resultado mide señal y estructura espacial en el área común, no equivalencia con la receta interna de Oasis.

## Resultado agregado

| Canal | Celdas comunes | Correlación | Sesgo IDW − GRD | MAE | RMSE |
| --- | ---: | ---: | ---: | ---: | ---: |
| f_mtf | 188.346 | 0,974 | −1,24 nT | 24,25 nT | 53,99 nT |
| f_adrn | 188.346 | 0,872 | 0,00 nGy/h | 2,14 nGy/h | 3,07 nGy/h |
| f_pot | 188.346 | 0,880 | −0,00 % | 0,10 % | 0,13 % |
| f_rtk | 187.984 | 0,822 | 0,05 | 0,23 | 0,34 |
| f_ruk | 187.984 | 0,722 | 0,03 | 0,16 | 0,22 |
| f_rut | 187.984 | 0,656 | 0,02 | 0,09 | 0,12 |
| f_tho | 188.346 | 0,799 | 0,01 ppm | 0,30 ppm | 0,46 ppm |
| f_ura | 188.346 | 0,589 | 0,00 ppm | 0,22 ppm | 0,34 ppm |

Cada resultado tiene su report.json bajo E:/0. Projects/0. Other Projects/TerraWorkbench_validation/milligan_channels_20260923. El resumen agregado está en summary.json.

La geometría producida por TerraWorkbench es 702 × 274 porque se ajusta a la extensión de los puntos. Los GRD entregados son 720 × 307 y usan el origen de malla 383512, 6065220. La zona común disponible para la comparación es de aproximadamente 188 mil celdas finitas. Todos los ocho informes pasaron las comprobaciones de CRS y cobertura mínima.

## Misma receta de filtro en Oasis y TerraWorkbench

Para comprobar la equivalencia matemática sin mezclar la etapa de interpolación, se tomó el mismo Milligan South_MTF.GRD como entrada para ambos programas. La receta fue un filtro binomial de nueve puntos, aplicado en dos pasadas, con conservación del tamaño y de la máscara del grid. Oasis ejecutó el macro mediante oms.exe, generó su GeoTIFF y TerraWorkbench ejecutó su algoritmo smooth_nine_point sobre una copia GeoTIFF de la misma malla.

Los dos productos tienen 720 × 307 celdas, EPSG:26710 y el mismo origen de píxel. Se compararon 196.152 celdas finitas: correlación 0,999810, sesgo TerraWorkbench menos Oasis de −0,0076 unidades, MAE 2,1046, RMSE 4,5148 y máximo absoluto 64,723. Esto confirma que el filtro implementado en TerraWorkbench reproduce la señal de Oasis con diferencias concentradas en bordes, nodata y precisión numérica, no en la estructura del grid.

El reporte reproducible está en E:/0. Projects/0. Other Projects/TerraWorkbench_validation/milligan_same_pipeline_20260923_04/report.json. El GeoTIFF de Oasis está en E:/0. Projects/0. Other Projects/TerraWorkbench_validation/milligan_same_pipeline_20260923_04/oasis_workspace/oasis_smooth9.tif y el de TerraWorkbench en E:/0. Projects/0. Other Projects/TerraWorkbench_validation/milligan_same_pipeline_20260923_04/terra_smooth9.tif. El macro ejecutado por Oasis y su salida de consola están en la carpeta oasis_workspace.

Esta prueba verifica el filtro sobre un grid ya construido. Todavía no certifica que ambos programas produzcan el mismo resultado desde la GDB cruda: esa prueba también debe fijar el método de interpolación, origen, extensión, máscaras, correcciones de línea y derivadas.

## Qué demuestra y qué no

Milligan demuestra que TerraWorkbench puede consumir puntos exportados desde una GDB Geosoft y reconstruir, con una interpolación documentada, el patrón de sus productos magnéticos y radiométricos sin ejecutar Oasis montaj durante el cálculo. También ofrece una referencia real para ajustar métodos y parámetros.

No demuestra igualdad celda por celda. El GRD histórico puede incluir una malla fija, selección de canales, máscaras, suavizados, correcciones y una interpolación distinta. El error MTF de 53,99 nT y la variación de correlación entre canales son evidencia de que el método debe calibrarse antes de sustituir una entrega histórica.

El siguiente trabajo útil es implementar una malla fija con el origen y extensión del GRD, identificar el método de interpolación y las máscaras mediante pruebas controladas, y separar correcciones de adquisición de la etapa de gridding. La lectura nativa de GDB/GRD sigue siendo una dependencia de conversión; los cálculos posteriores ya están en TerraWorkbench.

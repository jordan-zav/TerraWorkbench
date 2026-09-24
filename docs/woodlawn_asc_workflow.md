# Procesamiento de un ASC de Woodlawn

Validación local del 23 de septiembre de 2026. TerraWorkbench procesó el archivo completo 2026-08-08_18-08-54_rtr_processed_DTM_reassigned_Z.asc sin ejecutar ARCHIE ni Oasis montaj, sin cargar sus runtimes y sin consumir un grid de esos programas. Se usaron QGIS, GDAL/PROJ, NumPy, SciPy, PyArrow y xarray.

## Alcance comprobado

El ASC es una tabla tabulada de puntos, no un raster ASCII. Contiene 602.595 registros, 115 identificadores de línea y cinco sensores. El ejecutor conserva todos los canales en una base SurveyStore, añade coordenadas proyectadas y conecta su exportación de puntos con los algoritmos de Processing de TerraWorkbench. No se modificó la interfaz gráfica.

Se eligió anomaly_levelled_line, que ya contiene procesamiento anterior. Este ejercicio demuestra que es posible continuar desde ese ASC sin los programas propietarios; no reconstruye ni certifica las correcciones anteriores a su exportación. No se aplican otra vez nivelación por líneas, correcciones de altura ni correcciones temporales.

## Parámetros utilizados

| Etapa | Parámetros |
| --- | --- |
| Coordenadas | Longitude [°] como X; Latitude [°] como Y; entrada declarada EPSG:4326 y salida EPSG:32617 |
| Canal | anomaly_levelled_line, nT |
| Grid | IDW, potencia 2, 12 vecinos, celda de 0,25 m y radio de búsqueda de 1 m |
| Mediana | Disco de radio 2,5 m, equivalente a 10 píxeles; diámetro entre centros extremos de 5 m |
| Residual | Campo interpolado menos fondo de mediana circular |
| Suavizado | Dos pasadas del filtro binomial de nueve puntos sobre el residual |
| Derivadas | Este, norte y vertical ascendente de primer orden, calculadas por FFT directamente del residual sin suavizar |
| Preparación FFT | Remoción de plano, margen reflejado del 25 % por lado y taper del 100 % del margen; sin restaurar el plano |

El CRS del ASC es una declaración explícita porque el archivo no lo almacena. La salida UTM 17N coincide con el sistema usado por el DTM del manifiesto de Woodlawn. Los cinco sensores se interpolan en sus coordenadas suministradas. No se inventan desplazamientos ni se combinan otros vuelos.

## Resultados y verificaciones

Se generaron siete GeoTIFF de 322 filas por 239 columnas: campo, fondo de mediana, residual, residual suavizado y tres derivadas. Cada producto conserva 59.975 celdas válidas y 16.983 celdas NoData. El rellenado de huecos para FFT ocurre únicamente en el espacio de cálculo; al publicar se restaura la máscara.

La ejecución completa, incluidas las comprobaciones, tardó 29,13 segundos en este equipo. Se comprobaron 32 celdas mediante distancias directas a todos los puntos, independientemente del árbol espacial del interpolador. El error máximo IDW fue 0,00002853 nT, dentro de la tolerancia Float32 registrada. La mediana circular coincidió en las 32 celdas y la reconstrucción campo = fondo + residual tuvo error cero.

El SHA-256 del ASC se mantuvo idéntico antes y después y coincide con el manifiesto existente: 2e7354a4e1b0e7436cd1a092a57107abee393de37239eb6ae7a873338973e345.

La carpeta de resultados es E:/0. Projects/0. Other Projects/TerraWorkbench_validation/woodlawn_20260923_02. Incluye report.json, los siete GeoTIFF, points.csv y workspace con el catálogo y los canales versionados. La carpeta terminada en _01 corresponde a un intento previo incompleto; no es el resultado validado.

## Repetición

Desde la carpeta del repositorio, ejecutar con el Python de QGIS. La carpeta de salida debe ser nueva; el ejecutor rechaza sobrescribir resultados existentes. Ejemplo para PowerShell, usando una salida nueva:

    & 'E:\QGIS\bin\python-qgis-ltr.bat' scripts/process_archaeology_asc.py --source 'E:\Sandbox\Woodlawn Survey\03_processed\DTM_reassigned_Z\2026-08-08_18-08-54_rtr_processed_DTM_reassigned_Z.asc' --output 'E:\0. Projects\0. Other Projects\TerraWorkbench_validation\woodlawn_repeticion' --value anomaly_levelled_line --source-crs EPSG:4326 --target-crs EPSG:32617

El script admite otros nombres de coordenadas, línea, sensor y canal, así como celda, radios, unidades y CRS explícitos. Los parámetros elegidos permiten probar el recorrido y no constituyen una selección óptima para interpretar estructuras arqueológicas. No se aplicó reducción al polo, que requeriría parámetros geomagnéticos adicionales.

## Pruebas de software

Pasaron las 145 pruebas unitarias existentes, Ruff y la nueva prueba QGIS de integración con datos sintéticos públicos: importación ASC, conservación de registros, siete productos, comprobaciones numéricas y protección contra sobrescritura. La nueva prueba se añadió al flujo de integración continua.

Esto no certifica equivalencia numérica con ARCHIE u Oasis, procesamiento desde datos crudos de adquisición, todos los flujos arqueológicos ni rendimiento con ocho millones de puntos.

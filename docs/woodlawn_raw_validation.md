# Validación desde el ASC Raw track data

TerraWorkbench procesó el vuelo mag 1.1 de Woodlawn desde 2026-08-08_18-08-54_rtr.asc, usando Total field [nT]. No se ejecutaron ARCHIE ni Oasis montaj y no se utilizó el canal previamente nivelado.

## Entrada y alcance

La entrada está en E:/Sandbox/Woodlawn Survey/06_working/legacy/Data/Woodlawn_Geophys/pre_processed/mag 1.1/2026-08-08_18-08-54_rtr.asc. Su primera fila dice Raw track data, la segunda contiene las cabeceras y los datos empiezan en la tercera. El importador reconoció esta estructura y conservó exactamente los 602.595 valores de campo total, comprobados contra una segunda lectura independiente del ASC.

Hay 23 tracks y cinco sensores, que forman 115 perfiles track-sensor. Los 115 identificadores Line_ID de la validación anterior corresponden a estos perfiles, no a 115 pasadas independientes. No se detectaron retrocesos ni tiempos repetidos dentro de cada perfil, ni intervalos mayores de 10 ms. Estos controles no certifican la sincronización absoluta con el GNSS.

El campo total varía entre 51.089,40 y 55.762,64 nT. La diferencia máxima respecto de la norma de las tres componentes suministradas es 0,0121 nT. Es una comprobación de consistencia interna, no una recalibración del sensor.

## Procesamiento y resultado

Se emplearon coordenadas de entrada declaradas como EPSG:4326, salida EPSG:32617, gridding IDW de 12 vecinos y potencia 2, celda de 0,25 m y radio de búsqueda de 1 m. Se generaron campo, fondo de mediana circular de radio 2,5 m, residual, residual con dos pasadas de suavizado y tres derivadas FFT del residual sin suavizar.

Los siete GeoTIFF tienen 322 filas por 239 columnas y conservan 59.976 celdas válidas. Los originales permanecen intactos, comprobado mediante SHA-256. La ejecución y sus controles incorporados tardaron 21,93 segundos. La interpolación se comprobó en 32 celdas con distancias directas a todos los puntos; su error máximo fue 0,00183 nT, dentro de la tolerancia Float32. Las comprobaciones de mediana y reconstrucción del residual dieron error cero.

La salida está en E:/0. Projects/0. Other Projects/TerraWorkbench_validation/woodlawn_raw_20260923_01. El archivo report.json contiene parámetros, versiones de canales, hashes y controles por producto. raw_import_audit.json contiene la verificación independiente de importación y los controles temporales de cada perfil.

## Repetición desde PowerShell

Ejecutar desde el repositorio, eligiendo una carpeta de salida que todavía no exista:

    & 'E:\QGIS\bin\python-qgis-ltr.bat' scripts/process_archaeology_asc.py --source 'E:\Sandbox\Woodlawn Survey\06_working\legacy\Data\Woodlawn_Geophys\pre_processed\mag 1.1\2026-08-08_18-08-54_rtr.asc' --output 'E:\0. Projects\0. Other Projects\TerraWorkbench_validation\woodlawn_raw_repeticion' --value 'Total field [nT]' --line 'Track ID' --source-crs EPSG:4326 --target-crs EPSG:32617

Pasaron las 145 pruebas unitarias, Ruff y la prueba QGIS de integración, ahora con el encabezado adicional Raw track data.

## Qué independencia se ha demostrado

Se puede pasar del ASC raw exportado a los siete productos sin Oasis montaj ni ARCHIE. La lectura directa del binario PMXLF y el procesamiento efectuado por el exportador SENSYS quedan fuera de esta prueba.

El ejecutor no aplica correcciones diurnas, lag, rumbo, calibración entre sensores, nivelación por cruces ni normalización de altura. El residual por mediana no sustituye esas correcciones. Su necesidad y parámetros deben evaluarse con los registros auxiliares y el objetivo del levantamiento. Esta validación demuestra ejecución e integridad numérica; no certifica una entrega arqueológica final ni equivalencia con todos los resultados de Oasis.

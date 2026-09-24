# Correcciones magnéticas conectadas a la base de datos

El backend ahora publica seis canales versionados mediante SurveyStore.correct_magnetic: término aditivo de lag, despiking, base, rumbo, corrección total y campo corregido. Todos se publican en una sola transacción. Los originales permanecen intactos. La interfaz gráfica no se modificó.

## Modelo y controles

Campo corregido = campo original + término de lag + término de despiking + término de base + término de rumbo.

La receta distingue expresamente operaciones habilitadas y deshabilitadas. Un término cero de una operación deshabilitada no significa que su corrección se haya estimado o validado.

| Operación | Definición y requisitos |
| --- | --- |
| Lag | Evalúa el campo en t + lag, con interpolación dentro del mismo tramo. Requiere un lag explícito en segundos. No extrapola. |
| Despiking | Compara el centro con la mediana de una ventana completa; umbral = factor × 1,4826 × MAD. Sustituye candidatos por la mediana. |
| Base | Resta la variación respecto de una referencia explícita. Exige tiempos estrictamente crecientes, en segundos y sobre el mismo reloj que el vuelo. Fuera de cobertura devuelve valores ausentes. |
| Rumbo | Añade a × cos(azimut) + b × sin(azimut), con ambos coeficientes explícitos y un canal angular referido al norte verdadero, en grados. No estima automáticamente los coeficientes. |

El procesamiento conserva el orden original y separa los tramos al cambiar track o sensor, encontrar datos ausentes o superar el intervalo temporal admitido. Rechaza tiempos duplicados o decrecientes dentro de un tramo. No une partes discontinuas ni interpola a través de huecos. El backend actual limita la carga a tres millones de registros; no está certificado para ocho millones.

Se guardan parámetros, versiones de entrada, estadísticas y, cuando se suministra una base, sus observaciones y su huella SHA-256. La conversión del tiempo del levantamiento a segundos es explícita.

## Ensayo Woodlawn

Entrada: el ASC Raw track data del vuelo mag 1.1 de las 18:08:54. Campo: Total field [nT]. Los 602.595 registros forman 115 perfiles, correspondientes a 23 tracks y cinco sensores.

Se habilitó únicamente despiking con ventana de siete muestras y umbral de seis MAD normalizadas, como variante de evaluación. Con muestreo de 5 ms, los centros extremos de la ventana están separados por 30 ms. El máximo intervalo permitido entre muestras fue 20 ms.

- 148 muestras modificadas, equivalentes al 0,02456 % del archivo.
- Cambio absoluto mediano: 39,65 nT; máximo: 93,85 nT.
- 690 valores filtrados ausentes en los extremos: tres por extremo de cada perfil. Los registros originales se conservan; los grids usan 601.905 valores corregidos válidos.
- Verificación independiente de las ventanas en todas las filas: coincidencia exacta.
- Reconstrucción mediante la suma de términos: error cero.
- Siete GeoTIFF generados con el canal corregido y sus máscaras verificadas. Conservan 59.966 celdas válidas; la máscara difiere del ensayo sin despiking porque ahora faltan las muestras de extremo. Cada filtro de raster conserva la nueva máscara.
- Original intacto por SHA-256. Ejecución completa: 22,64 segundos en este equipo.

La carpeta de salida es E:/0. Projects/0. Other Projects/TerraWorkbench_validation/woodlawn_corrections_20260923_01. report.json contiene la receta y los productos. correction_audit.json contiene los controles independientes. despike_changes.csv localiza las 148 modificaciones e incluye valores originales, corregidos y diferencias. Las muestras detectadas son candidatas a picos; el criterio estadístico por sí solo no demuestra un fallo instrumental. Esta variante no sustituye automáticamente la entrega aceptada.

## Repetir el ensayo

Desde el repositorio, con una carpeta de salida nueva:

    & 'E:\QGIS\bin\python-qgis-ltr.bat' scripts/process_archaeology_asc.py --source 'E:\Sandbox\Woodlawn Survey\06_working\legacy\Data\Woodlawn_Geophys\pre_processed\mag 1.1\2026-08-08_18-08-54_rtr.asc' --output 'E:\0. Projects\0. Other Projects\TerraWorkbench_validation\woodlawn_despike_repeticion' --value 'Total field [nT]' --line 'Track ID' --source-crs EPSG:4326 --target-crs EPSG:32617 --despike-window 7 --despike-threshold 6

El ejecutor ofrece despiking antes del gridding. Las correcciones de base, lag y rumbo se suministran por la API del backend; no se añadieron controles nuevos en la GUI ni opciones para ellas en este ejecutor.

## Pendientes para este levantamiento

Se localizaron archivos de componentes magnéticas, GNSS y posiciones relativas de los sensores. El archivo de posiciones no equivale a coeficientes de calibración magnética. No se identificó una estación base magnética en la búsqueda de archivos por nombre ni en los auxiliares revisados.

Por eso base, lag y rumbo están deshabilitados en el ensayo real. Se validaron con señales sintéticas de resultado conocido. No se aplicaron nivelación por cruces, calibración de sensores ni normalización de altura. La nivelación ya existente requiere cruces o solapes verificables y un ajuste justificado; no se reemplazó por una resta arbitraria de medianas por línea.

Pasaron 150 pruebas unitarias, Ruff, validación del empaquetado y la prueba QGIS de ambos recorridos: raw sin correcciones y despiking conectado a grids. Los tests comprueban separación entre sensores, tracks y huecos, ausencia de extrapolación, términos aditivos, protección de originales, colisiones de nombres y cancelación.

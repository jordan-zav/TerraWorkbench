# 5. Workspaces, canales, versiones y linaje

[English](../en/05_bases_canales.md) · [Español](../es/05_bases_canales.md) · [Português](../pt/05_bases_canales.md)

## Modelo de almacenamiento

SurveyStore combina un catálogo SQLite con archivos Parquet inmutables. El catálogo identifica bases, canales, versiones y eventos. Parquet permite lectura por columnas y lotes; no es necesario cargar todas las variables para procesar una sola. El workspace es una unidad de trabajo, no un archivo GDB propietario.

Una base conserva alineación de filas. Seleccionar columnas no altera esa alineación. Una máscara o un filtro de vista limita una consulta; no reordena automáticamente la adquisición original. La geometría almacenada identifica canales XY y CRS, sin transformar sus coordenadas.

## Primera base desde la interfaz

Abrir el explorador, elegir Nuevo proyecto y una carpeta vacía, y después Importar texto / Parquet. Revisar el asistente antes de aceptar la carga. Seleccionar una base en la lista izquierda y solo los canales necesarios; Cargar selección muestra una página y no necesita volcar todas las filas en la tabla. Las acciones de canales permiten preparar derivados y consultar su pipeline. Guardar los productos importantes fuera de temporales de sesión y conservar la carpeta completa del workspace.

![Versiones de canales](../assets/es/linaje.svg)

Figura 2. Un ejemplo conceptual de fuentes y canales derivados. La versión de entrada, además del nombre, determina qué contenido se procesó.

## Crear una variable derivada

Se recomienda expresar primero la magnitud y su unidad: mag_anomaly_nt, gravity_complete_bouguer_mgal o sensor_height_m. Añadir el paso distintivo cuando se necesiten alternativas, por ejemplo mag_anomaly_lowpass_nt. Una etiqueta no sustituye los parámetros registrados.

La fórmula usa un lenguaje aritmético restringido. Por ejemplo, c("field_nt") − c("main_field_nt") calcula una resta de canales alineados. No es un intérprete Python general y no debe usarse para ejecutar imports o instrucciones externas.

La derivación conserva versiones de entrada. Si el contenido cambió desde la revisión de la receta, detenerse y revisar otra vez. Duplicar un canal puede crear un alias de la misma versión inmutable sin copiar todos sus bytes; versiones posteriores evolucionan por separado.

## Publicar cálculos externos

publish_channels recibe arrays de longitud igual a las filas de la base, unidad por salida, versiones exactas de los canales usados y procedencia con nombre de operación. Solo admite nombres nuevos. Las salidas se publican juntas bajo transacción; NaN se guarda como nulo e infinitos o longitudes distintas se rechazan.

Registrar parameters, libraries y engine permite mostrar parámetros, bibliotecas y motor en el inspector de linaje. Incluir también fuentes de topografía, campo inductor y selección si participaron en el cálculo, aunque no aparezcan directamente en la fórmula final.

## Capacidad y trabajo seguro

La capacidad total de una base no es el límite de un filtro por tramo. El filtrado de canales admite hasta tres millones de muestras por tramo continuo, sujeto a los demás presupuestos. Una base con varias líneas puede contener más filas. No concatenar líneas para eludir controles de continuidad.

Un presupuesto de arrays publicados limita su tamaño float64 combinado; no limita toda la RAM del proceso ni incluye buffers del motor. Guardar originales fuera de los archivos derivados y respaldar catálogo y Parquet de manera coherente.

Ver [workspaces](../../guides/survey_workspaces.md), [explorador](../../guides/survey_explorer.md) y [contratos de evidencia](../../guides/api_evidence.md).

## Implementación relacionada

[survey_store](../../../terraworkbench_core/survey_store.py), [survey_explorer](../../../terraworkbench_core/survey_explorer.py), [survey_recipes](../../../terraworkbench_core/survey_recipes.py)

---

[Índice](README.md) · [Anterior](04_importacion.md) · [Siguiente](06_perfiles_qc.md)

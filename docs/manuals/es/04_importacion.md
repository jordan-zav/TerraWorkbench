# 4. Importación de texto, GRD y datos geoespaciales

[English](../en/04_importacion.md) · [Español](../es/04_importacion.md) · [Português](../pt/04_importacion.md)

## Inspeccionar antes de cargar

La detección automática propone codificación, separador, fila de encabezados, inicio de datos y tipos. Se basa en una muestra del archivo; una propuesta razonable no garantiza que todas las filas posteriores tengan la misma estructura. Revisar las líneas físicas numeradas, los nombres duplicados, signos, ausencias y separador decimal.

La importación de surveys usa survey_text_import. El módulo histórico text_import contiene otra API de tablas basada en pandas; no intercambiar sus opciones ni asumir que sus resultados son SurveyStore. La referencia de API conserva ambas firmas.

## Procedimiento con texto

1. Conservar el original y registrar tamaño, fecha y hash.
2. Obtener la inspección; revisar coma, punto y coma, tabulador o espacios.
3. Identificar filas de comentarios y encabezados, incluidas secciones por línea cuando existan.
4. Declarar tipos, unidades, columnas XY, Z, tiempo, línea y sensor.
5. Previsualizar filas convertidas y comprobar nulos y nombres.
6. Importar a una base nueva y comparar cantidad de filas, rangos y muestras.

Un identificador como 001 puede ser texto significativo. Convertirlo a entero elimina los ceros iniciales. Un FID de exportación no necesariamente es un tiempo ni una distancia, y el nombre Z puede representar altura de plataforma, terreno u otra cantidad.

## GRD y otros raster

La extensión GRD puede corresponder a varias codificaciones. El adaptador debe reconocer el formato; no tratar cualquier archivo GRD como un raster binario Geosoft. Verificar dimensiones, georreferenciación, CRS recuperado, título, unidades y NoData antes de procesar.

El flujo del plugin puede producir GeoTIFF de trabajo a partir de GRD u otros formatos compatibles. El archivo original permanece intacto. Una salida temporal debe exportarse a una carpeta elegida si se necesita conservarla. Registrar conversión, escala/offset y remuestreo, si lo hubo.

Una tabla XYZ irregular necesita un paso de gridding. Un lector de grilla regular no debe rellenar posiciones faltantes ni inventar una resolución. Si faltan filas o columnas, diagnosticarlo explícitamente.

## Bases externas

Esri FileGDB contiene capas o tablas accesibles mediante el stack geoespacial compatible. La GeoDatabase Geosoft de archivo único utiliza el puente opcional de inventario y exportación. Exportar canales a un formato abierto no significa que el Core procese con el software propietario.

## Aceptación de una importación

La carga se considera revisada cuando coinciden conteos esperados, columnas críticas, unidades, coordenadas y valores muestreados. Separar errores de sintaxis de valores físicamente improbables: ambos requieren tratamiento, pero no la misma corrección.

Lecturas: [workspaces](../../guides/survey_workspaces.md), [importadores y arquitectura](../../development/scientific_core.md), [modelo GDAL](https://gdal.org/en/stable/user/raster_data_model.html).

## Implementación relacionada

[survey_text_import](../../../terraworkbench_core/survey_text_import.py), [text_import](../../../terraworkbench_core/text_import.py)

---

[Índice](README.md) · [Anterior](03_coordenadas.md) · [Siguiente](05_bases_canales.md)

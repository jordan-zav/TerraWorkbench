# Conversión de GDB de Geosoft a un archivo abierto

El lector opcional de Windows requiere Seequent Connect y una cuenta Seequent ID. El administrador de dependencias solicita autorización para descargar los componentes del lector. La alternativa con archivos abiertos es importar XYZ o CSV.

La conversión conserva el archivo fuente. El resultado es una carpeta SurveyStore con un catálogo SQLite y tablas Parquet. Conserva tipos nativos, espectros, texto, valores ausentes y los fiduciales propios de cada canal.

El inventario registra los canales, líneas y metadatos disponibles. El archivo verification.json registra la verificación de las muestras mediante una segunda lectura del origen. Los metadatos que el lector no puede recuperar se registran como no disponibles. El estado de verificación de datos y el de integridad de metadatos se registran por separado.

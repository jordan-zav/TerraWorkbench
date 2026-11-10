# 2. Instalación, dependencias y entorno

[English](../en/02_instalacion.md) · [Español](../es/02_instalacion.md) · [Português](../pt/02_instalacion.md)

La primera instalación de dependencias puede tardar unos 10 minutos, según la conexión y las cachés disponibles.

## Elegir el punto de entrada

El plugin QGIS y la distribución independiente del Core son productos relacionados con versiones distintas. La versión del plugin está en metadata.txt; la del paquete Python, en pyproject.toml. No asumir que sus números deben coincidir. La compatibilidad declarada por QGIS tampoco sustituye la verificación del Python que ejecuta un motor opcional.

El Core declara Python 3.10 o posterior y requiere NumPy y SciPy. Los extras de inversión, eléctrico y EM se declaran para Python 3.11 o posterior, con SimPEG 0.25, discretize 0.12 y choclo 0.3 en los rangos indicados por el proyecto. Revisar siempre el [contrato de instalación](../../../pyproject.toml) antes de fijar un entorno.

## Instalación independiente

Desde un entorno Python dedicado, situado en la raíz del repositorio:

    python -m pip install .
    python -m pip install ".[storage,coordinates,geomagnetism]"

Para inversión se usa el extra inversion en un Python compatible. Estos comandos explican el mecanismo de instalación; no se deben ejecutar sobre el Python de QGIS para intentar reparar indiscriminadamente sus bibliotecas nativas.

| Necesidad | Dependencia o extra |
| --- | --- |
| Catálogo y canales Parquet | storage: PyArrow |
| Transformación horizontal | coordinates: PyProj |
| Campo principal IGRF | geomagnetism: ppigrf |
| Prismas y fuentes equivalentes | prisms: Harmonica y su entorno compatible |
| Inversión potencial | inversion: SimPEG, discretize, choclo |
| Tablas históricas | tables: pandas |
| Registros LAS | borehole: lasio |
| Rasgos de imagen y wavelets | structure, archaeology según la operación |
| Raster y exportación geoespacial | GDAL o rasterio, según el adaptador |

La declaración del extra no significa que todos sus motores se importen al iniciar. Los motores opcionales se cargan cuando se usan. Registrar versiones efectivamente instaladas, no solo el rango de requisitos.

## Instalación del plugin

Obtener un ZIP validado con scripts/package_plugin.py y cargarlo con el mecanismo de instalación desde ZIP de QGIS. Comprobar que el proveedor TerraWorkbench aparece en Processing y que la versión coincide con metadata.txt. Una carpeta de código copiada a mano puede ocultar dependencias ausentes o una instalación anterior todavía activa.

Los adaptadores de GRD, GeoTIFF, FileGDB y capas requieren un runtime nativo compatible. El acceso opcional a una GeoDatabase Geosoft usa su puente de lectura/exportación, no constituye el motor numérico del Core. Una GeoDatabase Geosoft y una Esri FileGDB no son el mismo formato.

## Diagnóstico mínimo

Verificar el ejecutable Python real, importar únicamente el módulo necesario, consultar su firma y ejecutar un ejemplo sintético pequeño. Si falla una biblioteca nativa, conservar el mensaje original y el inventario de versiones. Evitar instalar paquetes repetidamente sin identificar qué Python recibió la instalación.

En equipos con recursos compartidos, separar cachés reutilizables de temporales por ejecución y evitar dos procesos escribiendo el mismo workspace. La memoria de una matriz no representa el consumo total del programa.

Detalles en [Core científico](../../development/scientific_core.md), [dependencias](../../../requirements/base.txt) y [licencias de terceros](../../legal/THIRD_PARTY_LICENSES.md).

## Desinstalación completa

Primero abre el gestor de dependencias de TerraWorkbench y pulsa **Eliminar dependencias y preferencias**. Revisa la carpeta exacta del perfil activo, el número de archivos, los bytes totales y las claves; después confirma. Reinicia QGIS como se indica; si el complemento sigue instalado, pedirá reinstalar las dependencias. Para desinstalar completamente, elimina TerraWorkbench desde **Administrar e instalar complementos** de QGIS después de la limpieza.

Alternativa manual: cierra QGIS y elimina únicamente <code>PERFIL_ACTIVO/python/dependencies/TerraWorkbench/PYTHON_MAJOR.MINOR</code>, usando el perfil que informa QGIS, incluida una raíz de perfiles personalizada. Elimina solo las claves bajo <code>TerraWorkbench/</code> de la configuración QSettings de ese perfil: defaultOutputDirectory, keepIntermediate, defaultBand, openInspectorAfterAdd, confirmClearStack, addFinalResultToProject, showScientificTooltips, geosoftLocation, localTestDataDirectory, language, dependencyDialogVersion y surveyWorkspace. Revisa cualquier clave adicional del mismo espacio. Conserva otros perfiles, versiones de Python y complementos. La acción automática rechaza enlaces y uniones; nunca borra al ejecutar unload ni al desactivar el complemento. En Windows, las DLL cargadas pueden impedir el borrado; deja de usar el complemento, reinicia QGIS y aplica la alternativa manual si hace falta.

---

[Índice](README.md) · [Anterior](01_inicio.md) · [Siguiente](03_coordenadas.md)

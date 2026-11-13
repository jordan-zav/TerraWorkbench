# Archivo abierto de GeoDatabase Geosoft

[Índice de desarrollo](README.md)

## Esquema y conservación

El archivo es una carpeta con catalog.sqlite, databases/samples.parquet, archive.json y verification.json. Mantiene SurveyStore versión 1 y añade la extensión gdb_open_archive versión 1, sin modificar las tablas ni la API anteriores. Las tablas adicionales son gdb_archives, gdb_channels, gdb_lines y gdb_channel_lines. survey_store.py permanece intacto.

Parquet contiene LINE, FIDUCIAL y una columna por canal. Se conservan int8/16/32/64, float32/64 y texto Unicode, incluidos enteros mayores que 2 elevado a 53. Los canales array son listas de tamaño fijo; los espectros de 256 elementos conservan su dimensión. Los dummies se representan como nulos, incluso dentro de una lista; los NaN originales que no son dummies permanecen como valores. El dummy original, el tipo y el ancho quedan registrados. Los nombres que colisionan con LINE o FIDUCIAL reciben un nombre de columna reversible registrado en archive_field.

Cada fila conserva el índice de muestra original dentro de su línea. FIDUCIAL procede del canal X o, si falta, del primer canal legible; su referencia queda identificada. gdb_channel_lines conserva inicio, incremento y longitud de cada par línea/canal. Una longitud menor produce relleno nulo identificable mediante esa tabla. No se remuestrea ningún canal ni se presupone que sus fiduciales coinciden. La alineación física exige consultar estos metadatos; las coordenadas con fiduciales diferentes no se deben combinar automáticamente.

archive.json y las tablas del catálogo conservan los diccionarios completos de canales y líneas: nombres, etiquetas/alias, unidades, descripción cuando la API la expone, tipos, formatos, decimales, dimensión, clase, protección, número, tipo, vuelo, fecha, versión y selección. Incluyen database.metadata, el diccionario interno get_gx_metadata, las propiedades públicas de lectura, las coordenadas XYZ, el nombre del CRS, WKT ESRI y JSON GX. El WKT de PROJ se deriva cuando es posible; un fallo de derivación se registra. LINE_DIRECTION, LINE_SPACING y atributos desconocidos permanecen en los diccionarios completos. Los extras se serializan con trazabilidad: geometrías en listas de coordenadas y CRS, arrays NumPy en listas, fechas ISO y tipos desconocidos como tipo y repr. Las conversiones con pérdida se registran y no impiden verificar las muestras; metadata_complete distingue la integridad de los metadatos.

La procedencia incluye SHA-256, tamaño, ruta y fecha de la GDB, fecha de conversión, versiones de geosoft y TerraWorkbench y versión del esquema. Las fuentes se copian a una temporal de lectura y se abren mediante GXDB.open_read_only; los originales nunca se abren con GX. La memoria de conversión corresponde a una línea completa, no a toda la base.

## Verificación y uso

La segunda lectura GX vuelve a obtener cada canal de cada línea. Se comparan dimensiones y fiduciales, posiciones de dummies/nulos, enteros y texto exactos y los bits de cada float válido, incluidos cero con signo y NaN originales. verification.json registra cantidades, diferencias y canales ilegibles con su motivo. Solo el estado verified permite la apertura normal; incomplete y unverified se rechazan. El lector comprueba también el SHA-256 del Parquet. Una excepción durante publicación o cambio de la fuente invalida la conversión.

La CLI acepta un archivo o una carpeta recursiva y continúa ante errores de archivos individuales. Un requerimiento de acceso/licencia detiene el lote. La verificación está activada por defecto; --no-verify deja un resultado explícitamente no verificado.

    python scripts/convert_gdb_archive.py --input SOURCE --output NEW_ARCHIVES --verify

La apertura independiente acepta la carpeta, archive.json, catalog.sqlite o samples.parquet. Python utiliza open_archive del módulo terraworkbench_core.gdb_archive; R, DuckDB y otras herramientas leen directamente el Parquet y SQLite. No se necesita importar Geosoft para abrirlos. attach_archive añade una copia verificada a otro SurveyStore y conserva tipos y metadatos.

QGIS ofrece Convertir a archivo abierto (recomendado) y Abrir copia abierta de levantamiento. La conversión utiliza la carpeta de trabajo del proyecto o una temporal aislada de QGIS. La copia se incorpora mediante el trabajador y las capas de levantamiento existentes. Los GeoPackage derivados son productos de mapa; el catálogo y el Parquet conservan el archivo completo y sus arrays. El CSV heredado se identifica como una exportación con pérdidas.

map_omissions identifica expresamente arrays y canales con fiduciales o longitudes diferentes de la referencia que no se incorporan como atributos de los puntos del GeoPackage. map_columns define los escalares compatibles que utiliza el trabajador existente; los valores omitidos del mapa permanecen íntegros en Parquet. Las discrepancias entre X e Y impiden crear geometría automática.

## Dependencias, términos y límites comprobados

La conversión requiere Windows. El paquete geosoft procede del administrador existente y requirements/base.txt fija la serie 2024.2. El botón Preparar conversión de GDB solicita aprobación antes de descargar el redistribuible completo 2024.2 desde la [publicación oficial de GeosoftInc](https://github.com/GeosoftInc/gxcore/releases/tag/v2024.2). El diálogo muestra origen, tamaño y términos. La descarga ocupa 362.081.059 bytes, aproximadamente 345,3 MiB; su SHA-256 fijado es c2711f043dcf4304493757346ac0bb4492ae345bc51035e18fe2d5c400047e74. Los binarios se extraen únicamente bajo las dependencias del perfil de QGIS, nunca en el repositorio ni en el ZIP del plugin.

La [licencia publicada](https://geosoftgxdev.atlassian.net/wiki/spaces/GD/pages/2359406/License) y la [licencia del repositorio de la versión](https://github.com/GeosoftInc/gxcore/blob/v2024.2/LICENSE) permiten redistribución con conservación de copyright, condiciones y exención de garantías. La [documentación de redistribución autónoma](https://geosoftgxdev.atlassian.net/wiki/spaces/GXD20212/pages/2479587994) contempla un ZIP sin instalación de Desktop. Esa autorización no elimina las restricciones de funciones comerciales ni los [términos de terceros](https://geosoftgxdev.atlassian.net/wiki/spaces/GD/pages/2359438/Third-Party+Licenses). La descarga conserva esos avisos junto a los recursos. Las bibliotecas nativas no se presentan como código GPL ni se incluyen en la distribución del plugin.

En la ruta gestionada, la API recibe redist_override y directorios propios de usuario y temporales. Esto selecciona el redist sin usar las DLL de Oasis montaj. Connect conserva sus rutas de usuario y el registro normal: no se debe bloquear su descubrimiento al iniciar el contexto. El instalador del plugin no modifica claves del proveedor. El comportamiento interno de GX y los requisitos de una PC limpia no están auditados.

El aviso en inglés, español y portugués aparece antes de iniciar el lector y permite No volver a mostrar. Puede aparecer una ventana de checkout de licencia; TerraWorkbench no la controla ni acepta licencias. En la cuenta de organización probada, rechazar ese checkout devolvió cero canales y líneas; aceptarlo permitió la conversión verificada. No se debe interpretar GXSYS.is_signed_in como una prueba concluyente del estado de la cuenta en Connect ni como un requisito para intentar lectura: se deja que GXDB.open_read_only comunique el acceso real. Si faltan canales o líneas se conserva una salida incompleta, nunca una conversión verificada.

## Public runtime checksum

The plugin bundles assets/runtime/SHA256SUMS in the standard sha256sum format:
an unchanged hexadecimal SHA-256, two spaces and the official archive filename.
This public integrity value is a resource, not a credential. The loader requires
exactly 64 lowercase hexadecimal characters and the expected filename; missing
or invalid resources stop setup. Download size and full SHA-256 verification
still precede extraction. No scanner rule, baseline or inline suppression is used.

The QGIS scanner documentation does not confirm inline allowlist pragmas:
[supported scanner configuration](https://plugins.qgis.org/docs/security-scanning/config-files).
The normal file scan in
[detect-secrets 1.5.0](https://github.com/Yelp/detect-secrets/blob/v1.5.0/detect_secrets/plugins/high_entropy_strings.py)
checks quoted high-entropy strings. Keeping a public checksum in its conventional
resource format avoids treating it as a source-code credential without hiding,
splitting or encoding the value. The resource is scanned along with the ZIP.


El paquete completo incluye las DLL seequent.evo.client que faltan en el mínimo de 2024.2. Sus componentes administrados requieren Microsoft.NETCore.App y Microsoft.WindowsDesktop.App 6.0; .NET 8 o 10 no los sustituyen. La preparación detecta ambos frameworks en DOTNET_ROOT_X64, DOTNET_ROOT y Program Files. Si faltan, una sola confirmación incluye los componentes pendientes. Descarga 69.372.937 bytes (unos 66 MiB) de Microsoft, verifica los SHA-512 oficiales y prepara .NET 6.0.36 x64 portable en el perfil de QGIS. El entorno de GX recibe DOTNET_ROOT, DOTNET_ROOT_X64 y DOTNET_MULTILEVEL_LOOKUP=0. La comprobación de geodist.dll se ejecuta en un proceso hijo. En la prueba real se usó una instalación portable preparada aparte y expuesta mediante DOTNET_ROOT. Microsoft ya retiró el soporte de .NET 6. El runtime 2026.1 usa .NET 8, pero corresponde a geosoft 2026.1 y exige cambiar la serie del SDK; se conserva la pareja 2024.2.

La migración conserva la instalación anterior, extrae la nueva en otra carpeta y reemplaza installed.json de forma atómica. Solo se ofrece borrar la carpeta anterior después de la preparación, con confirmación explícita; cancelar conserva los archivos. El ZIP temporal descargado por el instalador se elimina después de verificarlo y extraerlo; un archivo proporcionado al comando se conserva.

Antes de cargar GX se crea o repara GeosoftRedist/geosoft.redist, sin reinstalar un runtime válido. Contiene dos rutas absolutas sin comillas, en UTF-8 sin BOM y con CRLF en ambas líneas: las carpetas persistentes _gx_runtime/user y _gx_runtime/temp de las dependencias del perfil. Ambas se crean y se comprueba su escritura antes de crear el contexto. Esto evita el error modal de GX causado por la configuración ausente. La conversión no automatiza Seequent ID ni reserva licencias.

La conversión directa de GDB admite una cuenta Seequent ID gratuita. Antes de descargar se busca Geosoft Connect o Seequent Connector en sus rutas habituales, sin ejecutarlos. Si no se encuentran, no se descarga nada: se explican Seequent Connect y la cuenta Seequent ID gratuita, .NET 6 y los enlaces oficiales. Encontrar el ejecutable no demuestra que la autenticación funcione. Si existe un Oasis montaj con su Python integrado, se conserva el puente antiguo como primera opción; el runtime gestionado es la alternativa cuando no está disponible.

Para trabajar sin una cuenta Seequent, importar un XYZ o CSV ya disponible. Estos formatos también se pueden exportar desde Oasis montaj o desde [Geosoft Viewer gratuito](https://www.seequent.com/products-solutions/geosoft-viewer/) para luego importarlos en TerraWorkbench. La documentación oficial de [Seequent ID y Connector](https://www.seequent.com/help-support/seequent-id/) explica el acceso externo. El plugin no instala Connect ni modifica el .NET del sistema y no automatiza ninguna ventana de identidad ni de licencia.

El proceso hijo de conversión alinea su carpeta de trabajo, TEMP y TMP con la carpeta temporal indicada en geosoft.redist antes de crear GXpy. gxpy usa GXSYS.get_path para formar _gx_<id>/meta_…, lo escribe con GXWA y luego lo lee con Python; la coincidencia de directorios evita que las rutas relativas dependan de la carpeta desde la que se lanzó QGIS. El SDK del proveedor no se modifica.

Los metadatos generales o internos que no puedan leerse se conservan como no disponibles, con su error exacto. La conversión puede continuar con canales y líneas; archive.json y verification.json indican metadata_unavailable y metadata_complete=false. verified y data_verified describen la comparación exacta de muestras, no la integridad de metadatos ausentes. No se describe ese caso como una copia completa sin pérdidas. Un error de metadatos de canal, una diferencia de valores o una base sin líneas/canales sigue impidiendo verified=true.

El inventario de nombres obtiene list_channels y list_lines de forma independiente antes de cualquier metadato. El snapshot conserva ambas listas y los errores de cada operación aunque falle la otra. Las propiedades geométricas se conservan mediante un serializador general, sin exclusiones por propiedad. Point y objetos con xyz, pares p0/p1 y conjuntos pp se guardan como listas de coordenadas con el nombre o WKT del CRS disponible. Los arrays NumPy se guardan como listas, las fechas en ISO y cualquier tipo desconocido como un objeto con type y repr. metadata_conversions conserva la ruta de cada campo, el tipo y si hubo pérdida; una conversión desconocida marca metadata_complete=false sin impedir la verificación de canales y muestras. Los recuentos del inventario se registran antes de serializar para que un error posterior no aparezca como una base vacía.

En gxpy 2024.2, Entitled corresponde a check_intrinsic(100, "Oasis Montaj"). La lectura con una cuenta Seequent ID gratuita sin organización devolvió Entitled=false y produjo una copia verificada y con metadatos completos de Mount Polley.gdb: 32 canales, 51 líneas y 31.127 muestras sin diferencias. Se usó GX 2024.2 completo con .NET 6 portable, sin cargar DLL de Oasis Desktop. El contexto GX se cerró y la GDB conservó su SHA-256. Con una cuenta de organización, cancelar el checkout dejó el inventario sin canales. Aceptar While app is running permitió verificar la copia y el cierre de GX liberó la reserva.

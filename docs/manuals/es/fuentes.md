# Fuentes, versiones y política de citas

[English](../en/fuentes.md) · [Español](../es/fuentes.md) · [Português](../pt/fuentes.md)

[Índice del manual](README.md)

## Prioridad de fuentes

La descripción de una capacidad de TerraWorkbench se contrasta primero con su implementación y contrato. Las referencias metodológicas explican el contexto; las campañas enlazadas describen qué se probó. No se atribuyen al Core todas las capacidades de una dependencia ni se convierte una referencia general en validación independiente del código.

Las firmas se extraen de los módulos Python y los IDs de Core de su registro. El inventario incluye hashes normalizados a LF para poder verificar la misma fuente en Windows y Linux. El catálogo QGIS procede de un proveedor realmente registrado, con su versión de runtime declarada.

Las definiciones que no tenían docstring cuentan con notas editoriales en docs/reference/api/notes/es.json, separadas de las descripciones originales. La referencia muestra también los campos anotados de las clases de opciones. Los SVG se verifican como texto normalizado a LF y los PNG como bytes exactos; así los cambios de finales de línea de Git no se confunden con alteraciones gráficas.

## Referencias primarias consultadas para esta edición

Consulta documental: 6 de noviembre de 2026. Los enlaces latest/stable pueden cambiar de contenido; para reproducir una operación importan además las versiones guardadas por la ejecución.

| Referencia | Uso en el manual | Alcance |
| --- | --- | --- |
| [GDAL: raster data model](https://gdal.org/en/stable/user/raster_data_model.html) | Georreferenciación, bandas y máscaras | Contrato de raster; no valida un importador local completo |
| [PROJ: geodetic transformation](https://proj.org/en/stable/usage/transformation.html) | Diferencia entre proyección y transformación de datum | Contexto geodésico; no certifica alturas privadas |
| [SciPy: sosfiltfilt](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html) | Filtrado forward/backward y extensión de bordes | Operador de biblioteca; no decide cortes científicos |
| [Harmonica: prism_gravity](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html) | Prismas, componentes y unidades | Contrato del motor físico |
| [IAGA / NOAA: IGRF](https://www.ncei.noaa.gov/products/international-geomagnetic-reference-field) | Campo principal y generación de coeficientes | Modelo principal; no anomalías locales |
| [SimPEG](https://simpeg.xyz/) | Marco de simulación e inversión | Capacidades de la biblioteca, distintas de las adaptadas por TerraWorkbench |
| [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf) | Contexto de espectrometría gamma y calibración | Guía metodológica, no una calibración instrumental universal |

La bibliografía específica de Euler, Werner, SPI, micronivelación, flexura, fase, registros y formas de onda de IP se conserva en las guías especializadas enlazadas desde cada capítulo. El [manifiesto del manual práctico](../../handbook/handbook_sources.json) relaciona sus fichas con sus fuentes. Esas entradas históricas no se presentan aquí como una nueva auditoría de todos sus contenidos o licencias.

## Evidencia y resultados

Las figuras conceptuales, los controles artificiales, las capturas de la GUI con datos sintéticos, las pruebas de contratos y los benchmarks físicos se identifican por separado. Cada cifra científica debe llevar a su resultado y criterio de aceptación. Las capturas públicas muestran widgets reales con ejemplos artificiales CC0 incluidos, no un levantamiento de campo, una validación geológica ni una nueva inversión.

La [carpeta de benchmarks](../../validation/records/README.md) conserva tanto logros como limitaciones. Antes de citar un resultado, leer el protocolo, la fecha, el hash de fuente, la definición de error y si la geometría estaba fijada. Una prueba de precisión del solver, una de ajuste de datos y una de recuperación responden preguntas distintas.

## Cómo mantener la documentación

Agregar un módulo requiere asignarlo a un capítulo en docs/manuals/_meta/coverage.json y regenerar la referencia. Si cambia una firma o el registro, la comprobación --check debe detectar documentación desactualizada. Actualizar los ejemplos afectados y declarar qué se volvió a ejecutar. No reemplazar conteos históricos de campañas como si se hubieran recalculado con la nueva fuente.

El manual completo tiene 28 capítulos en español, inglés y portugués, accesibles también desde el lector de la GUI. El manifiesto de localización vincula cada traducción con los hashes de su fuente. Los docstrings técnicos originales y los informes históricos conservan su idioma original; se traducen las notas editoriales y la navegación. El manual práctico resumido tiene una fuente independiente, ui/knowledge_content.py, y su exportador mantiene su propia verificación de paridad EN/ES/PT.

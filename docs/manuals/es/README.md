# TerraWorkbench: manual completo por capítulos

[English](../en/README.md) · [Español](../es/README.md) · [Português](../pt/README.md)

Edición en español · revisión del 6 de noviembre de 2026.

Este manual desarrolla desde cero los conceptos, procedimientos, contratos y límites de los módulos disponibles. Complementa el manual práctico EN/ES/PT de la interfaz y las campañas científicas existentes. La documentación no equivale a nuevas pruebas de campo ni declara resuelta toda la geofísica.

## Cómo usarlo

Seguir los capítulos en orden para aprender el entorno, o consultar una disciplina y volver a las convenciones compartidas. Los capítulos 15 a 17 distinguen modelo, ajuste, convergencia y recuperación. Las APIs experimentales y las integraciones especializadas pendientes se señalan en contexto.

Las firmas exhaustivas se generan desde el código. Los docstrings originales conservan su idioma técnico; las notas editoriales, títulos y navegación tienen versión ES/EN/PT. Los IDs, nombres de canales, claves y ecuaciones no cambian al traducir.

## Capítulos

| # | Tema |
| ---: | --- |
| 01 | [Qué es TerraWorkbench y cómo empezar](01_inicio.md) |
| 02 | [Instalación, dependencias y entorno](02_instalacion.md) |
| 03 | [Coordenadas, unidades, alturas y convenciones](03_coordenadas.md) |
| 04 | [Importación de texto, GRD y datos geoespaciales](04_importacion.md) |
| 05 | [Workspaces, canales, versiones y linaje](05_bases_canales.md) |
| 06 | [QC, trayectoria, tiempos y correcciones de adquisición](06_perfiles_qc.md) |
| 07 | [Cruces, nivelación e interpolación](07_nivelacion_gridding.md) |
| 08 | [Filtros espaciales, máscaras y mosaicos](08_filtros_espaciales.md) |
| 09 | [FFT, continuación, derivadas y análisis espectral](09_fft_espectros.md) |
| 10 | [Magnetometría, campo principal y fuentes compactas](10_magnetometria.md) |
| 11 | [Gravimetría terrestre, redes y modelos 2D](11_gravimetria.md) |
| 12 | [Terreno, isostasia, flexura y tensores](12_terreno_isostasia.md) |
| 13 | [Radiometría gamma, espectros y radón](13_radiometria.md) |
| 14 | [Atributos estructurales y profundidad de fuentes](14_estructura_profundidad.md) |
| 15 | [Modelado e inversión de gravedad y susceptibilidad](15_inversion_potencial.md) |
| 16 | [MVI, inversión conjunta y supuestos estructurales](16_mvi_conjunta.md) |
| 17 | [Convergencia, resolución, incertidumbre y validación](17_resolucion_incertidumbre.md) |
| 18 | [Resistividad DC, geometría ABMN y PDE](18_electrica_dc.md) |
| 19 | [IP, SIP, Cole–Cole e historial de corriente](19_ip_sip.md) |
| 20 | [FDEM, TEM, transitorios y magnetotelúrica](20_em_mt.md) |
| 21 | [Potencial espontáneo y redes de referencia](21_potencial_espontaneo.md) |
| 22 | [GPR, sísmica, procesamiento de trazas y sondeos](22_ondas_sondeos.md) |
| 23 | [Integración multifuente y métodos experimentales](23_integracion_experimentos.md) |
| 24 | [Interfaz QGIS, formularios, idiomas y capturas](24_gui_qgis.md) |
| 25 | [API Python, trabajos y workflows reproducibles](25_api_workflows.md) |
| 26 | [Recursos, pruebas, empaquetado y mantenimiento](26_recursos_desarrollo.md) |
| 27 | [Tutoriales reproducibles desde cero](27_tutoriales.md) |
| 28 | [Evidencia científica, capítulos de resultados y publicación](28_evidencia_publicacion.md) |

## Referencias y material de apoyo

- [Referencia de API](../../reference/api/es.md)
- [Inventario estructurado](../../reference/api/core_inventory.json)
- [Notas editoriales de API](../../reference/api/notes/es.json)
- [Catálogo QGIS](../../reference/catalogues/qgis_es.md)
- [Fuentes y política de citas](fuentes.md)
- [Ejemplos ejecutados](../_meta/examples.json)
- [Capturas reales de Canadá](../_meta/captures.json)
- [Índice general](../../README.md)
- [Manual práctico](../../handbook/handbook_es.md)

## Imágenes y reproducibilidad

Las figuras usan enlaces relativos a recursos del idioma: dos diagramas conceptuales, dos demostraciones numéricas controladas y dos capturas reales, del workspace sintético incluido y del lector de capítulos. Estas imágenes no redistribuyen un levantamiento real. Los scripts y ejemplos se conservan en el repositorio; Matplotlib se declara en el extra documentation.

Para leer basta el árbol documental; los enlaces a código requieren el checkout completo. No se generan PDF. Los informes históricos se conservan en el idioma original y con sus métricas y fechas intactas.

## Qué significa completo

Todos los módulos Python de terraworkbench_core tienen capítulo en la cobertura compartida. Las tres ediciones tienen los mismos 28 IDs, secciones, tablas y enlaces técnicos, comprobados por un manifiesto de paridad. Esto verifica cobertura documental y correspondencia estructural, no validación científica universal ni estabilidad de toda función.

La evidencia de cada área se evalúa con contratos, referencias, pruebas y resultados. Fechas y conteos históricos no certifican una revisión posterior.

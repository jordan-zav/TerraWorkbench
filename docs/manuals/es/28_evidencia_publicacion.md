# 28. Evidencia científica, capítulos de resultados y publicación

[English](../en/28_evidencia_publicacion.md) · [Español](../es/28_evidencia_publicacion.md) · [Português](../pt/28_evidencia_publicacion.md)

## Escribir un resultado que se pueda verificar

Un artículo debe describir observaciones, metadatos, transformaciones, parámetros, fuentes de incertidumbre y criterios de aceptación. Conservar nombres de magnitudes, unidades, signos, fuentes de coeficientes y límites del modelo. Citar una librería indica qué se usó; no demuestra que su integración local sea correcta.

La estructura recomendada es resumen, introducción, datos y métodos, resultados, discusión, conclusiones, disponibilidad y referencias. En un manual, cada capítulo tiene su objetivo y procedimiento; en un estudio, esos procedimientos deben convertirse en la receta efectivamente ejecutada.

## Conteos y separación de conjuntos

Informar por separado filas disponibles, válidas, seleccionadas, ajustadas y reservadas. Una base grande importada no demuestra que se invirtieron todos sus puntos. Reservar líneas o regiones antes de seleccionar regularización y malla. No anunciar como independiente una comparación que reutiliza el mismo operador de forward en ambos lados.

## Evidencia existente del proyecto

El repositorio conserva campañas públicas de procesamiento, inversiones, extensiones y recuperación. Consultar fecha, hash de fuente, datos y criterio de cada una. Los ensayos de radón conservan problemas de calibración y residuos; los de voxeles libres conservan errores de modelo elevados en algunas geometrías. Los fallos son parte de la evidencia, no filas que se eliminan para mejorar el resumen.

| Pregunta | Documento de partida |
| --- | --- |
| Procesamiento con datos externos | [Campaña pública](../../validation/reports/public_processing_benchmark.md) |
| Reproducción de inversión pública | [Benchmark de inversión](../../validation/reports/public_inversion_benchmark.md) |
| Solver y no unicidad | [Convergencia](../../validation/reports/inversion_convergence_resolution.md) |
| Recuperación condicionada y libre | [Protocolo voxel](../../validation/reports/voxel_recovery_validation.md) |
| Métodos eléctricos, EM y SP | [Validación de métodos](../../validation/reports/inversion_methods_validation.md) |
| MVI y direcciones | [Referencias](../../validation/reports/mvi_reference_validation.md), [aceptación](../../validation/reports/mvi_acceptance.md) |
| Archivos de métricas | [Índice de benchmarks](../../validation/records/README.md) |

## Figuras y tablas

Generar figuras desde artefactos guardados, conservar el script y declarar semilla en datos artificiales. Diferenciar mapa de puntos, grilla interpolada, sección de modelo, diagrama conceptual y captura de GUI. Cada figura necesita leyenda, unidades y soporte. Si se limita la escala de color, indicarlo; un residual recortado puede ocultar valores extremos.

Los artículos se conservan en Markdown con imágenes enlazadas y tablas de parámetros y métricas. No generar PDF como paso automático. Verificar enlaces, fuentes y que las capturas correspondan a una ejecución real.

## Licencias, datos y responsabilidad

La licencia del software no otorga derechos sobre datasets o informes de terceros. Una descarga pública puede tener condiciones propias. Antes de publicar, revisar licencia, atribución, identificadores, integridad y posibilidad de redistribuir bytes o solo la receta de descarga.

Mantener adquisiciones privadas, rutas personales, credenciales, informes internos e imágenes de sitios fuera del repositorio público. Usar ejemplos artificiales para enseñar la interfaz. Autoría, afiliación, financiación y declaraciones de conflicto corresponden a quienes publican el estudio y deben confirmarse, no inferirse del usuario de Git.

Las próximas capacidades y benchmarks se registran como pendientes hasta ejecutarse. Un backlog es una propuesta de trabajo, no una lista de funcionalidades completadas. Ver [cobertura histórica](../../handbook/roadmap_cobertura.md), [licencias](../../legal/THIRD_PARTY_LICENSES.md) y [fuentes del manual](fuentes.md).

---

[Índice](README.md) · [Anterior](27_tutoriales.md)

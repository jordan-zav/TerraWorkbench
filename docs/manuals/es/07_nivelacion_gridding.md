# 7. Cruces, nivelación e interpolación

[English](../en/07_nivelacion_gridding.md) · [Español](../es/07_nivelacion_gridding.md) · [Português](../pt/07_nivelacion_gridding.md)

## Orden del procesamiento

La nivelación intenta reducir diferencias entre líneas de un levantamiento ya corregido en tiempo y adquisición. El gridding estima un campo sobre una malla; no arregla por sí mismo errores de lag, estación base o altura. Revisar primero la geometría de líneas, la calidad de cruces y su conectividad.

En un cruce, la diferencia entre observaciones comparables restringe correcciones relativas. Una red desconectada o sin ancla no define un datum absoluto. Los ajustes robustos constantes o polinómicos reducen la influencia de algunos residuos, pero el grado y las líneas aceptadas siguen siendo decisiones del usuario. Registrar cruces rechazados, correcciones estimadas y residuos por línea.

## Elección de interpolador

| Método | Qué controla el resultado | Precaución |
| --- | --- | --- |
| Vecino más cercano | Distribución de puntos | Discontinuidad entre dominios de vecinos |
| IDW | Potencia, vecinos, radio | Alta densidad de línea puede dominar |
| TPS global | Suavidad y soporte completo | Coste de sistema denso |
| TPS local | Vecindario y suavidad | No equivale al ajuste global |
| Mínima curvatura experimental | Malla, iteración y convergencia | Verificar residuos y límites; no asumir equivalencia propietaria |
| Sinc | Muestreo y soporte | No recupera detalle no adquirido |
| Kriging ordinario | Variograma, vecinos, nugget | Modelo estadístico debe justificarse |
| Fuentes equivalentes | Profundidad de fuentes y damping | Problema físico regularizado, no interpolación neutra |

Reducir el tamaño de celda puede mejorar la representación visual sin aumentar resolución física. Definir extensión, origen y celda antes de comparar productos. Para una comparación numérica, las dos grillas necesitan exactamente el mismo lattice o un remuestreo documentado.

## Validación espacial

Reservar bloques o líneas antes de seleccionar parámetros del interpolador. Medir error en puntos no usados y observar su localización; un RMS global puede ocultar extrapolación mala en bordes. La validación aleatoria entre puntos muy cercanos de la misma línea puede ser excesivamente favorable.

Un variograma empírico depende de distancia, bins, tendencia, pares disponibles y anisotropía. Un modelo de variograma no convierte el kriging variance en incertidumbre total de adquisición o de interpretación. Las fuentes equivalentes necesitan fuentes separadas de los receptores, unidades y superficie de predicción explícitas.

## Micronivelación

Se usa después de correcciones principales y nivelación de cruces, para tratar corrugación direccional residual. Comparar la corrección retirada con la amplitud y orientación de estructuras reales. Cambiar azimut, cutoff o máscara puede modificar la señal geológica, especialmente si es paralela al vuelo.

Las correcciones por línea, superficie aplicada y producto final deben conservarse como salidas distintas. Un aspecto más suave no es un criterio suficiente de aceptación.

Detalles en [interpolación](../../reference/methods/interpolation_methods.md), [pipeline básico](../../guides/basic_processing_migration.md), [fuentes equivalentes y métodos](../../research/core_expansion_implementation.md) y [extensiones de geostatística](../../validation/reports/2d_extensions.md).

## Implementación relacionada

[line_processing](../../../terraworkbench_core/line_processing.py), [gridding_methods](../../../terraworkbench_core/gridding_methods.py), [survey_processing](../../../terraworkbench_core/survey_processing.py), [survey_grid_pipeline](../../../terraworkbench_core/survey_grid_pipeline.py), [equivalent_sources](../../../terraworkbench_core/equivalent_sources.py), [geostatistics](../../../terraworkbench_core/geostatistics.py)

---

[Índice](README.md) · [Anterior](06_perfiles_qc.md) · [Siguiente](08_filtros_espaciales.md)

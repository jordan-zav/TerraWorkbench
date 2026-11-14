# 7. Cruces, nivelación e interpolación

[English](../en/07_nivelacion_gridding.md) · [Español](../es/07_nivelacion_gridding.md) · [Português](../pt/07_nivelacion_gridding.md)

Cuando la solicitud supera el límite, use el tamaño de celda sugerido o reduzca la extensión. El diálogo de Processing ofrece **Continuar solo esta vez**. Para autorizar explícitamente una ejecución desde el formulario, un modelo o un lote, active **Permitir grillas grandes de mínima curvatura** en Parámetros avanzados. Las grillas grandes pueden requerir mucha más memoria y tiempo.

## Orden del procesamiento

La nivelación intenta reducir diferencias entre líneas de un levantamiento ya corregido en tiempo y adquisición. El gridding estima un campo sobre una malla; no arregla por sí mismo errores de lag, estación base o altura. Revisar primero la geometría de líneas, la calidad de cruces y su conectividad.

En un cruce, la diferencia entre observaciones comparables restringe correcciones relativas. Una red desconectada o sin ancla no define un datum absoluto. Los ajustes robustos constantes o polinómicos reducen la influencia de algunos residuos, pero el grado y las líneas aceptadas siguen siendo decisiones del usuario. Registrar cruces rechazados, correcciones estimadas y residuos por línea.

## Validación cuantitativa de la interpolación

En un vuelo sintético de cinco millones de observaciones sobre 100 líneas, la grilla de 159 197 celdas a 25 m presentó un RMS de 0,000355 para la mínima curvatura con tensión 0,1 y de 0,000282 para el bidireccional PCHIP, en unidades del campo analítico. Los cálculos tomaron 35,2 y 2,25 s respectivamente, con picos de memoria de proceso de 412,5 y 389,7 MiB. Se midió una geometría regular, con los datos ya en memoria y sin contabilizar la exportación del raster. El error transversal dependiente de la fase de vuelo siguió siendo medible.

El solver multinivel tiene un límite predeterminado de 500 000 nodos de trabajo, incluidos los márgenes. Una extensión cuadrada de 50 km a 25 m requiere 4 020 025 nodos. El programa informa el límite y sugiere una celda de al menos 71,5 m para esa extensión. La comparación externa queda pendiente de autorización para divulgar resultados. [Briggs (1974)](https://doi.org/10.1190/1.1440410) · [Smith y Wessel (1990)](https://doi.org/10.1190/1.1442837)

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

## Gridding de líneas de vuelo

En Processing, abra **Interpolar puntos de levantamiento a GeoTIFF**. Seleccione un canal numérico, un SRC proyectado y, para el método bidireccional, el campo que identifica las líneas de producción. Excluya líneas de amarre, giros y líneas de orientación incompatible. Con identificadores de línea y celda automática, el tamaño se calcula dividiendo la mediana del espaciado transversal por 4 o 5. Sin el campo de línea, se usa la densidad de puntos.

El método bidireccional interpola linealmente a lo largo de cada perfil y luego entre perfiles con interpolación lineal o cúbica PCHIP. La tendencia opcional ajusta un plano, interpola los residuos y repone el plano. Los límites de hueco longitudinal y transversal evitan puentes sobre tramos sin soporte. Para líneas oblicuas, se remuestrea la malla alineada al vuelo sobre los ejes del SRC.

La mínima curvatura con tensión usa restricciones fuera de nodo de Briggs, refinamiento grueso a fino y condiciones naturales discretas en el borde. Revise los metadatos de convergencia del GeoTIFF. Desactive el promedio por celda para seleccionar directamente la observación más próxima a cada nodo en cada nivel cuando la densidad a lo largo del vuelo es alta.

Los valores nulos y no finitos se excluyen. Indique un valor nulo numérico si el canal usa un código finito. Combine una distancia máxima con el polígono **survey_boundary** generado por el mapa del levantamiento para asignar NoData fuera del soporte. El polígono conserva islas y huecos y se transforma al SRC de salida. El límite de distancia se mide desde el centro de celda a las observaciones válidas.

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

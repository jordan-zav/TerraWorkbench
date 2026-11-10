# 8. Filtros espaciales, máscaras y mosaicos

[English](../en/08_filtros_espaciales.md) · [Español](../es/08_filtros_espaciales.md) · [Português](../pt/08_filtros_espaciales.md)

## Dominio espacial frente a frecuencia

Un filtro espacial opera sobre vecindarios del raster; un filtro FFT aplica una transferencia espectral. Algunos filtros lineales tienen representaciones relacionadas en ambos dominios, pero una mediana es no lineal y no se describe mediante una transferencia Fourier única. La mediana circular 2D y la mediana sobre un canal 1D son herramientas distintas.

smooth_nine_point y smooth_least_squares_9x9 implementan suavizados locales diferentes. circular_median utiliza soporte circular y su tamaño debe expresarse conforme al contrato de la API o formulario. automatic_gain_control ajusta contraste local: su salida realzada no mantiene necesariamente la amplitud original de una anomalía para estimar propiedades físicas.

## Procedimiento recomendado

1. Revisar resolución, orientación y máscara del raster.
2. Elegir un radio o ventana coherente con el muestreo y el objetivo.
3. Guardar una salida nueva y la receta, sin reemplazar la entrada.
4. Calcular diferencia entrada–salida y comparar estadísticas dentro de soporte común.
5. Revisar bordes y anomalías estrechas, incluso cuando la imagen final parezca más limpia.

El tratamiento de vecinos faltantes debe ser el de la operación concreta. No rellenar NoData con cero antes de una mediana sin documentarlo. Para comparar productos, evitar que la máscara diferente de cada filtro cambie silenciosamente las observaciones que entran en el RMS.

## Filtrado direccional y wavelets

grid_tools contiene herramientas direccionales, mosaicos y filtrado direccional wavelet. Registrar azimut, escalas, familia wavelet, extensión de bordes y valores de ganancia. Un filtrado de textura de vuelo no identifica automáticamente ruido: la geología puede compartir su orientación.

El mosaico debe resolver explícitamente superposición, precedencia, lattice, CRS y ausencias. No combinar productos con amplitudes incompatibles como si fueran observaciones equivalentes. Una costura suave puede ocultar una diferencia de datum.

## Qué revisar en una salida

Medir rango, media, dispersión, fracción finita y amplitud retirada. Comparar perfiles que crucen rasgos a varias orientaciones. Si el filtro cambia unidades o normaliza amplitudes, indicarlo en el canal y en la leyenda. Separar una imagen para exploración de la señal usada en modelado.

Para parámetros exactos consultar la [referencia de API](../../reference/api/es.md), el [catálogo del proveedor](../../reference/catalogues/qgis.md) y [las advertencias del manual práctico](../../handbook/handbook_es.md).

## Implementación relacionada

[basic_processing](../../../terraworkbench_core/basic_processing.py), [grid_tools](../../../terraworkbench_core/grid_tools.py)

---

[Índice](README.md) · [Anterior](07_nivelacion_gridding.md) · [Siguiente](09_fft_espectros.md)

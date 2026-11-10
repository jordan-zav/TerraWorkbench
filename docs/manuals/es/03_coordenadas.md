# 3. Coordenadas, unidades, alturas y convenciones

[English](../en/03_coordenadas.md) · [Español](../es/03_coordenadas.md) · [Português](../pt/03_coordenadas.md)

## Contrato espacial

Antes de una operación de distancia o Fourier se necesitan unidades horizontales conocidas. Un número como 500000 no identifica por sí solo una zona UTM ni un datum. Asignar SRC documenta el significado de coordenadas existentes; reproyectar calcula otras coordenadas. Cambiar la etiqueta del SRC no repara una transformación equivocada.

La API reproject_xy admite SRC horizontales 2D, orden XY explícito y rechazo de transformaciones aproximadas no autorizadas. No transforma elevaciones. Si la mejor operación requiere rejillas de datum ausentes, investigar el problema en lugar de aceptar otra operación silenciosamente. El adaptador QGIS conserva su propio contexto de transformación.

## Alturas que no se deben intercambiar

| Cantidad | Uso típico | Precaución |
| --- | --- | --- |
| Elevación elipsoidal | Posición GNSS | No equivale a altura ortométrica |
| Elevación ortométrica | Terreno respecto al geoide | Registrar modelo de geoide |
| Altura sobre terreno | Separación sensor–suelo | Necesita posición del sensor y DEM compatibles |
| Elevación del sensor | Coordenada Z del receptor | Puede diferir de antena o plataforma |
| Separación entre sensores | Gradientes o pares | No sustituye a una elevación absoluta |

Un sensor remolcado puede tener desplazamiento vertical y horizontal. Una altura nominal documenta una aproximación, no una medición de su trayectoria. Mantener DEM, topografía y receptor en un marco vertical compatible.

## Convenciones físicas

El Core utiliza con frecuencia Este, Norte y Arriba. Sin embargo, los signos de una componente dependen de la API: el motor de inversión gravimétrica permite up o down, el polígono gravimétrico devuelve componente hacia abajo y el tensor MT utiliza ejes horizontales Norte/Este. Consultar el contrato del módulo, no inferirlo del gráfico.

Para campo magnético, inclinación positiva hacia abajo y declinación desde el norte verdadero no siempre son los ángulos de una malla proyectada. Si corresponde, utilizar D_grilla = D_verdadera − convergencia meridiana y comprobar el signo proyectando un rumbo conocido.

| Conversión | Relación |
| --- | --- |
| Gravedad | 1 mGal = 10⁻⁵ m/s² |
| Gradiente de gravedad | 1 Eötvös = 10⁻⁹ s⁻² |
| Campo magnético | 1 nT = 10⁻⁹ T |
| Densidad | 1 g/cm³ = 1.000 kg/m³ |
| Susceptibilidad | SI, adimensional |
| Cargabilidad | V/V; distinguir de mV/V |

## Raster, máscaras y píxeles

Comprobar tamaño, transformación afín, orientación de filas, centros de píxel y NoData. Un raster norte-arriba suele tener paso Y geográfico negativo aunque la distancia entre filas sea positiva. Las funciones FFT reciben distancias de muestreo; la orientación física de los ejes se debe resolver antes.

Mantener cero como dato válido cuando corresponda. NaN y máscara no significan amplitud nula. Revisar también escala y offset de las bandas para evitar aplicar el filtro a enteros almacenados en lugar de magnitudes físicas.

Fuentes: [modelo raster GDAL](https://gdal.org/en/stable/user/raster_data_model.html), [transformaciones PROJ](https://proj.org/en/stable/usage/transformation.html) y [contrato independiente de coordenadas](../../development/standalone_acquisition.md).

## Implementación relacionada

[coordinates](../../../terraworkbench_core/coordinates.py)

---

[Índice](README.md) · [Anterior](02_instalacion.md) · [Siguiente](04_importacion.md)

# 10. Magnetometría, campo principal y fuentes compactas

[English](../en/10_magnetometria.md) · [Español](../es/10_magnetometria.md) · [Português](../pt/10_magnetometria.md)

## Identificar la magnitud de entrada

Campo total, anomalía residual al IGRF y diferencia entre sensores no son intercambiables. Si la entrada ya es una anomalía, restar de nuevo el campo principal introduce un error de magnitud. Registrar también estación base, fecha y correcciones previas. Un nombre comercial o histórico del canal no describe necesariamente su contenido actual.

igrf_field calcula componentes Este, Norte y Arriba, campo total y elementos angulares mediante ppigrf. Las entradas son longitud, latitud geodética, altura en kilómetros y fecha válida para los coeficientes instalados. El Core registra archivo, hash y rango de épocas. No reproyecta coordenadas ni convierte datum vertical automáticamente. [IGRF es un modelo del campo principal](https://www.ncei.noaa.gov/products/international-geomagnetic-reference-field), no una descripción de anomalías locales.

## RTP, RTE y componentes

Por defecto, RTP conserva la media de entrada sobre las celdas válidas. Se puede elegir una salida de media cero. En la cadena magnética, la elección afecta a la grilla RTP publicada; las derivadas y los demás productos siguen usando la misma superficie de cálculo.

La reducción al polo o ecuador transforma una anomalía bajo hipótesis sobre dirección de campo y magnetización. En presencia de remanencia, una dirección inducida puede ser insuficiente. Cerca de condiciones que producen denominadores pequeños se necesita estabilización; un mapa simétrico no certifica que la transformación sea físicamente correcta.

magnetic_components ofrece transformación entre componentes y reconstrucción de TMI desde gradientes, con direcciones explícitas. La recuperación de modos débiles y del nivel medio necesita las restricciones del método; no asumir que integrar gradientes proporciona un datum absoluto medido. Documentar unidades de gradiente y cualquier componente no observable.

## Productos de realce

| Producto | Qué destaca | Limitación |
| --- | --- | --- |
| Derivadas horizontales y THDR | Variación lateral | Sensibilidad a ruido y orientación |
| Derivada vertical | Contenido de onda corta | Amplifica errores de alta frecuencia |
| Amplitud de señal analítica | Combinación de gradientes | No es susceptibilidad |
| Tilt, theta y TDX | Contrastes y relaciones de gradientes | Inestabilidad donde denominadores son pequeños |
| Pseudogravedad | Transformación bajo modelo de fuente | Requiere hipótesis físicas; no medición gravimétrica |

Las unidades y el restablecimiento de tendencia dependen del producto. Conservar grilla corregida sin realces como referencia para modelado cuantitativo.

## Dipolos y objetos compactos

magnetic_dipole_field y fit_magnetic_dipoles permiten forward y ajuste local de fuentes con posiciones y momentos. Requieren geometría, rango inicial, límites y suficientes observaciones. Un dipolo ajustado no clasifica UXO ni establece por sí solo peligrosidad, material o edad. La aproximación dipolar debe comprobarse frente al tamaño del objeto y distancia del sensor.

Ver [componentes magnéticas](../../reference/methods/magnetic_component_api.md), [fuentes compactas](../../reference/methods/compact_magnetics.md), [contratos de adquisición](../../development/standalone_acquisition.md) y [fuentes del método](../../research/PAPER_BACKED_MAGNETIC_METHODS.md).

## Implementación relacionada

[geomagnetism](../../../terraworkbench_core/geomagnetism.py), [magnetic_components](../../../terraworkbench_core/magnetic_components.py), [magnetic_pipeline](../../../terraworkbench_core/magnetic_pipeline.py), [magnetic_products](../../../terraworkbench_core/magnetic_products.py), [compact_magnetics](../../../terraworkbench_core/compact_magnetics.py)

---

[Índice](README.md) · [Anterior](09_fft_espectros.md) · [Siguiente](11_gravimetria.md)

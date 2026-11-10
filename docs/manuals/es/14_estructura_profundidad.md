# 14. Atributos estructurales y profundidad de fuentes

[English](../en/14_estructura_profundidad.md) · [Español](../es/14_estructura_profundidad.md) · [Português](../pt/14_estructura_profundidad.md)

## Productos matemáticos e interpretación

Gradientes, fase, textura y orientaciones ayudan a explorar contrastes. Un borde calculado no es automáticamente una falla, contacto litológico o cuerpo mineralizado. Registrar escala, filtro previo y máscara permite distinguir una interpretación del resultado numérico que la motivó.

structural_attributes contiene fase monogénica multiescala, textura local y entropía de orientaciones. Las longitudes de onda, ancho de banda, umbral de ruido, rango de valores y origen de bins influyen en el producto. La entropía axial necesita reconocer que orientaciones separadas 180° pueden representar el mismo eje. Una textura de muestreo o vuelo también puede producir orientación dominante.

lineament_geometry convierte esqueletos booleanos en caminos. La máscara, espaciado en metros y origen del primer píxel son explícitos. Las ramificaciones, ciclos y extremos no se deben suavizar o unir sin registrar una nueva operación. La longitud depende de la representación de píxeles y del criterio de conectividad.

## Euler

La ecuación de homogeneidad relaciona derivadas del campo con posición de fuente, fondo e índice estructural. Una forma habitual es:

    (x − x0) Tx + (y − y0) Ty + (z − z0) Tz = N (B − T)

Índice N, tamaño de ventana, derivadas, coordenadas y fondo deben ser compatibles. Una nube de soluciones puede reflejar ruido, mezcla de fuentes o mala condición. euler_window, euler_grid y euler_profile no justifican aceptar todas las soluciones por haber convergido un ajuste lineal.

## Werner y SPI

werner_profile y spi_profile responden a hipótesis de fuentes y geometría de perfil. Revisar modelo de fuente, longitud de ventana, muestreo, altura y bordes. La profundidad estimada con una aproximación de contacto no se interpreta igual que la de una fuente cilíndrica. Las APIs de grilla y de perfil tampoco comparten automáticamente todas sus hipótesis.

## Procedimiento de interpretación

1. Definir la pregunta geológica y el modelo de fuente plausible.
2. Preparar un campo con correcciones y unidades conocidas.
3. Comparar varias escalas o ventanas sin elegir solo la más atractiva.
4. Rechazar soluciones con soporte, rango o condición inadecuados según criterios previos.
5. Comparar con datos independientes, topografía, cartografía y trayectorias.
6. Exportar catálogo de soluciones y parámetros, además de la figura elegida.

Ver [profundidad de fuentes](../../reference/methods/source_depth.md), [atributos estructurales](../../reference/methods/structural_attributes.md) y las referencias específicas conservadas allí. Los catálogos de profundidad son soluciones de un modelo; no representan observaciones directas del basamento.

## Implementación relacionada

[source_depth](../../../terraworkbench_core/source_depth.py), [structural_attributes](../../../terraworkbench_core/structural_attributes.py), [lineament_geometry](../../../terraworkbench_core/lineament_geometry.py)

---

[Índice](README.md) · [Anterior](13_radiometria.md) · [Siguiente](15_inversion_potencial.md)

# 12. Terreno, isostasia, flexura y tensores

[English](../en/12_terreno_isostasia.md) · [Español](../es/12_terreno_isostasia.md) · [Português](../pt/12_terreno_isostasia.md)

## Construir un modelo de terreno defendible

Se necesitan DEM, resolución, extensión, máscara, datum vertical y densidad o contraste de densidad. La topografía finita omite masas fuera del dominio. Un DEM más detallado no siempre produce una corrección más precisa si el receptor está mal localizado o faltan alturas consistentes.

terrain_correction_prisms calcula un término definido como placa menos atracción del DEM finito, con unidades y límites explícitos. El método adaptativo terrain_gravity_adaptive calcula atracción del contraste del DEM en estaciones y combina prismas cercanos con aproximaciones lejanas. No intercambiar sus salidas por semejanza de nombre: verificar si se entrega atracción, corrección o componente de una reducción completa.

## Coste y tolerancia

El método finito histórico puede requerir trabajo cuadrático en el número de celdas. Dividir receptores en bloques reduce temporales, pero no elimina las interacciones físicas. La versión adaptativa permite una aproximación controlada; evaluar tolerancia, radio cercano, máscara y efectos de borde con estaciones de prueba.

Una prueba plana y un prisma conocido ayudan a verificar signo y unidades. Para regiones amplias, revisar también si la geometría plana sigue siendo suficiente. La presencia de una API de prismas no implica que exista una solución regional esférica con terreno multirresolución para cualquier tamaño.

## Isostasia Airy

airy_root_thickness y airy_moho_depth producen geometría de raíz bajo hipótesis de compensación local, densidades y espesor de referencia. isostasy permite calcular su efecto con prismas o FFT. El residual isostático depende del modelo adoptado; no es una eliminación observacionalmente única del campo profundo.

En formulaciones FFT hay periodicidad y tratamiento de bordes. En prismas finitos hay truncamiento espacial. Comparar ambos necesita el mismo soporte, referencia, densidades y signos. Diferencias marginales no prueban por sí solas que una implementación esté equivocada.

## Flexura

thin_plate_flexure calcula respuesta de placa bajo cargas y modelos reológicos explícitos; scan_elastic_thickness explora parámetros. La relación conceptual D ∝ E Te³/(1 − ν²) muestra la sensibilidad a espesor elástico. Una exploración de Te con carga y densidades fijadas no estima simultáneamente toda la estructura litosférica.

## Tensores

prism_gravity_tensor, rotate_tensor y tensor_invariants permiten campos de gradiente y cambios de base. Registrar orden de componentes, sistema ENU, matriz de rotación y unidades Eötvös. Una rotación incorrecta puede conservar algunos invariantes y aun así colocar mal las componentes. Evitar receptores en singularidades del modelo.

Fuentes: [prismas Harmonica](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html), [terreno adaptativo](../../reference/methods/adaptive_terrain.md), [isostasia](../../reference/methods/isostasy.md) y [flexura de referencia GMT](https://docs.generic-mapping-tools.org/6.5/supplements/potential/grdflexure.html).

## Implementación relacionada

[terrain_gravity](../../../terraworkbench_core/terrain_gravity.py), [adaptive_terrain](../../../terraworkbench_core/adaptive_terrain.py), [terrain_tree_walk](../../../terraworkbench_core/terrain_tree_walk.py), [isostasy](../../../terraworkbench_core/isostasy.py), [flexure](../../../terraworkbench_core/flexure.py), [potential_tensors](../../../terraworkbench_core/potential_tensors.py)

---

[Índice](README.md) · [Anterior](11_gravimetria.md) · [Siguiente](13_radiometria.md)

# 16. MVI, inversión conjunta y supuestos estructurales

[English](../en/16_mvi_conjunta.md) · [Español](../es/16_mvi_conjunta.md) · [Português](../pt/16_mvi_conjunta.md)

## Qué cambia respecto a susceptibilidad escalar

MVI permite componentes vectoriales de magnetización efectiva en lugar de fijar su dirección al campo inductor. Incrementa el número de parámetros y la ambigüedad. Una mejora del ajuste puede deberse a mayor flexibilidad; no demuestra que la dirección recuperada sea geológicamente correcta.

La representación cartesiana usa componentes por eje. La esférica separa amplitud y ángulos y añade dificultades en amplitud nula y polos. Al comparar o exportar, revisar si el campo representa susceptibilidad efectiva SI o magnetización A/m; los nombres históricos sin sufijo conservan convenciones de compatibilidad documentadas.

## Controles del solver

La regularización vectorial, por amplitud o por componentes no produce el mismo prior. El esquema esférico dispone de etapa cartesiana y reglas de carta para amplitud cero y polos. No interpretar una azimutal indefinida en un polo como una dirección determinada.

El escalado de amplitud SI y ángulos en radianes afecta el solve interno. Los diagnósticos distinguen residuos CG crudos y escalados. Cumplir uno no implica cumplir el otro. La actualización IRLS adaptativa es la referencia del Core; las estrategias de pesos congelados se conservan como diagnósticos experimentales y pueden agotar presupuestos.

## Inversión conjunta

run_joint_cross_gradient_inversion combina gravedad y magnetismo con una penalización de gradiente cruzado. Favorece relaciones estructurales bajo el peso elegido, pero no exige por sí sola una relación petrofísica única. La ausencia de gradiente en una región también afecta la interpretación del acoplamiento.

Cada dataset necesita sigma, regional, componente y unidades propios. Examinar sus desajustes por separado: una suma baja puede ocultar un conjunto mal explicado. Distinguir criterio de datos, tolerancia CG y criterio externo de cambio de modelo. El hessiano Gauss–Newton del término conjunto y el modo histórico estabilizado conservan diferencias de receta.

## Cómo comunicar el estado actual

Los informes públicos del repositorio incluyen pruebas sintéticas, comparaciones y casos que no cumplen recuperación. No resumirlos como MVI resuelta o inversión 3D cerrada. Los ensayos de cuerpos con geometría conocida y los de voxeles libres responden preguntas diferentes.

Antes de interpretar una solución, comparar modelos iniciales, referencias, pesos estructurales, límites y resolución con un diseño previamente fijado. Mantener reservadas observaciones o geometrías para evaluación final. Los mapas de residuo, dirección y amplitud deben acompañarse de estados de convergencia y límites físicos.

Ver [MVI esférica](../../reference/methods/spherical_mvi.md), [estabilidad](../../validation/reports/mvi_stability.md), [IRLS](../../validation/reports/lagged_irls.md), [sensibilidad externa](../../validation/reports/mvi_outer_sensitivity.md), [aceptación](../../validation/reports/mvi_acceptance.md) y [diagnóstico causal](../../validation/reports/mvi_causal_diagnosis.md).

## Implementación relacionada

[spherical_mvi](../../../terraworkbench_core/spherical_mvi.py)

---

[Índice](README.md) · [Anterior](15_inversion_potencial.md) · [Siguiente](17_resolucion_incertidumbre.md)

# 15. Modelado e inversión de gravedad y susceptibilidad

[English](../en/15_inversion_potencial.md) · [Español](../es/15_inversion_potencial.md) · [Português](../pt/15_inversion_potencial.md)

## Preparar el problema

Una inversión exige observaciones, incertidumbres, coordenadas de receptores, malla, máscara activa y una relación física entre propiedades y respuesta. Las coordenadas se expresan en metros y elevación positiva hacia arriba en el motor potencial. La componente de gravedad debe declararse: up o down. Susceptibilidad usa TMI en nT y propiedad SI; densidad del motor integral se expresa en g/cm³.

No invertir directamente gravedad observada o campo total sin definir qué regional y correcciones corresponden al modelo. regional_prediction se retira en espacio de datos; reference_model regulariza propiedades. Son términos distintos y no se sustituyen uno por otro.

## Objetivo y restricciones

Una formulación de referencia combina desajuste y regularización:

    φ(m) = ‖Wd (F(m) − d)‖² + β φm(m, mref)

Wd depende de desviaciones estándar en unidades de los datos. Usar una sigma arbitraria y luego anunciar que RMS ponderado ≈ 1 certifica ruido instrumental es incorrecto. La regularización, beta, norma y referencia aportan información o preferencias sobre el modelo.

run_potential_field_inversion admite malla construida o suministrada, celdas activas, límites escalares o por celda, modelo inicial y referencia. spatial_property_constraints y build_cell_difference_prior agregan hipótesis explícitas. No derivar restricciones geológicas de la misma anomalía y tratarlas después como evidencia independiente.

## Discretización y memoria

Definir tamaño de celda, profundidad, padding y topografía antes del ajuste. Un receptor dentro de un prisma activo puede producir dificultades físicas o numéricas. La malla debe separar aire y terreno de forma coherente con la representación utilizada.

Para N datos y M parámetros, una sensibilidad densa escalar requiere aproximadamente N × M × bytes_por_elemento. MVI añade tres componentes. Los modos RAM, disco y matrix_free intercambian almacenamiento, cálculo e I/O; matrix_free no elimina el coste de cada evaluación ni garantiza menor tiempo.

## Ejecución y exportación

run_inversion_workflow publica NPZ, VTK, datos CSV y run.json en una carpeta nueva. Guarda observaciones, sigma, regional, predicción, modelo e historia. require_data_target permite exigir el objetivo de datos, pero un estado de ejecución completada no demuestra recuperación geológica.

La salida escalar de gravedad es contraste de densidad. La susceptibilidad negativa, si se permite, es un contraste efectivo bajo la referencia y regional adoptados; no se presenta automáticamente como una medida absoluta de propiedad.

## Geometría conocida y problema libre

fit_prism_density y fit_prism_magnetization estiman propiedades de prismas de geometría fijada. Esa condición reduce la ambigüedad y no es equivalente a recuperar un cuerpo libre voxel a voxel. apparent_layer_property también condiciona la geometría de una capa; su estabilización y background deben declararse.

Ver [controles standalone](../../development/standalone_inversion.md), [regularización](../../reference/methods/regularization_conventions.md), [propiedades aparentes](../../reference/methods/apparent_properties.md), [recuperación](../../validation/reports/voxel_recovery_validation.md) y [SimPEG](https://simpeg.xyz/).

## Implementación relacionada

[inversion](../../../terraworkbench_core/inversion.py), [inversion_workflows](../../../terraworkbench_core/inversion_workflows.py), [spatial_constraints](../../../terraworkbench_core/spatial_constraints.py), [regularization_profiles](../../../terraworkbench_core/regularization_profiles.py), [prism_inversion](../../../terraworkbench_core/prism_inversion.py), [apparent_properties](../../../terraworkbench_core/apparent_properties.py)

---

[Índice](README.md) · [Anterior](14_estructura_profundidad.md) · [Siguiente](16_mvi_conjunta.md)

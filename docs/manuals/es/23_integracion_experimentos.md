# 23. Integración multifuente y métodos experimentales

[English](../en/23_integracion_experimentos.md) · [Español](../es/23_integracion_experimentos.md) · [Português](../pt/23_integracion_experimentos.md)

## Alinear antes de combinar

stack_layers, rgb_composite, pca_fusion y anomaly_coincidence permiten apilar o comparar productos. Se necesitan CRS, lattice, escala, máscara y unidades compatibles. La normalización altera la contribución relativa de una variable: una PCA sobre nT y mGal sin un criterio explícito de escala puede representar principalmente la unidad de mayor varianza numérica.

shift_without_wrap desplaza un array sin recuperar por el borde opuesto valores que salieron del dominio. No equivale a reproyección, ajuste de trayectoria o registro subpíxel con incertidumbre. Cualquier búsqueda de desplazamiento debe validarse con puntos o rasgos independientes.

multisensor_project coordina operaciones y publicaciones; terrain_analysis produce atributos de relieve. vector_grid_audit compara soporte de polígonos y grillas. Verificar que una estadística zonal no mezcle máscaras, unidades o píxeles de borde de manera diferente entre productos.

## Catálogos de anomalías

archaeology contiene exploración multiescala, regiones conectadas y retención de rasgos. Los objetos resultantes son regiones umbralizadas de un campo, no una clasificación arqueológica, edad o identificación de UXO. Una mayor retención respecto a una selección inicial puede conservar ruido si esa selección no tiene referencia independiente.

process_effect compara productos GeoTIFF. Definir soporte común, máscara, transformaciones y diferencias de amplitud antes de interpretar una métrica. No utilizar solo similitud visual para decidir qué filtro conserva mejor una señal de interés.

## Pares de alturas y fusión direccional

paired_flights calcula diferencias entre campos en superficies compartidas, normalizadas por separación vertical. La forma conceptual es:

    G_aparente = (T_alto − T_bajo) / (z_alto − z_bajo)

Requiere alturas, bases de campo, soporte horizontal y umbrales de separación compatibles. Un campo con background retirado de manera distinta en cada vuelo puede producir un pseudogradiente de anomalías locales, no un gradiente vertical absoluto calibrado.

fuse_directions distingue soporte común y cobertura disponible. Una media donde aportan dos direcciones y un único valor donde aporta una generan soportes distintos; conservar el número y origen de contribuciones. La capacidad está disponible en Core, pero este manual no recomienda esos experimentos como parte obligatoria de un procesamiento básico.

No se incluyen alturas, separaciones, sensores, sitios ni parámetros privados de adquisición. Los experimentos históricos permanecen separados de recetas genéricas y requieren validación específica antes de difusión científica.

Ver [API completa](../../reference/api/es.md), [límites de procesamiento](../../validation/reports/processing_overlap_audit.md) y [referencias de integración](../../research/core_expansion_implementation.md).

## Implementación relacionada

[multisensor_fusion](../../../terraworkbench_core/multisensor_fusion.py), [multisensor_project](../../../terraworkbench_core/multisensor_project.py), [terrain_analysis](../../../terraworkbench_core/terrain_analysis.py), [vector_grid_audit](../../../terraworkbench_core/vector_grid_audit.py), [process_effect](../../../terraworkbench_core/process_effect.py), [archaeology](../../../terraworkbench_core/archaeology.py), [paired_flights](../../../terraworkbench_core/paired_flights.py), [crossovers](../../../terraworkbench_core/crossovers.py)

---

[Índice](README.md) · [Anterior](22_ondas_sondeos.md) · [Siguiente](24_gui_qgis.md)

# 18. Resistividad DC, geometría ABMN y PDE

[English](../en/18_electrica_dc.md) · [Español](../es/18_electrica_dc.md) · [Português](../pt/18_electrica_dc.md)

## Datos y geometría

Una medida DC combina electrodos de corriente A/B, potencial M/N, corriente y diferencia de potencial. La resistencia de transferencia V/I se expresa en ohmios. El factor geométrico transforma esa resistencia en resistividad aparente bajo una geometría y medio de referencia; no convierte una observación en resistividad verdadera de una celda.

validate_abmn, geometric_factor, apparent_resistivity y reciprocal_errors ayudan a comprobar geometría, polaridad y reciprocidad. Mantener coordenadas de electrodos y configuración, incluyendo electrodos remotos según el contrato. Un factor muy grande puede amplificar ruido. La reciprocidad evalúa consistencia, no identifica por sí sola la distribución de conductividad.

## Tierra estratificada

dc_layered y fit_dc_resistivity utilizan capas con resistividades y espesores explícitos. El número de espesores es uno menos que el de capas cuando la última representa un semiespacio. Un buen ajuste 1D necesita compatibilidad con la hipótesis lateral del medio; no demuestra ausencia de estructura 2D o 3D.

Comparar sensibilidad a espesores, rango de separaciones y ruido. Si se fijan espesores durante el ajuste, comunicarlo: las resistividades quedan condicionadas a esa geometría y a sus límites.

## Simulación 2.5D y 3D

electrical_pde trabaja con malla tensorial y electrodos ENU en metros. En 2.5D la sección usa X/Z y el survey corresponde a Y = 0. Conductividad en S/m, resistencia de transferencia en ohmios y chargeability IP en V/V. No se realiza snapping o draping automático: los electrodos deben estar ubicados de manera válida respecto a la malla y terreno.

active_cells representa la tierra suministrada; las celdas de aire tienen la conductividad fijada por el módulo. Declarar parameter_labels cuando se ajusten zonas. La inversión por zonas y la inversión con parámetros celulares tienen presupuestos y ambigüedades distintos.

## Controles mínimos

Comprobar malla, origen, extensión, unidades, resistencia prevista para un semiespacio y polaridad. Evaluar convergencia respecto a malla y tratamiento transversal de 2.5D. Revisar celdas activas y posición de electrodos antes de aumentar iteraciones ante un mal ajuste.

Los límites de celdas, parámetros, trabajo y factorización protegen una ejecución; no garantizan capacidad para un levantamiento regional. No se dispone por ello de mallado automático, reconstrucción topográfica o selección geológica certificada.

Ver [implementación de otros métodos](../../validation/reports/inversion_methods_validation.md), [PDE y alcance](../../research/core_expansion_implementation.md) y [SimPEG](https://simpeg.xyz/). Consultar las firmas actuales en la referencia para distinguir observaciones, sigma y log-parametrización del modelo.

## Implementación relacionada

[electrical](../../../terraworkbench_core/electrical.py), [layered_electrical](../../../terraworkbench_core/layered_electrical.py), [electrical_pde](../../../terraworkbench_core/electrical_pde.py)

---

[Índice](README.md) · [Anterior](17_resolucion_incertidumbre.md) · [Siguiente](19_ip_sip.md)

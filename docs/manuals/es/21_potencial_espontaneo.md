# 21. Potencial espontáneo y redes de referencia

[English](../en/21_potencial_espontaneo.md) · [Español](../es/21_potencial_espontaneo.md) · [Português](../pt/21_potencial_espontaneo.md)

## Magnitud y referencias

El potencial espontáneo se mide como diferencia entre electrodos. Su nivel depende de la referencia; combinar perfiles sin resolver offsets puede generar estructuras artificiales. Las APIs del Core utilizan voltios, metros, S/m y amperios según el modelo. Convertir mV de adquisición a V antes de calcular y conservar la unidad original en la procedencia.

adjust_reference_network permite tratar diferencias entre referencias. Revisar conectividad, anclas y ciclos de cierre. Una red sin datum definido no se interpreta como potencial absoluto. Los cambios electroquímicos de electrodos y la deriva instrumental requieren información adicional, no se eliminan porque el ajuste de red tenga residuos pequeños.

## Fuentes prescritas en medio uniforme

prescribed_source_potential y invert_source_currents modelan fuentes eléctricas con conductividad conocida, en espacio completo o con una superficie horizontal aislante. Posición, intensidad y geometría de fuente son parte del problema. No permiten deducir directamente flujo de agua, permeabilidad o coeficiente electrocinético a partir de un mapa SP.

Una geometría de fuente fijada reduce el problema inverso. Comparar sensibilidad a esa geometría, conductividad y referencia antes de atribuir amplitudes a un proceso físico. El mismo campo de potencial puede admitir modelos de fuente distintos.

## Conductor heterogéneo finito

self_potential_pde resuelve una ecuación de la forma:

    −div(σ grad φ) = q

σ es una conductividad isotrópica positiva fijada por celda y q, fuente de corriente por volumen en A/m³. Las caras exteriores son aislantes. Este dominio finito no equivale a infinito abierto y necesita balance de fuentes y referencia coherentes. El módulo no agrega automáticamente aire o topografía a través de una máscara de celdas activas.

sp_pde_forward y fit_sp_pde_sources se deben revisar con tamaño del dominio, malla y condiciones de borde. Si cambiar el límite modifica significativamente la solución cerca de las observaciones, no interpretar el primer resultado como estable.

## Revisión práctica

Conservar diferencias medidas, referencias, tiempos y controles de deriva. Verificar un caso conocido, balance de corriente y unidades. Comparar residuo espacial y regiones con sensibilidad débil. Comunicar que el resultado es un ajuste de fuentes bajo conductividad y fronteras prescritas.

Ver [contratos de otros métodos](../../validation/reports/inversion_methods_validation.md), [límites de implementación](../../research/core_expansion_implementation.md) y la [referencia de API](../../reference/api/es.md).

## Implementación relacionada

[self_potential](../../../terraworkbench_core/self_potential.py), [self_potential_pde](../../../terraworkbench_core/self_potential_pde.py)

---

[Índice](README.md) · [Anterior](20_em_mt.md) · [Siguiente](22_ondas_sondeos.md)

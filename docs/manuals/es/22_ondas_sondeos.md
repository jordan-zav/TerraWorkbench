# 22. GPR, sísmica, procesamiento de trazas y sondeos

[English](../en/22_ondas_sondeos.md) · [Español](../es/22_ondas_sondeos.md) · [Português](../pt/22_ondas_sondeos.md)

## Contrato de arrays

waveform_processing recibe matrices con trazas en filas y tiempo uniformemente muestreado en el último eje. Usa segundos, metros y velocidad en m/s. La presencia de estos kernels no establece lectura de SEG-Y o de todos los formatos propietarios GPR, eliminación de respuesta instrumental ni una solución sísmica de interpretación completa.

Identificar primero el instante cero, dt, distancia entre trazas, canales y orientación de componentes. Registrar si una matriz representa amplitud física calibrada o cuentas digitales. Una interpolación o remuestreo temporal debe quedar como operación separada.

## Preparación de trazas

trace_bandpass aplica Butterworth SOS de fase cero; las dos pasadas alteran amplitud respecto a una pasada. dewow reduce contenido de baja frecuencia según una ventana elegida. remove_trace_background retira una componente común y puede eliminar reflectores horizontales reales. correct_time_zero desplaza la referencia temporal; explicit_time_gain modifica amplitudes con una función declarada.

Conservar una versión sin ganancias de visualización. No ajustar velocidad o amplitudes de reflexión sobre un producto AGC sin considerar cómo se transformó la señal. Comparar bordes temporales, zonas sin soporte y diferencias antes/después de cada paso.

## Herramientas de interpretación limitada

fit_diffraction_hyperbola ajusta una geometría y velocidad efectivas bajo el modelo de hipérbola. normal_moveout necesita velocidad y offsets compatibles con su aproximación; no equivale a migración. phase_velocity_image produce una representación de velocidad de fase cuya resolución depende del arreglo y de los datos. hvsr_windows y sta_lta_picks implementan análisis por ventanas y detección de cambios, sin seleccionar automáticamente una interpretación estratigráfica o evento verdadero.

## Registros y trayectoria

well_log_io incorpora lectura de texto LAS y actualización de curvas mediante lasio cuando corresponde. Revisar mnemónicos, unidades, NULL, profundidad inicial/final y espaciado. No convertir un archivo LAS de registros de pozo en una nube LiDAR por compartir extensión.

borehole contiene QC de profundidad y trayectoria de mínima curvatura. Se necesitan profundidad medida, inclinación y azimut con referencias definidas. Profundidad medida a lo largo del pozo no equivale a elevación vertical ni a distancia horizontal. La trayectoria reconstruida hereda incertidumbres de rumbo e inclinación.

## Aceptación

Comprobar conteos de muestras y trazas, dt, velocidades plausibles, inversión de ejes, nulls y datos recalculados desde la exportación. Separar las curvas originales, las corregidas y las interpretadas. Los ejemplos sintéticos prueban contratos concretos; no certifican cualquier instrumento o formato.

Ver [métodos y límites](../../research/core_expansion_implementation.md), [validación de métodos](../../validation/reports/inversion_methods_validation.md) y [API de ondas y registros](../../reference/api/es.md).

## Implementación relacionada

[waveform_processing](../../../terraworkbench_core/waveform_processing.py), [well_log_io](../../../terraworkbench_core/well_log_io.py), [borehole](../../../terraworkbench_core/borehole.py)

---

[Índice](README.md) · [Anterior](21_potencial_espontaneo.md) · [Siguiente](23_integracion_experimentos.md)

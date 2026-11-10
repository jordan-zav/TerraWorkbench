# 20. FDEM, TEM, transitorios y magnetotelúrica

[English](../en/20_em_mt.md) · [Español](../es/20_em_mt.md) · [Português](../pt/20_em_mt.md)

## Separar los problemas

FDEM utiliza frecuencias discretas y respuesta compleja; TEM utiliza evolución temporal, excitación y compuertas. MT trabaja con impedancia entre campos naturales y tiene convenciones de ejes y unidades propias. Una conductividad ajustada en cualquiera de estos modelos depende de geometría, calibración y parametrización.

## FDEM

fdem_layered representa una Tierra estratificada y fit_fdem_conductivity ajusta conductividades bajo geometría fijada. Registrar separación, orientación y altura de transmisor/receptor, frecuencia, momento y componente. No intercambiar B secundaria en teslas con ppm respecto al primario sin la conversión instrumental apropiada.

fdem_3d_forward y fit_fdem_3d_zones permiten campos 3D isotrópicos y ajuste local por zonas con malla explícita. La factorización dispersa impone límites de trabajo. Esta capacidad no establece inversión industrial de millones de voxeles, anisotropía ni diseño automático de malla.

complex_calibration contiene ajuste y aplicación de respuesta compleja. Una calibración de amplitud y fase requiere patrones y contexto instrumental; no adoptar una respuesta unitaria porque el archivo no incluya información de transferencia.

## TEM y compuertas

tem_stepoff_layered representa la respuesta al apagado ideal; tem_waveform_layered incorpora una forma de onda lineal por tramos. Registrar si la variable es B o dB/dt y sus unidades; el contrato de estos métodos utiliza dB/dt en T/s donde corresponde. La respuesta de un dipolo ideal no equivale a una espira finita con electrónica real.

tem_gate_average, stack_transients y gate_recorded_transients distinguen predicción integrada, datos registrados y apilado. Definir tiempos absolutos o relativos al apagado, ancho de ventanas y signo de pulsos. Una interpolación temporal no crea soporte fuera del registro.

## MT

magnetotellurics usa Z = E/H en ohmios, convención exp(+iωt) y ejes horizontales Norte/Este. La respuesta 1D entrega Zxy positivo y Zyx = −Zxy. La resistividad aparente depende de |Z|²/(μ₀ω); utilizar E/B en lugar de E/H cambia las unidades y necesita conversión.

layered_impedance, apparent_resistivity_phase, phase_tensor y fit_layered_resistivity proporcionan primitivas y ajustes. El módulo no es un lector EDI/MTH5 ni un estimador robusto de funciones de transferencia desde series temporales. Un phase tensor calculado no valida los campos de entrada ni elimina todas las distorsiones instrumentales.

Ver [métodos y límites](../../research/core_expansion_implementation.md), [validación de inversiones](../../validation/reports/inversion_methods_validation.md) y [catálogo de SimPEG](https://simpeg.xyz/). No atribuir a TerraWorkbench todas las capacidades del motor externo que utiliza.

## Implementación relacionada

[layered_em](../../../terraworkbench_core/layered_em.py), [fdem_3d](../../../terraworkbench_core/fdem_3d.py), [magnetotellurics](../../../terraworkbench_core/magnetotellurics.py), [transient_processing](../../../terraworkbench_core/transient_processing.py), [complex_calibration](../../../terraworkbench_core/complex_calibration.py)

---

[Índice](README.md) · [Anterior](19_ip_sip.md) · [Siguiente](21_potencial_espontaneo.md)

# 13. Radiometría gamma, espectros y radón

[English](../en/13_radiometria.md) · [Español](../es/13_radiometria.md) · [Português](../pt/13_radiometria.md)

## Distinguir productos y observaciones

Concentraciones K, eU y eTh, tasas de conteo y espectros por canal son entradas diferentes. K se expresa habitualmente en porcentaje; eU y eTh, en ppm equivalentes bajo los supuestos de calibración y equilibrio. Un RGB no conserva por sí solo incertidumbre ni escala comparable entre campañas.

radiometry ofrece ratios seguros, tasa de dosis terrestre, factor F, ternarios y QC. El ternario usa K en rojo, eTh en verde y eU en azul; registrar percentiles y si se normalizó. Un ratio solo es interpretable cuando el denominador tiene soporte suficiente. safe_ratio y los umbrales acumulativos evitan interpretar divisiones por valores próximos a cero como enriquecimientos seguros.

## Calibrar cuentas

1. Identificar integración temporal, tiempo vivo y estado de correcciones previas.
2. Aplicar el modelo de tiempo muerto o tiempo vivo correspondiente, sin doble corrección.
3. Estimar y retirar fondos de instrumento, cósmico y radón con calibración apropiada.
4. Aplicar corrección de altura respecto a una referencia justificada.
5. Resolver mezcla de ventanas o espectros con matriz de respuesta calibrada.
6. Convertir a concentraciones y propagar incertidumbre bajo los supuestos declarados.

Para un detector no paralizable, la corrección de tiempo muerto tiene la forma n = m/(1 − τm). La fórmula falla cuando el denominador no es positivo. live_time_correction es otra operación: requiere tiempo vivo medido y tasas normalizadas al intervalo. No combinar ambas por rutina.

## Espectros y covarianza

energy_rebin y fit_energy_calibration tratan escala energética y redistribución de bins. Integrar ventanas requiere límites energéticos y manejo de covarianzas. fit_full_spectrum y spectral_unmix resuelven modelos distintos; documentar plantillas, unidades, fondo y restricciones.

NASVD y MNF reducen ruido bajo hipótesis estadísticas. Suavizar no genera información energética nueva; evaluar sesgo de amplitudes, covarianzas y componentes negativas. fit_radiometric_response y radiometric_concentrations requieren patrones y respuesta instrumental pertinentes; no existe una sensibilidad universal para cualquier detector.

## Radón: alcance real

Hay correcciones por detector ascendente, ventanas calibradas, espectro completo y un proxy temporal con detectores emparejados. Los coeficientes y fondos deben venir de calibración; una correlación o una solución algebraica no establece reconstrucción atmosférica completa de campo. Examinar chi cuadrado, residuos espectrales, componentes negativas y estabilidad temporal.

Los patrones de laboratorio y las simulaciones no sustituyen condiciones aéreas, presión, humedad, altura y geometría del sistema. Los informes existentes conservan esas limitaciones.

Lecturas: [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf), [contratos de calibración y radón](../../validation/reports/2d_extensions.md), [métodos implementados](../../research/core_expansion_implementation.md) y [campaña pública](../../validation/reports/public_processing_benchmark.md). IAEA aporta contexto metodológico; no valida automáticamente los coeficientes ni el código local.

## Implementación relacionada

[radiometry](../../../terraworkbench_core/radiometry.py), [radiometric_calibration](../../../terraworkbench_core/radiometric_calibration.py), [radiometric_spectra](../../../terraworkbench_core/radiometric_spectra.py), [radiometric_radon](../../../terraworkbench_core/radiometric_radon.py), [radon_corrections](../../../terraworkbench_core/radon_corrections.py)

---

[Índice](README.md) · [Anterior](12_terreno_isostasia.md) · [Siguiente](14_estructura_profundidad.md)

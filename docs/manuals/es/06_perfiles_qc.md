# 6. QC, trayectoria, tiempos y correcciones de adquisición

[English](../en/06_perfiles_qc.md) · [Español](../es/06_perfiles_qc.md) · [Português](../pt/06_perfiles_qc.md)

## Conservar el orden de adquisición

Los filtros de perfiles trabajan en muestras, tiempo o distancia. Database identifica un contenedor, no un dominio matemático. Para tiempo se necesita un eje temporal numérico; para distancia, una abscisa métrica definida por perfil. La distancia acumulada sigue la trayectoria y no equivale a distancia radial desde la primera observación.

Definir línea y sensor antes de filtrar. Los nulos, cambios de grupo, ejes no crecientes y huecos separan tramos. El motor no ordena, interpola huecos ni une líneas por su cuenta. Inspeccionar velocidad, dirección, espaciado y muestras duplicadas antes de considerar un tramo uniforme.

## Correcciones magnéticas de adquisición

La estación base corrige variación temporal bajo supuestos de sincronización y representatividad. Revisar calidad de base y soporte temporal: extrapolar una estación más allá de sus registros puede crear una corrección sin evidencia. El lag desplaza la relación entre medida y posición; documentar su signo y verificarlo con líneas repetidas o señales comparables.

La corrección de rumbo modela efectos dependientes de orientación. Tolles–Lawson requiere datos vectoriales, calibración y geometría pertinentes; una regresión que absorbe señal geológica no es compensación instrumental demostrada. Conservar diseño, coeficientes y ventanas de calibración para reproducir el resultado.

## Selección de filtros de canal

| Proceso | Parámetro decisivo | Riesgo |
| --- | --- | --- |
| Media o mediana móvil | Ventana impar en muestras | Atenuar anomalías estrechas |
| Despike Hampel | Ventana y umbral MAD | Confundir señal real con picos |
| Detrend | Grado y dominio del eje | Retirar contenido regional útil |
| Butterworth | Corte, orden y frecuencia de muestreo | Cortes mal convertidos o bordes dominantes |
| Notch por API específica | Frecuencia rechazada y ancho | Retirar señal junto con interferencia |

ChannelFilterOptions admite ventana impar de 3 a 1.001 muestras, orden Butterworth de 1 a 10 y un máximo de tres millones de filas por tramo. En tiempo o distancia se comprueba monotonía y uniformidad dentro de una tolerancia explícita. La frecuencia de corte se expresa en ciclos por unidad del eje, no en radianes por metro del FFT 2D.

Los filtros móviles necesitan ventanas completas y dejan bordes nulos. El Butterworth usa SOS hacia delante y atrás; reduce desfase pero su respuesta de amplitud es la del filtro aplicado dos veces. Un tramo corto puede quedar sin salida válida: no se presenta la copia original como si estuviera filtrada.

## QC de gravedad móvil

La deriva exige tiempos y épocas consistentes. Marea, Eötvös y movimiento requieren convenciones de signo y canales de velocidad compatibles; no aplicar correcciones por simple disponibilidad de un campo llamado heading. En gravedad terrestre estacionaria estos pasos no se trasladan automáticamente desde un flujo aéreo.

Ver [adquisición independiente](../../development/standalone_acquisition.md), [reglas de canales](../../guides/survey_workspaces.md) y [SOS forward/backward de SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html).

## Implementación relacionada

[channel_filters](../../../terraworkbench_core/channel_filters.py), [profile_distance](../../../terraworkbench_core/profile_distance.py), [profile_preparation](../../../terraworkbench_core/profile_preparation.py), [preprocessing](../../../terraworkbench_core/preprocessing.py), [survey_corrections](../../../terraworkbench_core/survey_corrections.py), [survey_correction_pipeline](../../../terraworkbench_core/survey_correction_pipeline.py), [magnetic_compensation](../../../terraworkbench_core/magnetic_compensation.py)

---

[Índice](README.md) · [Anterior](05_bases_canales.md) · [Siguiente](07_nivelacion_gridding.md)

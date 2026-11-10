# 19. IP, SIP, Cole–Cole e historial de corriente

[English](../en/19_ip_sip.md) · [Español](../es/19_ip_sip.md) · [Português](../pt/19_ip_sip.md)

## Magnitudes y dominio

La cargabilidad integrada depende de ventanas temporales, potencial primario y convención de normalización. V/V y mV/V difieren por un factor de mil. Una integral temporal sin normalización o unidades no se puede comparar directamente con una amplitud Cole–Cole adimensional.

electrical ofrece integrated_chargeability y cole_cole_resistivity. dispersive_ip incluye respuesta y ajuste en frecuencia y tiempo. El exponente, tau y convención compleja deben acompañar los resultados; una fase con signo opuesto puede provenir de la convención temporal y no de una diferencia de geología.

## Forma de onda y memoria

Una respuesta a un pulso ideal aislado no equivale a una adquisición con pulsos de signos alternos y polarización remanente de pulsos anteriores. ip_waveform modela historial de corriente y compuertas explícitas. Registrar tiempos de cambio, amplitud de cada pulso, inicio y final de ventanas y referencia del potencial primario.

El apilado puede calcular media de ratios o ratio de sumas. Estas dos operaciones no son algebraicamente iguales si cambia el denominador. stack_ip_decay y fit_ip_stack conservan convención, pesos e intervalos aceptados. No corregir discrepancias entre campañas cambiando retrospectivamente la definición de cargabilidad.

## Inversión espacial

La IP estática de electrical_pde se linealiza alrededor de conductividad fija para cargabilidades pequeñas. No representa automáticamente inversión espacial completa de una Tierra Cole–Cole dispersiva. Las funciones espaciales de historial de corriente también necesitan el modelo de sensibilidad y las zonas especificadas por su contrato.

Los ajustes de decaimiento pueden ser ambiguos en tau, exponente y amplitud si las ventanas no cubren las escalas relevantes. La existencia de un covariance array local no significa identificación única de esos parámetros. Examinar correlaciones, cotas, ventanas reservadas y sensibilidad a incertidumbres.

## Procedimiento

1. Verificar polaridad y geometría DC.
2. Conservar la corriente medida y las compuertas originales.
3. Identificar normalización y unidades de cada observación.
4. Ajustar el modelo apropiado al dominio y a la secuencia de pulsos.
5. Comparar respuesta completa, no solo una cargabilidad resumen.
6. Revisar residuos temporales/frecuenciales y límites de parámetros.

Ver [IP dispersiva](../../reference/methods/dispersive_ip_mvi.md), [historial de corriente](../../reference/methods/ip_current_history.md), [apilado](../../reference/methods/ip_stacking.md) y las referencias primarias asociadas a cada contrato. Una operación registrada IP no significa que todos los tipos instrumentales de IP estén implementados o validados.

## Implementación relacionada

[dispersive_ip](../../../terraworkbench_core/dispersive_ip.py), [ip_waveform](../../../terraworkbench_core/ip_waveform.py), [ip_stacking](../../../terraworkbench_core/ip_stacking.py)

---

[Índice](README.md) · [Anterior](18_electrica_dc.md) · [Siguiente](20_em_mt.md)

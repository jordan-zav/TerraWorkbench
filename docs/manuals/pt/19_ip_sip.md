# 19. IP, SIP, Cole–Cole e histórico de corrente

[English](../en/19_ip_sip.md) · [Español](../es/19_ip_sip.md) · [Português](../pt/19_ip_sip.md)

## Grandezas e domínio

Cargabilidade integrada depende de janelas temporais, potencial primário e normalização. V/V e mV/V diferem por mil. Uma integral temporal sem unidades/normalização não pode ser comparada diretamente à amplitude Cole–Cole adimensional.

electrical fornece integrated_chargeability e cole_cole_resistivity. dispersive_ip inclui cálculo direto e ajuste em frequência e tempo. Expoente, tau e convenção complexa devem acompanhar os resultados; fases com sinais opostos podem decorrer da convenção temporal, não da geologia.

## Forma de onda e memória

Um pulso ideal isolado não representa pulsos de sinais alternados com polarização residual de pulsos anteriores. ip_waveform modela histórico de corrente e janelas explícitos. Registrar tempos de comutação, amplitudes, início/fim das janelas e referência do potencial primário.

O empilhamento pode usar média de razões ou razão das somas. Não são equivalentes quando o denominador varia. stack_ip_decay e fit_ip_stack preservam convenção, pesos e intervalos aceitos. Não reconciliar campanhas alterando retrospectivamente a definição de cargabilidade.

## Inversão espacial

A IP estática de electrical_pde é linearizada em torno de condutividade fixa para cargabilidades pequenas. Não equivale automaticamente à inversão espacial completa de Terra Cole–Cole dispersiva. Funções espaciais de histórico também exigem o modelo de sensibilidade e zonas definidos em seu contrato.

Ajustes de decaimento podem ser ambíguos em tau, expoente e amplitude quando as janelas não cobrem as escalas relevantes. Covariância local não estabelece identificação única. Examinar correlações, limites, janelas reservadas e sensibilidade às incertezas.

## Procedimento

1. Verificar polaridade e geometria DC.
2. Preservar corrente medida e janelas originais.
3. Identificar normalização e unidades de cada observação.
4. Ajustar modelo apropriado ao domínio e à sequência de pulsos.
5. Comparar resposta completa, não apenas cargabilidade-resumo.
6. Examinar resíduos temporais/frequenciais e limites de parâmetros.

Ver [IP dispersiva](../../reference/methods/dispersive_ip_mvi.md), [histórico de corrente](../../reference/methods/ip_current_history.md), [empilhamento](../../reference/methods/ip_stacking.md) e referências primárias de cada contrato. Uma operação IP registrada não significa implementar ou validar todos os modos instrumentais.

## Implementação relacionada

[dispersive_ip](../../../terraworkbench_core/dispersive_ip.py), [ip_waveform](../../../terraworkbench_core/ip_waveform.py), [ip_stacking](../../../terraworkbench_core/ip_stacking.py)

---

[Índice](README.md) · [Anterior](18_electrica_dc.md) · [Próximo](20_em_mt.md)

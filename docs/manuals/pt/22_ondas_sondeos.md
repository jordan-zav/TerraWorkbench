# 22. GPR, traços sísmicos e sondagens

[English](../en/22_ondas_sondeos.md) · [Español](../es/22_ondas_sondeos.md) · [Português](../pt/22_ondas_sondeos.md)

## Contrato de arrays

waveform_processing recebe matrizes com traços nas linhas e tempo uniformemente amostrado no último eixo. Usa segundos, metros e m/s. Esses kernels não estabelecem leitura SEG-Y ou de todos os formatos proprietários GPR, remoção de resposta instrumental ou sistema completo de interpretação sísmica.

Identificar primeiro tempo zero, dt, espaçamento entre traços, canais e orientação das componentes. Informar se amplitudes são grandezas físicas calibradas ou contagens digitais. Interpolação/reamostragem temporal é uma operação separada e registrada.

## Preparação de traços

trace_bandpass aplica Butterworth SOS de fase zero; duas passagens mudam a amplitude em relação a uma. dewow reduz baixa frequência conforme uma janela. remove_trace_background retira componente comum e pode apagar refletores horizontais reais. correct_time_zero desloca a referência temporal; explicit_time_gain altera amplitudes por função declarada.

Preservar versão sem ganhos de visualização. Ajustar velocidade ou amplitude de reflexão sobre AGC exige considerar a transformação do sinal. Comparar bordas temporais, regiões sem suporte e diferenças em cada etapa.

## Ferramentas de interpretação limitada

fit_diffraction_hyperbola ajusta geometria e velocidade efetivas sob modelo hiperbólico. normal_moveout precisa de velocidade/offsets compatíveis e não equivale à migração. phase_velocity_image produz representação cuja resolução depende do arranjo e dos dados. hvsr_windows e sta_lta_picks implementam análise por janelas e detecção de mudanças sem determinar automaticamente estratigrafia ou eventos verdadeiros.

## Perfis e trajetória

well_log_io lê texto LAS e atualiza curvas com lasio quando pertinente. Conferir mnemônicos, unidades, NULL, profundidades inicial/final e espaçamento. LAS de perfilagem de poço não é nuvem LiDAR, apesar da extensão compartilhada.

borehole oferece QC de profundidade e trajetória de mínima curvatura. Profundidade medida, inclinação e azimute exigem referências definidas. Profundidade ao longo do poço não é elevação vertical nem distância horizontal. A trajetória reconstruída herda incerteza de rumo/inclinação.

## Aceitação

Verificar contagens de amostras/traços, dt, velocidades plausíveis, eixos invertidos, nulos e valores reabertos da exportação. Separar curvas originais, corrigidas e interpretadas. Exemplos controlados testam contratos específicos, não qualquer instrumento ou formato.

Ver [métodos e limites](../../research/core_expansion_implementation.md), [validação de métodos](../../validation/reports/inversion_methods_validation.md) e [APIs de ondas e registros](../../reference/api/pt.md).

## Implementação relacionada

[waveform_processing](../../../terraworkbench_core/waveform_processing.py), [well_log_io](../../../terraworkbench_core/well_log_io.py), [borehole](../../../terraworkbench_core/borehole.py)

---

[Índice](README.md) · [Anterior](21_potencial_espontaneo.md) · [Próximo](23_integracion_experimentos.md)

# 6. QC, trajetória, tempos e correções de aquisição

[English](../en/06_perfiles_qc.md) · [Español](../es/06_perfiles_qc.md) · [Português](../pt/06_perfiles_qc.md)

## Preservar a ordem de aquisição

Filtros de perfil operam em amostras, tempo ou distância. Database identifica um contêiner, não um domínio matemático. Tempo exige eixo temporal numérico; distância exige abscissa métrica definida por perfil. Distância acumulada segue a trajetória e não é distância radial desde a primeira observação.

Definir linha e sensor antes de filtrar. Nulos, mudanças de grupo, eixos não crescentes e lacunas separam trechos. O motor não ordena, interpola lacunas ou une linhas automaticamente. Inspecionar velocidade, rumo, espaçamento e duplicatas antes de supor amostragem uniforme.

## Correções magnéticas de aquisição

A estação-base corrige variação temporal sob hipóteses de sincronização e representatividade. Revisar qualidade e suporte temporal: extrapolar além do registro pode introduzir correção sem evidência. Lag desloca a relação medida–posição; registrar o sinal e verificar com linhas repetidas ou sinais comparáveis.

A correção de rumo modela efeitos dependentes de orientação. Tolles–Lawson precisa de dados vetoriais, calibração e geometria adequados; uma regressão que absorve geologia não demonstra compensação instrumental. Preservar matriz de projeto, coeficientes e janelas de calibração para reprodução.

## Escolher filtros de canal

| Processo | Parâmetro decisivo | Risco |
| --- | --- | --- |
| Média ou mediana móvel | Janela ímpar em amostras | Atenuar anomalias estreitas |
| Despike Hampel | Janela e limiar MAD | Confundir sinal real com picos |
| Detrend | Grau e domínio do eixo | Retirar conteúdo regional útil |
| Butterworth | Corte, ordem e amostragem | Conversão errada ou bordas dominantes |
| API específica de notch | Frequência rejeitada e largura | Retirar sinal junto da interferência |

ChannelFilterOptions aceita janela ímpar de 3 a 1.001 amostras, ordem Butterworth de 1 a 10 e até três milhões de linhas por trecho. Em tempo/distância, verifica monotonicidade e uniformidade com tolerância explícita. O corte é expresso em ciclos por unidade do eixo, não nos rad/m da FFT 2D.

Filtros móveis precisam de janelas completas e deixam bordas nulas. Butterworth usa SOS para frente e para trás: reduz defasagem, mas a resposta de amplitude corresponde a duas passagens. Um trecho curto pode ficar sem saída válida; o original não é apresentado silenciosamente como filtrado.

## QC de gravidade móvel

Deriva exige tempos e épocas consistentes. Maré, Eötvös e movimento requerem canais de velocidade e sinais compatíveis; não aplicar correções só porque existe um campo heading. Etapas aéreas não se transferem automaticamente para gravimetria terrestre estacionária.

Ver [aquisição independente](../../development/standalone_acquisition.md), [regras de canais](../../guides/survey_workspaces.md) e [SOS forward/backward do SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html).

## Implementação relacionada

[channel_filters](../../../terraworkbench_core/channel_filters.py), [profile_distance](../../../terraworkbench_core/profile_distance.py), [profile_preparation](../../../terraworkbench_core/profile_preparation.py), [preprocessing](../../../terraworkbench_core/preprocessing.py), [survey_corrections](../../../terraworkbench_core/survey_corrections.py), [survey_correction_pipeline](../../../terraworkbench_core/survey_correction_pipeline.py), [magnetic_compensation](../../../terraworkbench_core/magnetic_compensation.py)

---

[Índice](README.md) · [Anterior](05_bases_canales.md) · [Próximo](07_nivelacion_gridding.md)

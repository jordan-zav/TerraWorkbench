# 7. Cruzamentos, nivelamento e interpolação

[English](../en/07_nivelacion_gridding.md) · [Español](../es/07_nivelacion_gridding.md) · [Português](../pt/07_nivelacion_gridding.md)

## Ordem de processamento

O nivelamento reduz diferenças entre linhas após correções temporais e de aquisição. A geração de grade estima um campo em uma malha; não resolve sozinha erros de lag, estação-base ou altura. Revisar primeiro geometria de linhas, qualidade de cruzamentos e conectividade.

Diferenças entre observações comparáveis em um cruzamento restringem correções relativas. Uma rede desconectada ou sem âncora não determina datum absoluto. Ajustes robustos constantes ou polinomiais reduzem a influência de alguns resíduos, mas grau e linhas aceitas continuam sendo escolhas do usuário. Registrar cruzamentos rejeitados, correções e resíduos por linha.

## Escolher interpolador

| Método | Controles principais | Cuidado |
| --- | --- | --- |
| Vizinho mais próximo | Distribuição de pontos | Descontinuidades entre regiões |
| IDW | Potência, vizinhos, raio | Linhas densas podem dominar |
| TPS global | Suavidade e suporte completo | Custo de sistema denso |
| TPS local | Vizinhança e suavidade | Não equivale ao ajuste global |
| Mínima curvatura experimental | Malha, iterações e convergência | Conferir resíduos e limites; não supor equivalência proprietária |
| Sinc | Amostragem e suporte | Não recupera detalhe não adquirido |
| Krigagem ordinária | Variograma, vizinhos, efeito pepita | Justificar o modelo estatístico |
| Fontes equivalentes | Profundidade e damping | Problema físico regularizado, não interpolação neutra |

Células menores podem melhorar a apresentação sem aumentar resolução física. Fixar extensão, origem e célula antes de comparar produtos. Comparações numéricas precisam do mesmo lattice ou de reamostragem documentada.

## Validação espacial

Reservar blocos ou linhas antes de selecionar parâmetros. Medir erro em pontos não utilizados e examinar sua localização; um RMS global pode ocultar extrapolação ruim nas bordas. Validação aleatória entre pontos próximos da mesma linha pode ser otimista.

Um variograma empírico depende de distância, bins, tendência, pares e anisotropia. Seu modelo não transforma a variância de krigagem em incerteza total de aquisição/interpretação. Fontes equivalentes precisam de separação dos receptores, unidades e superfície de previsão explícitas.

## Micronivelamento

Aplicar depois das correções principais e do nivelamento de cruzamentos, para tratar corrugação direcional residual. Comparar a correção retirada com amplitude e orientação de estruturas reais. Mudar azimute, corte ou máscara pode alterar sinal geológico, especialmente paralelo ao voo.

Preservar separadamente correções por linha, superfície aplicada e produto final. Aparência mais suave não basta como critério de aceitação.

Detalhes: [interpolação](../../reference/methods/interpolation_methods.md), [pipeline básico](../../guides/basic_processing_migration.md), [fontes equivalentes e métodos](../../research/core_expansion_implementation.md) e [extensões geoestatísticas](../../validation/reports/2d_extensions.md).

## Implementação relacionada

[line_processing](../../../terraworkbench_core/line_processing.py), [gridding_methods](../../../terraworkbench_core/gridding_methods.py), [survey_processing](../../../terraworkbench_core/survey_processing.py), [survey_grid_pipeline](../../../terraworkbench_core/survey_grid_pipeline.py), [equivalent_sources](../../../terraworkbench_core/equivalent_sources.py), [geostatistics](../../../terraworkbench_core/geostatistics.py)

---

[Índice](README.md) · [Anterior](06_perfiles_qc.md) · [Próximo](08_filtros_espaciales.md)

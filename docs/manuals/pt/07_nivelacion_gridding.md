# 7. Cruzamentos, nivelamento e interpolação

[English](../en/07_nivelacion_gridding.md) · [Español](../es/07_nivelacion_gridding.md) · [Português](../pt/07_nivelacion_gridding.md)

Quando a solicitação exceder o limite, use o tamanho de célula sugerido ou reduza a extensão. A janela de Processamento oferece **Continuar somente desta vez**. Para autorizar uma execução no formulário, no modelo ou em lote, ative **Permitir grades grandes de curvatura mínima** em Parâmetros avançados. Grades grandes podem exigir muito mais memória e tempo.

## Ordem de processamento

O nivelamento reduz diferenças entre linhas após correções temporais e de aquisição. A geração de grade estima um campo em uma malha; não resolve sozinha erros de lag, estação-base ou altura. Revisar primeiro geometria de linhas, qualidade de cruzamentos e conectividade.

Diferenças entre observações comparáveis em um cruzamento restringem correções relativas. Uma rede desconectada ou sem âncora não determina datum absoluto. Ajustes robustos constantes ou polinomiais reduzem a influência de alguns resíduos, mas grau e linhas aceitas continuam sendo escolhas do usuário. Registrar cruzamentos rejeitados, correções e resíduos por linha.

## Validação quantitativa da interpolação

Em um levantamento aéreo sintético com cinco milhões de observações em 100 linhas, a grade de 159.197 células a 25 m apresentou RMS de 0,000355 para a curvatura mínima com tensão 0,1 e de 0,000282 para a interpolação bidirecional PCHIP, em unidades do campo analítico. O cálculo levou 35,2 e 2,25 s, respectivamente, com picos de memória de processo de 412,5 e 389,7 MiB. O ensaio usou geometria regular e entradas em memória, com a exportação do raster fora da medição. O erro transversal ainda variou conforme a posição entre linhas.

O solver multinível tem um limite padrão de 500.000 nós de trabalho, incluindo margens. Uma extensão quadrada de 50 km a 25 m requer 4.020.025 nós. O programa informa o limite e sugere uma célula de pelo menos 71,5 m para essa extensão. Os resultados da comparação externa aguardam autorização para divulgação. [Briggs (1974)](https://doi.org/10.1190/1.1440410) · [Smith e Wessel (1990)](https://doi.org/10.1190/1.1442837)

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

## Interpolação de linhas de voo

Abra **Interpolar pontos do levantamento para GeoTIFF** no Processing. Selecione um canal numérico, um SRC projetado e, para o método bidirecional, o campo que identifica as linhas de produção. Exclua linhas de amarração, curvas e linhas de orientação incompatível. Com identificadores e tamanho automático, divide-se a mediana do espaçamento transversal por 4 ou 5. Sem identificadores, usa-se a densidade de pontos.

O método bidirecional interpola linearmente ao longo de cada perfil e depois entre perfis com interpolação linear ou cúbica PCHIP. A tendência opcional ajusta um plano, interpola os resíduos e repõe o plano. Os limites de lacuna ao longo e entre linhas evitam atravessar intervalos sem suporte. Para linhas oblíquas, a malha alinhada ao voo é reamostrada sobre os eixos do SRC.

A curvatura mínima com tensão usa restrições fora dos nós de Briggs, refinamento progressivo e condições naturais discretas nas bordas. Examine os metadados de convergência do GeoTIFF. Desative a média por célula para selecionar diretamente a observação mais próxima de cada nó em cada nível quando a amostragem ao longo da linha é densa.

Valores nulos e não finitos são excluídos. Indique um valor nulo numérico se o canal usa um código finito. Combine uma distância máxima com o polígono **survey_boundary** gerado pelo mapa do levantamento para atribuir NoData fora da cobertura. O polígono preserva ilhas e lacunas e é transformado para o SRC de saída. A distância é medida do centro da célula às observações válidas.

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

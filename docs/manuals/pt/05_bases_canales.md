# 5. Workspaces, canais, versões e linhagem

[English](../en/05_bases_canales.md) · [Español](../es/05_bases_canales.md) · [Português](../pt/05_bases_canales.md)

## Modelo de armazenamento

SurveyStore combina catálogo SQLite e arquivos Parquet imutáveis. O catálogo identifica bases, canais, versões e eventos. Parquet permite ler por colunas e lotes; processar uma variável não exige carregar todos os canais. O workspace é uma unidade de trabalho, não um arquivo GDB proprietário.

A base preserva alinhamento de linhas. Selecionar colunas não o altera. Máscaras e filtros de visualização restringem consultas, sem reordenar automaticamente a aquisição. A geometria armazenada identifica canais XY e SRC, sem transformar coordenadas.

## Primeira base pela interface

Abrir o explorador, escolher Novo projeto e uma pasta vazia, depois Importar texto / Parquet. Revisar o assistente antes de aceitar. Selecionar uma base à esquerda e somente os canais necessários; Carregar seleção mostra uma página sem despejar todas as linhas na tabela. As ações de canais preparam derivados e mostram seu pipeline. Salvar produtos importantes fora de temporários e preservar a pasta completa do workspace.

![Versões de canais](../assets/pt/linaje.svg)

Figura 2. Fontes e canais derivados em um exemplo conceitual. A versão de entrada, além do nome, determina o conteúdo processado.

## Criar uma variável derivada

Nomear primeiro grandeza e unidade: mag_anomaly_nt, gravity_complete_bouguer_mgal ou sensor_height_m. Acrescentar o passo distintivo para alternativas, como mag_anomaly_lowpass_nt. O rótulo não substitui parâmetros registrados.

A fórmula usa linguagem aritmética restrita. Por exemplo, c("field_nt") − c("main_field_nt") subtrai canais alinhados. Não é um interpretador Python geral e não deve executar imports ou instruções externas.

A derivação conserva versões de entrada. Se o conteúdo mudou após a revisão da receita, parar e revisar novamente. Duplicar um canal pode criar alias da mesma versão imutável sem copiar todos os bytes; versões futuras evoluem independentemente.

## Publicar cálculos externos

publish_channels recebe arrays com o mesmo número de linhas da base, uma unidade por saída, versões exatas dos canais utilizados e procedência com o nome da operação. Os nomes precisam ser novos. As saídas são publicadas juntas em transação; NaN vira nulo, enquanto infinitos ou comprimentos incompatíveis são rejeitados.

Registrar parameters, libraries e engine mostra parâmetros, bibliotecas e motor no inspetor de linhagem. Incluir topografia, campo indutor e seleção quando participarem, mesmo que não apareçam diretamente na fórmula final.

## Capacidade e segurança

A capacidade total da base difere do limite do filtro por trecho. O filtrado de canais aceita até três milhões de amostras por trecho contínuo, sujeito aos demais orçamentos. Uma base com várias linhas pode ter mais registros. Não concatenar linhas para contornar os controles de continuidade.

O orçamento de arrays publicados limita seu tamanho float64 combinado; não limita toda a RAM nem inclui buffers do motor. Separar originais de derivados e fazer backup coerente de catálogo e Parquet.

Ver [workspaces](../../guides/survey_workspaces.md), [explorador](../../guides/survey_explorer.md) e [contratos de evidência](../../guides/api_evidence.md).

## Implementação relacionada

[survey_store](../../../terraworkbench_core/survey_store.py), [survey_explorer](../../../terraworkbench_core/survey_explorer.py), [survey_recipes](../../../terraworkbench_core/survey_recipes.py)

---

[Índice](README.md) · [Anterior](04_importacion.md) · [Próximo](06_perfiles_qc.md)

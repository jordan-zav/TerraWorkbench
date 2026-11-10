# 28. Evidência científica, capítulos de resultados e publicação

[English](../en/28_evidencia_publicacion.md) · [Español](../es/28_evidencia_publicacion.md) · [Português](../pt/28_evidencia_publicacion.md)

## Escrever resultados verificáveis

Um artigo descreve observações, metadados, transformações, parâmetros, fontes de incerteza e critérios de aceitação. Preservar nomes de grandezas, unidades, sinais, fontes de coeficientes e limites. Citar biblioteca identifica um componente; não demonstra integração local correta.

Estrutura recomendada: resumo, introdução, dados/métodos, resultados, discussão, conclusões, disponibilidade e referências. Capítulos do manual têm objetivos/procedimentos; um estudo deve convertê-los na receita efetivamente executada.

## Contagens e partições

Informar separadamente linhas disponíveis, válidas, selecionadas, ajustadas e reservadas. Importar uma base grande não significa inverter todos os pontos. Reservar linhas/regiões antes de escolher regularização e malha. Comparação que reutiliza o mesmo operador direto não é validação física independente.

## Evidência existente

O repositório conserva campanhas públicas de processamento, inversão, extensões e recuperação. Conferir data, hash, dados e critério de cada uma. Testes de radônio preservam problemas de calibração/resíduos; algumas geometrias voxel livres preservam erros elevados de modelo. Falhas fazem parte da evidência, não são linhas descartadas para melhorar o resumo.

| Pergunta | Documento inicial |
| --- | --- |
| Processamento com dados externos | [Campanha pública](../../validation/reports/public_processing_benchmark.md) |
| Reprodução de inversão pública | [Benchmark de inversão](../../validation/reports/public_inversion_benchmark.md) |
| Solver e não unicidade | [Convergência](../../validation/reports/inversion_convergence_resolution.md) |
| Recuperação condicionada/livre | [Protocolo voxel](../../validation/reports/voxel_recovery_validation.md) |
| Métodos elétricos, EM e SP | [Validação de métodos](../../validation/reports/inversion_methods_validation.md) |
| MVI e direções | [Referências](../../validation/reports/mvi_reference_validation.md), [aceitação](../../validation/reports/mvi_acceptance.md) |
| Arquivos de métricas | [Índice de benchmarks](../../validation/records/README.md) |

## Figuras e tabelas

Gerar figuras a partir de artefatos salvos, preservar scripts e declarar semente em dados artificiais. Distinguir pontos, grade interpolada, seção de modelo, diagrama conceitual e captura da GUI. Toda figura precisa de legenda, unidades e suporte. Informar escalas de cor recortadas: resíduos cortados podem esconder extremos.

Artigos usam Markdown, imagens vinculadas e tabelas de parâmetros/métricas. Não gerar PDFs automaticamente. Verificar links, fontes e se as capturas pertencem a uma execução real.

## Licenças, dados e responsabilidade

A licença do software não concede direitos sobre dados/relatórios de terceiros. Downloads públicos podem ter condições próprias. Antes de publicar, revisar licença, atribuição, identificadores, integridade e se podem ser redistribuídos bytes ou apenas a receita de download.

Manter dados privados de aquisição, caminhos pessoais, credenciais, relatórios internos e imagens de locais fora da distribuição pública. Estas capturas usam valores artificiais CC0; futuras imagens de dados reais exigem revisão separada de direitos. Autoria, afiliação, financiamento e conflitos pertencem aos autores e devem ser confirmados, não deduzidos de um usuário Git.

Capacidades/benchmarks futuros permanecem pendentes até serem executados. Backlog propõe trabalho; não lista funcionalidades concluídas. Ver [cobertura histórica](../../handbook/roadmap_cobertura.md), [licenças](../../legal/THIRD_PARTY_LICENSES.md) e [fontes do manual](../es/fuentes.md).

---

[Índice](README.md) · [Anterior](27_tutoriales.md)

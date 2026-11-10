# 26. Recursos, testes, empacotamento e manutenção

[English](../en/26_recursos_desarrollo.md) · [Español](../es/26_recursos_desarrollo.md) · [Português](../pt/26_recursos_desarrollo.md)

## Evitar estimativas enganosas

N linhas e M canais float64 exigem no mínimo 8NM bytes em arrays densos, antes de máscaras, cópias, índices e buffers. Sensibilidades dependem também dos dados e parâmetros. Orçamento de arquivo, matriz ou interações não é memória total do processo nem garantia de duração.

Usar leitura seletiva por colunas, lotes, grades limitadas e orçamentos explícitos. Capacidade de armazenamento difere da capacidade de um kernel que recebe arrays inteiros. Alguns módulos de exploração, FFT e espectros precisam da grade completa mesmo com base lida em lotes.

## Ambiente reproduzível

Registrar Python, plataforma, versões, executável e extras. Reutilizar bibliotecas nativas compatíveis. Separar caches compartilháveis de temporários por projeto/execução. O desenvolvimento local usa lançadores e bloqueios; evitar escritores simultâneos no mesmo catálogo/pacote.

Não apagar parciais/caches rotineiramente enquanto processos ou referências dependerem deles. Conservar originais, receitas e artefatos de falha para diagnóstico. Sincronizar pasta não equivale a backup transacional SQLite/Parquet.

## Controles do repositório

| Controle | Objetivo |
| --- | --- |
| pytest | Contratos e regressões definidos em cada teste |
| Ruff | Verificações estáticas configuradas |
| check_core_install.py | Instalar wheel e operar sem checkout/host |
| check_localization.py | Catálogos e frases escritos em três idiomas |
| export_handbook.py --check | Manual prático coerente com fonte da GUI |
| build_manual_reference.py --check | Cobertura por capítulo e inventário AST atual |
| check_manual.py | Links, imagens, formato e separação de evidência |
| package_plugin.py | Metadados e conteúdo permitido do ZIP |
| Testes qgis_*.py | Integração QGIS offscreen real |

Aprovação significa atender aos critérios daquele controle e ambiente. Datas/contagens históricas não certificam outra versão atual. Capturas precisam corresponder à fonte e aos dados declarados, não a desenhos apresentados como execução.

## Contribuir sem duplicar motores

Kernels numéricos ficam em terraworkbench_core, widgets em ui e adaptadores em qgis_plugin/algorithms. Preservar imports históricos via compat, sem copiar implementações. Atribuir novos módulos a capítulos e atualizar inventário, dependências e testes pertinentes.

O pacote do plugin usa listas permitidas. Documentos/imagens novos precisam de inclusão e limite de tamanho, sem incorporar dados, credenciais ou relatórios internos. A distribuição independente contém o pacote científico, não toda a interface.

Ver [organização](../../development/repository_structure.md), [responsabilidade do Core](../../validation/README.md), [qualidade](../../validation/README.md) e [empacotamento](../../../scripts/package_plugin.py).

## Implementação relacionada

[_array_contract](../../../terraworkbench_core/_array_contract.py)

---

[Índice](README.md) · [Anterior](25_api_workflows.md) · [Próximo](27_tutoriales.md)

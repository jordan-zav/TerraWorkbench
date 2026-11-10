# Fontes, versões e política de citações

[English](../en/fuentes.md) · [Español](../es/fuentes.md) · [Português](../pt/fuentes.md)

[Índice do manual](../es/README.md)

## Prioridade de fontes

As capacidades do TerraWorkbench são verificadas primeiro na implementação e nos contratos. Referências metodológicas explicam contexto; campanhas vinculadas documentam o que foi testado. Não se atribuem automaticamente ao Core todas as capacidades de dependências nem se trata referência geral como validação independente do código.

Assinaturas vêm dos módulos Python e IDs do Core de seu registro. Os hashes de fonte são normalizados para LF, permitindo verificação em Windows/Linux. O catálogo QGIS vem de provedor efetivamente registrado e declara a versão do ambiente.

Definições sem docstring recebem notas editoriais separadas. A referência mostra também campos anotados das classes de opções. SVG é verificado como texto normalizado para LF e PNG como bytes exatos, evitando confundir alterações de fim de linha do Git com mudanças gráficas. Docstrings e identificadores técnicos preservam idioma original; navegação e notas complementares seguem o idioma escolhido.

## Referências primárias consultadas nesta edição

Revisão documental: 6 de novembro de 2026. Páginas latest/stable podem mudar; reprodução exige também versões efetivas registradas na execução.

| Referência | Uso no manual | Alcance |
| --- | --- | --- |
| [GDAL: raster data model](https://gdal.org/en/stable/user/raster_data_model.html) | Georreferenciamento, bandas e máscaras | Contrato raster, não validação completa do importador local |
| [PROJ: geodetic transformation](https://proj.org/en/stable/usage/transformation.html) | Projeção e transformação de datum | Contexto geodésico, não certificação de alturas privadas |
| [SciPy: sosfiltfilt](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html) | Filtragem forward/backward e bordas | Operador de biblioteca, não seleção científica de cortes |
| [Harmonica: prism_gravity](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html) | Prismas, componentes e unidades | Contrato do motor físico |
| [IAGA / NOAA: IGRF](https://www.ncei.noaa.gov/products/international-geomagnetic-reference-field) | Campo principal e coeficientes | Modelo principal, não anomalias locais |
| [SimPEG](https://simpeg.xyz/) | Estrutura de simulação/inversão | Capacidade da biblioteca difere dos adaptadores locais |
| [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf) | Contexto de espectrometria gama/calibração | Guia metodológico, não calibração universal |

A bibliografia específica de Euler, Werner, SPI, micronivelamento, flexura, fase, perfis e formas de onda IP permanece nos guias especializados vinculados. O [manifesto do manual prático](../../handbook/handbook_sources.json) relaciona fichas e fontes. Entradas históricas não representam nova auditoria de cada conteúdo ou licença.

## Evidência e resultados

Diagramas conceituais, controles artificiais, capturas da GUI com dados sintéticos, testes de contratos e benchmarks físicos são identificados separadamente. Cada métrica científica deve apontar a resultado e critério de aceitação. As capturas públicas mostram widgets reais com exemplos artificiais CC0 incluídos, não um levantamento de campo, validação geológica ou nova inversão.

O [arquivo de benchmarks](../../validation/records/README.md) conserva resultados e limitações. Antes de citar, ler protocolo, data, hash, definição de erro e se a geometria estava fixa. Precisão do solver, ajuste de dados e recuperação são perguntas diferentes.

## Manutenção da documentação

Novo módulo exige capítulo e referência regenerada. Mudanças de assinatura/registro devem reprovar a verificação de atualização. Atualizar exemplos e declarar o que foi reexecutado; não reescrever contagens históricas como se recalculadas com fonte nova.

O manual completo não altera automaticamente o manual curto da GUI. Sua fonte continua em ui/knowledge_content.py, com exportador e verificação próprios. Alterações científicas destinadas à interface exigem textos EN/ES/PT e contratos correspondentes. Os capítulos traduzidos compartilham IDs e manifesto de revisão; paridade estrutural é controle de manutenção, não certificação de tradutor científico independente.

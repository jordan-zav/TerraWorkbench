# TerraWorkbench: manual completo por capítulos

[English](../en/README.md) · [Español](../es/README.md) · [Português](../pt/README.md)

Edição em português · revisão de 6 de novembro de 2026.

Este manual desenvolve desde o início conceitos, procedimentos, contratos e limites dos módulos disponíveis. Complementa o manual prático EN/ES/PT da interface e as campanhas científicas existentes. Documentação não é nova campanha de campo nem declaração de que toda a geofísica esteja resolvida.

## Como usar

Seguir os capítulos em ordem para aprender o ambiente, ou consultar uma disciplina e retornar às convenções compartilhadas. Os capítulos 15 a 17 distinguem modelo, ajuste, convergência e recuperação. APIs experimentais e integração especializada pendente são identificadas no contexto.

Assinaturas completas são extraídas do código. Docstrings originais preservam idioma técnico; notas editoriais, títulos e navegação têm edições ES/EN/PT. IDs, canais, chaves e equações não mudam na tradução.

## Capítulos

| # | Tema |
| ---: | --- |
| 01 | [O que é o TerraWorkbench e como começar](01_inicio.md) |
| 02 | [Instalação, dependências e ambiente](02_instalacion.md) |
| 03 | [Coordenadas, unidades, alturas e convenções](03_coordenadas.md) |
| 04 | [Importação de texto, GRD e dados geoespaciais](04_importacion.md) |
| 05 | [Workspaces, canais, versões e linhagem](05_bases_canales.md) |
| 06 | [QC, trajetória, tempos e correções de aquisição](06_perfiles_qc.md) |
| 07 | [Cruzamentos, nivelamento e interpolação](07_nivelacion_gridding.md) |
| 08 | [Filtros espaciais, máscaras e mosaicos](08_filtros_espaciales.md) |
| 09 | [FFT, continuação, derivadas e análise espectral](09_fft_espectros.md) |
| 10 | [Magnetometria, campo principal e fontes compactas](10_magnetometria.md) |
| 11 | [Gravimetria terrestre, redes e modelos 2D](11_gravimetria.md) |
| 12 | [Terreno, isostasia, flexura e tensores](12_terreno_isostasia.md) |
| 13 | [Radiometria gama, espectros e radônio](13_radiometria.md) |
| 14 | [Atributos estruturais e profundidade de fontes](14_estructura_profundidad.md) |
| 15 | [Modelagem e inversão de gravidade e suscetibilidade](15_inversion_potencial.md) |
| 16 | [MVI, inversão conjunta e hipóteses estruturais](16_mvi_conjunta.md) |
| 17 | [Convergência, resolução, incerteza e validação](17_resolucion_incertidumbre.md) |
| 18 | [Resistividade DC, geometria ABMN e PDE](18_electrica_dc.md) |
| 19 | [IP, SIP, Cole–Cole e histórico de corrente](19_ip_sip.md) |
| 20 | [FDEM, TEM, transientes e magnetotelúrica](20_em_mt.md) |
| 21 | [Potencial espontâneo e redes de referência](21_potencial_espontaneo.md) |
| 22 | [GPR, traços sísmicos e sondagens](22_ondas_sondeos.md) |
| 23 | [Integração multifonte e métodos experimentais](23_integracion_experimentos.md) |
| 24 | [Interface QGIS, formulários, idiomas e capturas](24_gui_qgis.md) |
| 25 | [API Python, trabalhos e workflows reproduzíveis](25_api_workflows.md) |
| 26 | [Recursos, testes, empacotamento e manutenção](26_recursos_desarrollo.md) |
| 27 | [Tutoriais reproduzíveis desde o início](27_tutoriales.md) |
| 28 | [Evidência científica, capítulos de resultados e publicação](28_evidencia_publicacion.md) |

## Referências e material de apoio

- [Referência de API](../../reference/api/pt.md)
- [Inventário estruturado](../../reference/api/core_inventory.json)
- [Notas editoriais de API](../../reference/api/notes/pt.json)
- [Catálogo QGIS](../../reference/catalogues/qgis_pt.md)
- [Fontes e política de citações](fuentes.md)
- [Exemplos executados](../_meta/examples.json)
- [Capturas reais do Canadá](../_meta/captures.json)
- [Índice geral](../../README.md)
- [Manual prático](../../handbook/handbook_pt.md)

## Imagens e reprodutibilidade

As figuras usam links relativos aos recursos do idioma: dois diagramas conceituais, duas demonstrações numéricas controladas e duas capturas reais, do workspace sintético incluído e do leitor de capítulos. Estas imagens não redistribuem um levantamento real. Scripts e exemplos permanecem no repositório; Matplotlib está no extra documentation.

A leitura exige apenas a árvore documental; links de código precisam do checkout completo. Não são gerados PDFs. Relatórios históricos permanecem no idioma original com métricas e datas intactas.

## O que significa completo

Todo módulo Python de terraworkbench_core tem capítulo na cobertura compartilhada. As três edições têm os mesmos 28 IDs, seções, tabelas e links técnicos verificados por manifesto de paridade. Isso verifica cobertura documental e correspondência estrutural, não validação científica universal ou estabilidade de toda função.

Avaliar cada área com contratos, referências, testes e resultados. Datas e contagens históricas não certificam revisões posteriores.

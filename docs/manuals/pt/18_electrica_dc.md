# 18. Resistividade DC, geometria ABMN e PDE

[English](../en/18_electrica_dc.md) · [Español](../es/18_electrica_dc.md) · [Português](../pt/18_electrica_dc.md)

## Dados e geometria

Uma medida DC combina eletrodos de corrente A/B, potencial M/N, corrente e diferença de potencial. Resistência de transferência V/I está em ohms. O fator geométrico a converte em resistividade aparente sob geometria/meio de referência; não transforma uma observação em resistividade verdadeira de célula.

validate_abmn, geometric_factor, apparent_resistivity e reciprocal_errors verificam geometria, polaridade e reciprocidade. Preservar coordenadas e configuração, incluindo eletrodos remotos conforme o contrato. Fatores grandes podem amplificar ruído. Reciprocidade avalia consistência, não determina sozinha a distribuição de condutividade.

## Terra estratificada

dc_layered e fit_dc_resistivity usam resistividades e espessuras explícitas. Há uma espessura a menos que camadas quando a última é semiespaço. Um bom ajuste 1D exige compatibilidade com a hipótese lateral; não prova ausência de estrutura 2D/3D.

Comparar sensibilidade a espessuras, separações e ruído. Informar espessuras fixadas: as resistividades ajustadas ficam condicionadas à geometria e aos seus limites.

## Simulação 2.5D e 3D

electrical_pde usa malha tensorial e eletrodos ENU em metros. Em 2.5D, a seção usa X/Z e o levantamento fica em Y = 0. Condutividade em S/m, resistência de transferência em ohms e cargabilidade IP em V/V. Não há snapping/draping automático: posicionar eletrodos corretamente em relação à malha e ao terreno.

active_cells representa a terra fornecida; o ar inativo usa condutividade prescrita pelo módulo. Declarar parameter_labels para ajuste por zonas. Inversões zonais e celulares têm orçamentos e ambiguidades diferentes.

## Controles mínimos

Conferir malha, origem, extensão, unidades, resposta esperada de semiespaço e polaridade. Avaliar convergência da malha e tratamento transversal 2.5D. Inspecionar células ativas e posições antes de aumentar iterações para tentar corrigir um ajuste ruim.

Limites de células, parâmetros, trabalho e fatoração protegem a execução; não garantem capacidade regional. As APIs não implicam geração automática de malha, reconstrução topográfica ou seleção geológica certificada.

Ver [outros métodos de inversão](../../validation/reports/inversion_methods_validation.md), [alcance PDE](../../research/core_expansion_implementation.md) e [SimPEG](https://simpeg.xyz/). Consultar assinaturas atuais para distinguir observações, sigma e log-parametrização.

## Implementação relacionada

[electrical](../../../terraworkbench_core/electrical.py), [layered_electrical](../../../terraworkbench_core/layered_electrical.py), [electrical_pde](../../../terraworkbench_core/electrical_pde.py)

---

[Índice](README.md) · [Anterior](17_resolucion_incertidumbre.md) · [Próximo](19_ip_sip.md)

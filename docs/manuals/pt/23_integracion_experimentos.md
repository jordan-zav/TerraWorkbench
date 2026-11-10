# 23. Integração multifonte e métodos experimentais

[English](../en/23_integracion_experimentos.md) · [Español](../es/23_integracion_experimentos.md) · [Português](../pt/23_integracion_experimentos.md)

## Alinhar antes de combinar

stack_layers, rgb_composite, pca_fusion e anomaly_coincidence empilham ou comparam produtos. Exigem SRC, lattice, escala, máscara e unidades compatíveis. Normalização altera contribuições relativas: PCA em nT e mGal sem critério de escala pode representar principalmente a maior variância numérica.

shift_without_wrap desloca um array sem trazer valores pela borda oposta. Não é reprojeção, correção de trajetória ou registro subpixel com incerteza. Validar buscas de deslocamento com pontos/feições independentes.

multisensor_project coordena operações/publicação; terrain_analysis produz atributos de relevo. vector_grid_audit compara suporte de polígonos e grades. Conferir se estatísticas zonais não misturam máscaras, unidades ou pixels de borda de modo diferente entre produtos.

## Catálogos de anomalias

archaeology fornece exploração multiescala, regiões conectadas e retenção de feições. Os objetos são regiões limiarizadas do campo, não classes arqueológicas, idades ou identificações de UXO. Maior retenção da seleção inicial pode preservar ruído quando essa seleção não tem referência independente.

process_effect compara produtos GeoTIFF. Definir suporte comum, máscaras, transformações e diferenças de amplitude antes de interpretar uma métrica. Similaridade visual não basta para decidir qual filtro preserva melhor o sinal desejado.

## Pares de alturas e fusão direcional

paired_flights calcula diferenças de campos em superfícies compartilhadas e normaliza pela separação vertical. Conceitualmente:

    G_aparente = (T_alto − T_baixo) / (z_alto − z_baixo)

Exige alturas, baselines de campo, suporte horizontal e limiares de separação compatíveis. Voos com backgrounds retirados separadamente podem gerar pseudogradiente de anomalias locais, não gradiente vertical absoluto calibrado.

fuse_directions distingue suporte comum de cobertura disponível. Fazer média de duas direções onde ambas existem e manter uma onde só uma existe gera suportes distintos; preservar número e origem das contribuições. Essas capacidades não são recomendadas aqui como etapas obrigatórias do processamento básico.

Não se fornecem alturas, separações, sensores, locais ou parâmetros privados de aquisição. Experimentos históricos ficam separados das receitas genéricas e exigem validação específica antes da divulgação científica.

Ver [API completa](../../reference/api/pt.md), [limites de processamento](../../validation/reports/processing_overlap_audit.md) e [referências de integração](../../research/core_expansion_implementation.md).

## Implementação relacionada

[multisensor_fusion](../../../terraworkbench_core/multisensor_fusion.py), [multisensor_project](../../../terraworkbench_core/multisensor_project.py), [terrain_analysis](../../../terraworkbench_core/terrain_analysis.py), [vector_grid_audit](../../../terraworkbench_core/vector_grid_audit.py), [process_effect](../../../terraworkbench_core/process_effect.py), [archaeology](../../../terraworkbench_core/archaeology.py), [paired_flights](../../../terraworkbench_core/paired_flights.py), [crossovers](../../../terraworkbench_core/crossovers.py)

---

[Índice](README.md) · [Anterior](22_ondas_sondeos.md) · [Próximo](24_gui_qgis.md)

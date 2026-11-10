# 21. Potencial espontâneo e redes de referência

[English](../en/21_potencial_espontaneo.md) · [Español](../es/21_potencial_espontaneo.md) · [Português](../pt/21_potencial_espontaneo.md)

## Grandeza e referências

Potencial espontâneo é medido como diferença entre eletrodos. Seu nível depende da referência; combinar perfis sem resolver offsets pode criar estruturas artificiais. As APIs usam volts, metros, S/m e amperes conforme o modelo. Converter mV de aquisição para V antes do cálculo e preservar a unidade original na procedência.

adjust_reference_network trata diferenças de referências. Verificar conectividade, âncoras e fechamento de ciclos. Rede sem datum definido não é potencial absoluto. Mudanças eletroquímicas dos eletrodos e deriva instrumental precisam de informação adicional; resíduos pequenos da rede não as eliminam.

## Fontes prescritas em meio uniforme

prescribed_source_potential e invert_source_currents modelam fontes elétricas com condutividade conhecida, em espaço completo ou sob superfície horizontal isolante. Posição, intensidade e geometria pertencem ao problema. Não inferem diretamente fluxo de água, permeabilidade ou coeficiente eletrocinético de um mapa SP.

Geometria fixa reduz o problema inverso. Comparar sensibilidade à geometria, condutividade e referência antes de atribuir amplitudes a um processo físico. Modelos de fonte distintos podem produzir o mesmo campo de potencial.

## Condutor heterogêneo finito

self_potential_pde resolve uma equação da forma:

    −div(σ grad φ) = q

σ é condutividade isotrópica positiva prescrita por célula; q é fonte de corrente por volume em A/m³. Faces externas são isolantes. O domínio finito não equivale ao infinito aberto e exige balanço de fontes e referência coerentes. O módulo não acrescenta automaticamente ar/topografia com máscara ativa.

Avaliar sp_pde_forward e fit_sp_pde_sources frente a domínio, malha e fronteiras. Se mover o limite alterar significativamente previsões próximas às observações, a primeira solução não é evidência de estabilidade.

## Revisão prática

Preservar diferenças medidas, referências, tempos e controles de deriva. Verificar caso conhecido, balanço de corrente e unidades. Comparar resíduo espacial e regiões de baixa sensibilidade. Comunicar o resultado como ajuste de fontes sob condutividade e fronteiras prescritas.

Ver [contratos de outros métodos](../../validation/reports/inversion_methods_validation.md), [limites de implementação](../../research/core_expansion_implementation.md) e [referência de API](../../reference/api/pt.md).

## Implementação relacionada

[self_potential](../../../terraworkbench_core/self_potential.py), [self_potential_pde](../../../terraworkbench_core/self_potential_pde.py)

---

[Índice](README.md) · [Anterior](20_em_mt.md) · [Próximo](22_ondas_sondeos.md)

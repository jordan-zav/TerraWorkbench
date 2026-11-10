# 16. MVI, inversão conjunta e hipóteses estruturais

[English](../en/16_mvi_conjunta.md) · [Español](../es/16_mvi_conjunta.md) · [Português](../pt/16_mvi_conjunta.md)

## Diferenças em relação à suscetibilidade escalar

MVI permite componentes vetoriais de magnetização efetiva em vez de fixar a direção ao campo indutor. Aumenta parâmetros e ambiguidade. Melhor ajuste pode refletir maior flexibilidade, não direção geologicamente correta.

A representação cartesiana usa componentes por eixo. A esférica separa amplitude e ângulos e introduz dificuldades na amplitude nula e nos polos. Ao comparar/exportar, verificar se o campo é suscetibilidade efetiva SI ou magnetização A/m; nomes históricos sem sufixo mantêm convenções de compatibilidade documentadas.

## Controles do solver

Regularização vetorial, de amplitude ou por componentes impõe priors distintos. O esquema esférico possui etapa cartesiana e regras de carta para amplitude zero/polos. Azimute indefinido em um polo não é direção determinada.

Escalar amplitude SI e ângulos em radianos afeta o solve interno. Diagnósticos distinguem resíduos CG brutos e escalados; satisfazer um não implica satisfazer o outro. IRLS adaptativo é a referência do Core; estratégias com pesos congelados permanecem diagnósticos experimentais e podem esgotar orçamentos.

## Inversão conjunta

run_joint_cross_gradient_inversion combina gravidade e magnetometria com penalização de gradiente cruzado. Favorece relações estruturais sob o peso escolhido, mas não impõe relação petrofísica única. Regiões sem gradiente também afetam a interpretação do acoplamento.

Cada conjunto precisa de sigma, regional, componente e unidades próprios. Examinar os desajustes separadamente: soma baixa pode ocultar um conjunto mal explicado. Distinguir objetivo de dados, tolerância CG e critério externo de mudança de modelo. O Hessiano Gauss–Newton do gradiente cruzado e o modo histórico estabilizado mantêm diferenças de receita.

## Comunicar o estado atual

Relatórios do repositório incluem testes sintéticos, comparações e casos de recuperação reprovados. Não resumir como MVI resolvida ou inversão 3D encerrada. Geometria conhecida e voxels livres respondem a perguntas distintas.

Antes de interpretar, comparar modelos iniciais, referências, pesos estruturais, limites e resolução em um desenho previamente fixado. Reservar observações/geometrias para avaliação final. Mapas de resíduos, direção e amplitude devem acompanhar estados de convergência e limites físicos.

Ver [MVI esférica](../../reference/methods/spherical_mvi.md), [estabilidade](../../validation/reports/mvi_stability.md), [IRLS](../../validation/reports/lagged_irls.md), [sensibilidade externa](../../validation/reports/mvi_outer_sensitivity.md), [aceitação](../../validation/reports/mvi_acceptance.md) e [diagnóstico causal](../../validation/reports/mvi_causal_diagnosis.md).

## Implementação relacionada

[spherical_mvi](../../../terraworkbench_core/spherical_mvi.py)

---

[Índice](README.md) · [Anterior](15_inversion_potencial.md) · [Próximo](17_resolucion_incertidumbre.md)

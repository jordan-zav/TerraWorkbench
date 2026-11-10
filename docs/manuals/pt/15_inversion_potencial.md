# 15. Modelagem e inversão de gravidade e suscetibilidade

[English](../en/15_inversion_potencial.md) · [Español](../es/15_inversion_potencial.md) · [Português](../pt/15_inversion_potencial.md)

## Preparar o problema

A inversão exige observações, incertezas, coordenadas de receptores, malha, máscara ativa e relação física entre propriedade e resposta. O motor potencial usa metros e elevação positiva para cima. Declarar componente gravimétrica up ou down. Suscetibilidade usa TMI em nT e propriedade SI; o motor integral gravimétrico usa densidade em g/cm³.

Não inverter gravidade observada ou campo magnético total sem definir regional e correções apropriados. regional_prediction é retirado no espaço de dados; reference_model regulariza propriedades. São termos distintos, não substitutos.

## Objetivo e restrições

Uma formulação de referência combina desajuste e regularização:

    φ(m) = ‖Wd (F(m) − d)‖² + β φm(m, mref)

Wd depende de desvios padrão nas unidades dos dados. Escolher sigma arbitrário e depois afirmar que RMS ponderado ≈ 1 certifica ruído instrumental é incorreto. Regularização, beta, norma e referência fornecem informação ou preferências sobre o modelo.

run_potential_field_inversion aceita malha construída ou fornecida, células ativas, limites escalares/por célula, modelo inicial e referência. spatial_property_constraints e build_cell_difference_prior acrescentam hipóteses explícitas. Não derivar restrições geológicas da mesma anomalia e tratá-las depois como evidência independente.

## Discretização e memória

Definir célula, profundidade, padding e topografia antes do ajuste. Um receptor dentro de prisma ativo pode causar problemas físicos ou numéricos. A separação ar/terreno precisa ser coerente com a representação.

Para N dados e M parâmetros, sensibilidade escalar densa exige aproximadamente N × M × bytes_por_elemento. MVI acrescenta três componentes. RAM, disco e matrix_free trocam armazenamento, cálculo e I/O; matrix_free não elimina custo de avaliação nem garante execução mais rápida.

## Execução e exportação

run_inversion_workflow publica NPZ, VTK, CSV de dados e run.json em pasta nova. Conserva observações, sigma, regional, previsão, modelo e histórico. require_data_target pode exigir o objetivo de dados, mas execução concluída não demonstra recuperação geológica.

A saída gravimétrica escalar é contraste de densidade. Suscetibilidade negativa, se permitida, é contraste efetivo sob referência/regional adotados, não automaticamente uma propriedade absoluta medida.

## Geometria conhecida e geometria livre

fit_prism_density e fit_prism_magnetization estimam propriedades de prismas com geometria fixa. Essa condição reduz ambiguidade e difere de recuperar um corpo livre voxel a voxel. apparent_layer_property também condiciona a geometria de camada; estabilização e background devem ser declarados.

Ver [controles standalone](../../development/standalone_inversion.md), [regularização](../../reference/methods/regularization_conventions.md), [propriedades aparentes](../../reference/methods/apparent_properties.md), [recuperação](../../validation/reports/voxel_recovery_validation.md) e [SimPEG](https://simpeg.xyz/).

## Implementação relacionada

[inversion](../../../terraworkbench_core/inversion.py), [inversion_workflows](../../../terraworkbench_core/inversion_workflows.py), [spatial_constraints](../../../terraworkbench_core/spatial_constraints.py), [regularization_profiles](../../../terraworkbench_core/regularization_profiles.py), [prism_inversion](../../../terraworkbench_core/prism_inversion.py), [apparent_properties](../../../terraworkbench_core/apparent_properties.py)

---

[Índice](README.md) · [Anterior](14_estructura_profundidad.md) · [Próximo](16_mvi_conjunta.md)

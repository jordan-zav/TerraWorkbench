# 12. Terreno, isostasia, flexura e tensores

[English](../en/12_terreno_isostasia.md) · [Español](../es/12_terreno_isostasia.md) · [Português](../pt/12_terreno_isostasia.md)

## Modelo de terreno justificável

São necessários DEM, resolução, extensão, máscara, datum vertical e densidade ou contraste. Um DEM finito omite massas externas ao domínio. Maior detalhe não garante melhor correção se o receptor estiver mal localizado ou as alturas forem inconsistentes.

terrain_correction_prisms calcula seu termo definido como placa menos atração do DEM finito, com unidades e limites explícitos. terrain_gravity_adaptive calcula atração do contraste do DEM em estações, combinando prismas próximos e aproximações distantes. Não intercambiar saídas por semelhança de nomes: identificar atração, correção ou componente da redução completa.

## Custo e tolerância

O método finito histórico pode exigir trabalho quadrático no número de células. Blocos de receptores reduzem temporários, mas não as interações físicas. O método adaptativo permite aproximação controlada; avaliar tolerância, raio próximo, máscara e efeitos de borda em estações de teste.

Caso plano e prisma conhecido ajudam a verificar sinal e unidades. Em áreas extensas, examinar também a adequação da geometria plana. Uma API de prismas não implica solução regional esférica de terreno multirresolução para qualquer escala.

## Isostasia Airy

airy_root_thickness e airy_moho_depth produzem geometria de raiz sob compensação local, densidades e espessura de referência. isostasy calcula seu efeito por prismas ou FFT. O residual isostático depende do modelo escolhido; não é remoção observacionalmente única do campo profundo.

Formulações FFT têm periodicidade e tratamento de bordas; prismas finitos têm truncamento espacial. A comparação exige mesmo suporte, referência, densidades e sinais. Diferenças marginais, sozinhas, não demonstram erro de implementação.

## Flexura

thin_plate_flexure calcula resposta de placa com cargas e modelos reológicos explícitos; scan_elastic_thickness explora parâmetros. A relação conceitual D ∝ E Te³/(1 − ν²) mostra sensibilidade à espessura elástica. Uma varredura de Te com cargas/densidades fixas não estima simultaneamente toda a litosfera.

## Tensores

prism_gravity_tensor, rotate_tensor e tensor_invariants fornecem gradientes e mudanças de base. Registrar ordem de componentes, sistema ENU, matriz de rotação e unidades Eötvös. Rotação errada pode preservar alguns invariantes e ainda posicionar incorretamente as componentes. Evitar receptores nas singularidades do modelo.

Fontes: [prismas Harmonica](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html), [terreno adaptativo](../../reference/methods/adaptive_terrain.md), [isostasia](../../reference/methods/isostasy.md) e [referência de flexura GMT](https://docs.generic-mapping-tools.org/6.5/supplements/potential/grdflexure.html).

## Implementação relacionada

[terrain_gravity](../../../terraworkbench_core/terrain_gravity.py), [adaptive_terrain](../../../terraworkbench_core/adaptive_terrain.py), [terrain_tree_walk](../../../terraworkbench_core/terrain_tree_walk.py), [isostasy](../../../terraworkbench_core/isostasy.py), [flexure](../../../terraworkbench_core/flexure.py), [potential_tensors](../../../terraworkbench_core/potential_tensors.py)

---

[Índice](README.md) · [Anterior](11_gravimetria.md) · [Próximo](13_radiometria.md)

# 10. Magnetometria, campo principal e fontes compactas

[English](../en/10_magnetometria.md) · [Español](../es/10_magnetometria.md) · [Português](../pt/10_magnetometria.md)

## Identificar a grandeza de entrada

Campo total, anomalia residual ao IGRF e diferença entre sensores não são intercambiáveis. Subtrair novamente o campo principal de uma anomalia introduz erro de magnitude. Registrar estação-base, data e correções anteriores. Um nome comercial ou histórico do canal não descreve necessariamente seu conteúdo atual.

igrf_field calcula componentes Leste, Norte e Cima, campo total e elementos angulares via ppigrf. Entradas: longitude/latitude geodésicas, altura em quilômetros e data válida para os coeficientes instalados. O Core registra arquivo, hash e intervalo de épocas. Não reprojeta coordenadas nem converte datum vertical automaticamente. [IGRF representa o campo principal](https://www.ncei.noaa.gov/products/international-geomagnetic-reference-field), não anomalias locais.

## RTP, RTE e componentes

Por padrão, a RTP preserva a média da entrada nas células válidas. A saída com média zero é opcional. Na cadeia magnética, a opção afeta a grade RTP publicada; as derivadas e os demais produtos usam a mesma superfície de cálculo.

A redução ao polo ou equador transforma uma anomalia sob hipóteses de direção do campo e magnetização. Uma direção induzida pode ser insuficiente com remanência. Condições que produzem denominadores pequenos exigem estabilização; um mapa simétrico não certifica correção física.

magnetic_components oferece conversão de componentes e reconstrução de TMI a partir de gradientes com direções explícitas. Recuperação de modos fracos e nível médio depende das restrições do método; integrar gradientes não recupera necessariamente um datum absoluto medido. Documentar unidades e componentes não observáveis.

## Produtos de realce

| Produto | Destaque | Limitação |
| --- | --- | --- |
| Derivadas horizontais e THDR | Variação lateral | Sensibilidade a ruído e orientação |
| Derivada vertical | Ondas curtas | Amplifica erros de alta frequência |
| Amplitude do sinal analítico | Combinação de gradientes | Não é suscetibilidade |
| Tilt, theta e TDX | Contrastes e razões de gradientes | Instabilidade com denominadores pequenos |
| Pseudogravidade | Transformação sob modelo de fonte | Requer hipóteses; não é gravidade medida |

Unidades e restauração de tendência dependem do produto. Preservar uma grade corrigida sem realces como referência da modelagem quantitativa.

## Dipolos e objetos compactos

magnetic_dipole_field e fit_magnetic_dipoles fornecem cálculo direto e ajuste local de posições/momentos. Exigem geometria, intervalos iniciais, limites e observações suficientes. Um dipolo ajustado não classifica UXO nem determina risco, material ou idade. Verificar a aproximação frente ao tamanho do objeto e à distância do sensor.

Ver [componentes magnéticas](../../reference/methods/magnetic_component_api.md), [fontes compactas](../../reference/methods/compact_magnetics.md), [contratos de aquisição](../../development/standalone_acquisition.md) e [fontes metodológicas](../../research/PAPER_BACKED_MAGNETIC_METHODS.md).

## Implementação relacionada

[geomagnetism](../../../terraworkbench_core/geomagnetism.py), [magnetic_components](../../../terraworkbench_core/magnetic_components.py), [magnetic_pipeline](../../../terraworkbench_core/magnetic_pipeline.py), [magnetic_products](../../../terraworkbench_core/magnetic_products.py), [compact_magnetics](../../../terraworkbench_core/compact_magnetics.py)

---

[Índice](README.md) · [Anterior](09_fft_espectros.md) · [Próximo](11_gravimetria.md)

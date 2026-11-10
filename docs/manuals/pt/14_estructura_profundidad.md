# 14. Atributos estruturais e profundidade de fontes

[English](../en/14_estructura_profundidad.md) · [Español](../es/14_estructura_profundidad.md) · [Português](../pt/14_estructura_profundidad.md)

## Produtos matemáticos e interpretação

Gradientes, fase, textura e orientações ajudam a explorar contrastes. Uma borda calculada não é automaticamente falha, contato litológico ou corpo mineralizado. Registrar escala, filtro anterior e máscara distingue a interpretação do produto numérico que a motivou.

structural_attributes contém fase monogênica multiescala, textura local e entropia de orientações. Comprimentos de onda, largura de banda, limiar de ruído, intervalo de valores e origem dos bins afetam o resultado. A entropia axial reconhece que direções separadas por 180° podem representar o mesmo eixo. Textura de amostragem ou voo também pode gerar orientação dominante.

lineament_geometry converte esqueletos booleanos em caminhos. Máscara, espaçamento em metros e origem do primeiro pixel são explícitos. Ramificações, ciclos e extremidades não devem ser suavizados ou unidos sem registrar nova operação. Comprimentos dependem da representação de pixels e da conectividade.

## Euler

A equação de homogeneidade relaciona derivadas do campo, posição de fonte, fundo e índice estrutural. Uma forma habitual é:

    (x − x0) Tx + (y − y0) Ty + (z − z0) Tz = N (B − T)

Índice N, janela, derivadas, coordenadas e fundo precisam ser compatíveis. Uma nuvem de soluções pode refletir ruído, fontes misturadas ou mau condicionamento. euler_window, euler_grid e euler_profile não justificam aceitar tudo apenas porque o ajuste linear terminou.

## Werner e SPI

werner_profile e spi_profile dependem de hipóteses de fonte e geometria do perfil. Revisar modelo, janela, amostragem, altura e bordas. Profundidade obtida para contato difere em interpretação daquela de uma fonte cilíndrica. APIs de grade e perfil não compartilham automaticamente todas as hipóteses.

## Procedimento de interpretação

1. Definir a pergunta geológica e um modelo de fonte plausível.
2. Preparar campo com correções e unidades conhecidas.
3. Comparar escalas/janelas sem escolher apenas o resultado mais atraente.
4. Rejeitar suporte, intervalo ou condicionamento inadequados segundo critérios prévios.
5. Comparar dados independentes, terreno, cartografia e trajetórias.
6. Exportar catálogo de soluções e parâmetros, além da figura escolhida.

Ver [profundidade de fontes](../../reference/methods/source_depth.md), [atributos estruturais](../../reference/methods/structural_attributes.md) e suas referências específicas. Catálogos de profundidade são soluções de modelo, não observações diretas do embasamento.

## Implementação relacionada

[source_depth](../../../terraworkbench_core/source_depth.py), [structural_attributes](../../../terraworkbench_core/structural_attributes.py), [lineament_geometry](../../../terraworkbench_core/lineament_geometry.py)

---

[Índice](README.md) · [Anterior](13_radiometria.md) · [Próximo](15_inversion_potencial.md)

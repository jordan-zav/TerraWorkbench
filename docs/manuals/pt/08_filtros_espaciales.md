# 8. Filtros espaciais, máscaras e mosaicos

[English](../en/08_filtros_espaciales.md) · [Español](../es/08_filtros_espaciales.md) · [Português](../pt/08_filtros_espaciales.md)

## Espaço e frequência

Um filtro espacial opera em vizinhanças; um filtro FFT aplica transferência espectral. Alguns filtros lineares possuem representações relacionadas em ambos os domínios, mas a mediana é não linear e não tem uma transferência Fourier única. A mediana circular 2D difere da mediana de um canal 1D.

smooth_nine_point oferece a suavização binomial do TerraWorkbench. A API opcional smooth_least_squares_9x9 foi removida na versão 1.1.0 e sempre lança NotImplementedError; migre explicitamente para smooth_nine_point ou circular_median. São filtros diferentes, sem equivalência numérica declarada. circular_median usa suporte circular e tamanho conforme a API ou formulário. automatic_gain_control altera contraste local: a imagem realçada não preserva necessariamente a amplitude original para estimar propriedades físicas.

## Procedimento recomendado

1. Revisar resolução, orientação e máscara.
2. Escolher raio/janela coerente com amostragem e objetivo.
3. Salvar nova saída e receita, sem substituir a entrada.
4. Calcular diferenças entrada–saída e comparar estatísticas em suporte comum.
5. Examinar bordas e anomalias estreitas mesmo que a imagem pareça mais limpa.

O tratamento de vizinhos ausentes pertence a cada operação. Não preencher NoData com zero antes da mediana sem documentar. Ao comparar produtos, evitar que máscaras diferentes mudem silenciosamente quais observações entram no RMS.

## Filtragem direcional e wavelets

grid_tools fornece filtros direcionais, mosaicos e filtragem wavelet direcional. Registrar azimute, escalas, família wavelet, extensão de bordas e ganhos. Filtrar textura de voo não identifica ruído automaticamente: a geologia pode ter a mesma orientação.

O mosaico deve resolver explicitamente sobreposição, precedência, lattice, SRC e ausências. Não combinar amplitudes incompatíveis como observações equivalentes. Uma emenda suave pode ocultar diferença de datum.

## Revisão da saída

Medir intervalo, média, dispersão, fração finita e amplitude retirada. Comparar perfis cruzando feições em várias orientações. Se o filtro altera unidades ou normaliza amplitudes, informar nos canais e legendas. Separar imagens de exploração do sinal usado em modelagem.

Para parâmetros exatos, consultar a [referência de API](../../reference/api/pt.md), o [catálogo do provedor](../../reference/catalogues/qgis.md) e os [cuidados do manual prático](../../handbook/handbook_pt.md).

## Implementação relacionada

[basic_processing](../../../terraworkbench_core/basic_processing.py), [grid_tools](../../../terraworkbench_core/grid_tools.py)

---

[Índice](README.md) · [Anterior](07_nivelacion_gridding.md) · [Próximo](09_fft_espectros.md)

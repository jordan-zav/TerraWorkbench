# 13. Radiometria gama, espectros e radônio

[English](../en/13_radiometria.md) · [Español](../es/13_radiometria.md) · [Português](../pt/13_radiometria.md)

## Produtos e observações

Concentrações K, eU e eTh, taxas de contagem e espectros por canal são entradas diferentes. K costuma ser expresso em porcentagem; eU/eTh, em ppm equivalentes sob hipóteses de calibração e equilíbrio. Um RGB sozinho não preserva incerteza nem escala necessariamente comparável entre campanhas.

radiometry oferece razões seguras, taxa de dose terrestre, fator F, ternários e QC. O ternário usa K em vermelho, eTh em verde e eU em azul; registrar percentis e normalização. Razões exigem suporte suficiente no denominador. safe_ratio e limiares acumulativos evitam interpretar divisões por valores quase nulos como enriquecimento seguro.

## Calibrar contagens

1. Identificar integração temporal, tempo vivo e correções anteriores.
2. Aplicar o modelo pertinente de tempo morto ou vivo sem dupla correção.
3. Estimar e retirar fundos de instrumento, cósmico e radônio com calibração adequada.
4. Corrigir altura para uma referência justificada.
5. Resolver mistura de janelas/espectros com matriz de resposta calibrada.
6. Converter em concentrações e propagar incerteza sob hipóteses declaradas.

Para detector não paralisável, a correção de tempo morto é n = m/(1 − τm). Falha quando o denominador não é positivo. live_time_correction é diferente: exige tempo vivo medido e taxas normalizadas ao intervalo. Não combinar ambas rotineiramente.

## Espectros e covariância

energy_rebin e fit_energy_calibration tratam escala energética e redistribuição de bins. Integrar janelas exige limites energéticos e tratamento de covariância. fit_full_spectrum e spectral_unmix resolvem modelos distintos; documentar padrões, unidades, fundo e restrições.

NASVD e MNF reduzem ruído sob hipóteses estatísticas. Suavizar não cria informação energética; avaliar viés de amplitude, covariância e componentes negativas. fit_radiometric_response e radiometric_concentrations precisam de padrões e resposta instrumental pertinentes. Não existe sensibilidade universal para todo detector.

## Radônio: alcance real

Há correções por detector ascendente, janelas calibradas, espectro completo e proxy temporal com detectores emparelhados. Coeficientes e fundos exigem calibração; correlação ou solução algébrica não demonstram reconstrução atmosférica completa em campo. Examinar qui-quadrado, resíduos espectrais, componentes negativas e estabilidade temporal.

Padrões de laboratório e simulações não substituem condições aéreas, pressão, umidade, altura e geometria do sistema. Os relatórios existentes preservam essas limitações.

Leituras: [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf), [contratos de calibração e radônio](../../validation/reports/2d_extensions.md), [métodos implementados](../../research/core_expansion_implementation.md) e [campanha pública](../../validation/reports/public_processing_benchmark.md). A IAEA fornece contexto metodológico, não valida automaticamente coeficientes ou código locais.

## Implementação relacionada

[radiometry](../../../terraworkbench_core/radiometry.py), [radiometric_calibration](../../../terraworkbench_core/radiometric_calibration.py), [radiometric_spectra](../../../terraworkbench_core/radiometric_spectra.py), [radiometric_radon](../../../terraworkbench_core/radiometric_radon.py), [radon_corrections](../../../terraworkbench_core/radon_corrections.py)

---

[Índice](README.md) · [Anterior](12_terreno_isostasia.md) · [Próximo](14_estructura_profundidad.md)

# 11. Gravimetria terrestre, redes e modelos 2D

[English](../en/11_gravimetria.md) · [Español](../es/11_gravimetria.md) · [Português](../pt/11_gravimetria.md)

## Da leitura instrumental à anomalia

Começar identificando a entrada: leitura relativa, gravidade observada calibrada, distúrbio, anomalia de ar livre ou Bouguer. Resolver correções instrumentais e de movimento antes de interpretar uma anomalia como efeito do subsolo. Não deduzir o estado do processamento pelo nome do arquivo.

normal_gravity_grs80 retorna gravidade normal sobre o elipsoide GRS80 em mGal, pela fórmula de Somigliana. normal_gravity_somigliana aceita constantes explícitas; ao alterá-las, não rotular automaticamente o resultado como GRS80. Elevação do receptor e do terreno participam de termos distintos.

## Esquema de redução

Em uma convenção terrestre habitual, a anomalia Bouguer simples combina gravidade observada, normal, correção de ar livre e atração da placa:

    g_B_simples = g_observada − γ + C_ar_livre − C_placa

O termo de placa depende de densidade e altura do terreno; ar livre depende da altura de observação. Manter explícitos coeficiente da placa, unidades e referência de altura. land_gravity_reduction solicita esses elementos e produz procedência numérica.

A anomalia completa acrescenta terreno e, conforme a receita, curvatura ou outras reduções. Verificar sinal e definição de atração/correção recebida. Um distúrbio calculado com gravidade normal na altura correspondente não é idêntico a todas as definições de anomalia de ar livre.

## Redes e deriva

adjust_gravity_network estima uma rede com estações, instrumentos, tempos e referências. As âncoras fixam o datum; se forem incertas, não tratá-las depois como exatas nem descartar a covariância comum induzida. Deriva estimada não corrige automaticamente marés ou cargas não fornecidas.

fit_bouguer_density explora densidade sob relação estatística declarada. A associação anomalia–topografia pode refletir geologia além da densidade de redução. Examinar intervalos, resíduos e sensibilidade antes de adotar um único valor regional.

## Perfis poligonais

polygon_gravity_2d usa seção X/Z positiva para cima, densidade em kg/m³ e extensão infinita normal à seção. Retorna componente vertical positiva para baixo em mGal. fit_polygon_densities ajusta propriedades com geometria fixa; não recupera automaticamente vértices ou extensão lateral finita.

## Controles de aceitação

Conferir latitude, datum horizontal, alturas, escala instrumental, bases repetidas, deriva, ar livre, densidade e topografia. Examinar cada correção separadamente. Antes da inversão, confirmar componente para cima/baixo e se o dado é contraste em relação a um regional.

Ver [reduções e convenções](../../development/standalone_acquisition.md), [redes e perfis](../../validation/reports/2d_extensions.md) e [gravidade normal do Boule](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html). Defaults não substituem metadados do levantamento.

## Implementação relacionada

[gravity_corrections](../../../terraworkbench_core/gravity_corrections.py), [gravity_network](../../../terraworkbench_core/gravity_network.py), [gravity_profiles](../../../terraworkbench_core/gravity_profiles.py)

---

[Índice](README.md) · [Anterior](10_magnetometria.md) · [Próximo](12_terreno_isostasia.md)

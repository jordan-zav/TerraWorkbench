# 3. Coordenadas, unidades, alturas e convenções

[English](../en/03_coordenadas.md) · [Español](../es/03_coordenadas.md) · [Português](../pt/03_coordenadas.md)

## Contrato espacial

Operações de distância e Fourier precisam de unidades horizontais conhecidas. Um número como 500000 não identifica zona UTM nem datum. Atribuir SRC descreve coordenadas existentes; reprojetar calcula novas coordenadas. Alterar o rótulo do SRC não corrige uma transformação errada.

reproject_xy aceita SRC horizontais 2D, ordem XY explícita e rejeição de transformações aproximadas não autorizadas. Não transforma elevações. Se a melhor operação exigir grades de datum ausentes, investigar em vez de aceitar silenciosamente outra operação. O adaptador QGIS mantém seu próprio contexto de transformação.

## Alturas que devem permanecer distintas

| Grandeza | Uso típico | Cuidado |
| --- | --- | --- |
| Elevação elipsoidal | Posição GNSS | Não é altitude ortométrica |
| Elevação ortométrica | Terreno em relação ao geoide | Registrar o modelo geoidal |
| Altura acima do terreno | Separação sensor–solo | Exige posição do sensor e DEM compatíveis |
| Elevação do sensor | Coordenada Z do receptor | Pode diferir da antena ou plataforma |
| Separação entre sensores | Gradientes ou pares | Não substitui elevação absoluta |

Um sensor rebocado pode ter deslocamentos vertical e horizontal. Altura nominal documenta uma aproximação, não uma trajetória medida. Manter DEM, topografia e receptor em referenciais verticais compatíveis.

## Convenções físicas

O Core usa frequentemente Leste, Norte e Cima. Entretanto, sinais de componentes dependem da API: a inversão gravimétrica permite up ou down, o polígono gravimétrico retorna componente para baixo e o tensor MT usa eixos horizontais Norte/Leste. Consultar o contrato do módulo, não deduzir sinais de uma figura.

Em magnetometria, inclinação positiva para baixo e declinação a partir do norte verdadeiro nem sempre correspondem aos ângulos de uma malha projetada. Quando apropriado, usar D_grade = D_verdadeira − convergência meridiana e verificar o sinal projetando um rumo conhecido.

| Conversão | Relação |
| --- | --- |
| Gravidade | 1 mGal = 10⁻⁵ m/s² |
| Gradiente de gravidade | 1 Eötvös = 10⁻⁹ s⁻² |
| Campo magnético | 1 nT = 10⁻⁹ T |
| Densidade | 1 g/cm³ = 1.000 kg/m³ |
| Suscetibilidade | SI, adimensional |
| Cargabilidade | V/V; distinguir de mV/V |

## Raster, máscaras e pixels

Verificar dimensões, transformação afim, orientação das linhas, centros de pixel e NoData. Um raster norte-acima costuma ter passo Y geográfico negativo, embora a distância entre linhas seja positiva. As funções FFT recebem distâncias de amostragem; resolver antes a orientação física dos eixos.

Manter zero como dado válido quando pertinente. NaN e máscara não significam amplitude nula. Conferir também escala e offset das bandas para não filtrar inteiros armazenados em vez de grandezas físicas.

Fontes: [modelo raster GDAL](https://gdal.org/en/stable/user/raster_data_model.html), [transformações PROJ](https://proj.org/en/stable/usage/transformation.html) e [contrato independente de coordenadas](../../development/standalone_acquisition.md).

## Implementação relacionada

[coordinates](../../../terraworkbench_core/coordinates.py)

---

[Índice](README.md) · [Anterior](02_instalacion.md) · [Próximo](04_importacion.md)

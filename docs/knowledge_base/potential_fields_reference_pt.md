# Geofísica de Campos Potenciais — Referência Técnica

O TerraWorkbench reúne fluxos de magnetometria, gravimetria, filtragem espectral, preparação de levantamentos e inversão 3D dentro do QGIS. Cada operação declara seu domínio numérico, expõe os parâmetros físicos ou numéricos e produz saídas compatíveis com o QGIS.

Esta referência auxilia a interpretação, mas não substitui controle de qualidade do levantamento, controle geológico, análise de incerteza ou testes de sensibilidade.

## 1. Realces e derivadas magnéticas

### DX e DY — derivadas horizontais

**Fórmula:** DX = ∂T/∂x; DY = ∂T/∂y.

Realçam variações laterais associadas a contatos, falhas, diques e bordas de intrusões. A resposta depende da orientação da feição. Combine as duas componentes por meio do THDR e avalie a amplificação de ruído.

O TerraWorkbench oferece variantes por diferença finita espacial e por FFT explícita. As derivadas espaciais usam células vizinhas; as derivadas FFT multiplicam o espectro pelo operador de número de onda correspondente.

### DZ e DZ2 — derivadas verticais

**Fórmula:** DZ = ∂T/∂z; DZ2 = ∂²T/∂z².

As derivadas verticais realçam comprimentos de onda curtos e fontes rasas, mas amplificam fortemente ruído de alta frequência e efeitos de borda. Interprete DZ2 junto com geologia, sinal analítico e produtos de menor ordem.

### Continuação ascendente

**Fórmula:** T̂(h) = T̂(0) exp(−kh).

A distância de continuação é um parâmetro explícito nas unidades do SRC do raster. Distâncias maiores suprimem progressivamente os menores comprimentos de onda. Nenhuma distância é codificada no nome ou no ID Processing do algoritmo.

### Realce residual

**Fórmula:** Tres = T − TCA(h).

Subtrair um campo regional continuado para cima realça componentes mais rasas. A altura escolhida controla a separação regional/residual e deve ser documentada.

### THDR, Tilt, sinal analítico, TDX e Theta

- **THDR:** sqrt(DX² + DY²), útil para limites laterais.
- **Tilt:** atan2(DZ, THDR), normaliza amplitudes em um ângulo.
- **Amplitude do sinal analítico:** sqrt(DX² + DY² + DZ²), menos sensível à direção de magnetização que o campo original.
- **TDX:** atan2(THDR, abs(DZ)), medida de tilt horizontal voltada a bordas.
- **Mapa Theta:** atributo normalizado de derivadas para interpretação de bordas de fontes.

Esses produtos são atributos interpretativos, não estimadores únicos de profundidade ou litologia.

### Gradiente horizontal direcional

**Fórmula:** GH(α) = DX sin(α) + DY cos(α), com azimute α no sentido horário a partir do Norte geográfico.

O azimute é definido pelo usuário. Nenhum ângulo é codificado no nome ou no ID Processing. Compare diversos azimutes quando a orientação estrutural for incerta.

## 2. Transformações da direção do campo magnético

### IGRF-14

O modo automático calcula o IGRF-14 no centro do raster usando data do levantamento e altitude elipsoidal. O modo manual recebe inclinação e declinação diretamente. Verifique metadados, convenções de sinal e época do campo.

### Redução ao polo (RTP)

A RTP transforma as direções do campo indutor e da magnetização em direção a um campo vertical, de modo que as anomalias fiquem aproximadamente centradas sobre as fontes. É mal condicionada em baixas latitudes magnéticas e na presença de forte remanência; o TerraWorkbench expõe estabilização e ângulos remanentes opcionais.

### Redução ao equador (RTE)

A RTE é uma alternativa para baixas latitudes. Pode produzir respostas alongadas e não é automaticamente superior à RTP estabilizada. Compare ambas com a geologia e a orientação das fontes.

### Transformação geral da direção do campo

Transforma uma direção de campo de origem em inclinação e declinação alvo configuráveis. Usa uma função de transferência FFT 2D e retorna um GeoTIFF espacial.

## 3. Realce gravimétrico

DX, DY, DZ, DZ2, continuação ascendente, separação regional/residual, THDR, Tilt e amplitude do gradiente total seguem os mesmos princípios espaciais e espectrais dos equivalentes magnéticos. A gravidade responde ao contraste de densidade, não à magnetização. A separação regional/residual depende da escala e não é uma separação única por profundidade.

## 4. Correções e anomalias gravimétricas

### Gravidade normal GRS80 e distúrbio de gravidade

A gravidade normal é calculada pela latitude de cada pixel no elipsoide GRS80 com a fórmula de Somigliana. O distúrbio de gravidade subtrai esse campo de referência da gravidade observada. Deriva instrumental, marés terrestres e calibração devem estar resolvidas previamente.

### Correção e anomalia ar-livre

**Correção linear:** CAL = gradiente vertical × elevação geométrica.

O gradiente vertical é configurável. A elevação deve ter referência vertical e unidades documentadas.

### Placa de Bouguer, Bullard B e anomalia Bouguer simples

A aproximação de placa infinita usa densidade de redução e elevação. Bullard B representa a curvatura terrestre por uma aproximação de calota esférica. As hipóteses de densidade afetam materialmente as amplitudes e devem ser testadas.

### Correção de terreno e anomalia Bouguer completa

A correção de terreno usa prismas retangulares derivados de um MDE projetado. O MDE deve estar alinhado à grade gravimétrica, sem vazios e com extensão suficiente além da área de interpretação. O custo cresce rapidamente com o número de células; por isso há um limite de segurança.

O fluxo terrestre de Bouguer completa combina gravidade observada, gravidade normal GRS80, ar livre, placa de Bouguer, terreno e Bullard B com convenções de sinal explícitas.

### Moho de Airy e residual isostático

O modelo de Airy converte carga topográfica em espessura de raiz crustal usando densidades da crosta e do manto. O residual subtrai da anomalia Bouguer completa a resposta modelada da raiz. Teste profundidade de referência, densidades, extensão e resolução.

## 5. Filtros espectrais FFT

As ferramentas FFT transformam um raster projetado, completo e regularmente espaçado para o domínio do número de onda, aplicam uma função de transferência e fazem a transformada inversa.

O TerraWorkbench distingue:

- **ESPACIAL / DIFERENÇA FINITA:** operações entre células vizinhas.
- **FFT / HARMONICA:** operadores espectrais fornecidos pelo Harmonica.
- **FFT / TIPO MAGMAP:** motor espectral condicionado do TerraWorkbench.
- **MISTO GRADE / FFT:** atributos formados por componentes de mais de um domínio.
- **CORREÇÃO FÍSICA / GRADE:** reduções físicas avaliadas sobre células do raster.

### Condicionamento espectral

O motor tipo MAGMAP pode remover média ou plano, adicionar preenchimento refletido, aplicar taper na margem, combinar operadores compatíveis em uma única FFT direta, recortar a área original e opcionalmente restaurar a tendência. Isso reduz, mas não elimina, artefatos de borda.

### Funções de transferência disponíveis

- Butterworth passa-baixa, passa-alta, passa-banda e notch.
- Passa-banda e rejeita-faixa ideais, com aviso explícito de ringing.
- Passa-baixa e passa-alta com transição cossenoidal.
- Cosseno direcional de passagem e rejeição com rumo configurável.
- Continuação descendente estabilizada com controle de ganho.
- Integrações horizontal e vertical.
- Derivadas FFT explícitas nas direções leste, norte e vertical.

Comprimentos de onda e distâncias de continuação usam as unidades do SRC. Use um SRC projetado métrico quando os parâmetros forem definidos em metros.

## 6. Preparação e importação de levantamentos

O TerraWorkbench importa grades aceitas pelo GDAL, dados CSV/ASCII e conteúdo Esri FileGDB. No Windows, o runtime oficial BSD GX Developer lê GeoDatabase Geosoft de arquivo único sem Oasis montaj e exporta os dados para CSV/GeoTIFF/camadas QGIS abertas. Uma instalação do Oasis é apenas uma alternativa.

A interpolação de pontos expõe SRC projetado de saída, tamanho da célula, método, número de vizinhos e raio de busca. Raio zero preenche o retângulo completo para FFT, mas extrapola em áreas sem suporte.

O controle de cruzamentos e o nivelamento por linhas de amarração identificam interseções, rejeitam valores atípicos robustos e resolvem correções por linha. O micronivelamento direcional trata corrugação residual; não substitui correções de lag, variação diurna, heading ou linhas de amarração.

## 7. Inversão tridimensional

O TerraWorkbench fornece inversões SimPEG de densidade gravimétrica, suscetibilidade magnética, vetor magnético (MVI) e conjunta gravidade–magnetometria. Os fluxos TensorMesh e TreeMesh adaptativa expõem tamanho de célula, profundidade, padding, topografia, incertezas, limites, iterações e limites de segurança.

A inversão conjunta usa acoplamento por gradiente cruzado para favorecer similaridade estrutural sem impor uma razão fixa densidade–suscetibilidade. Execute testes de sensibilidade do peso de acoplamento e da malha. Os resultados são não únicos e devem ser avaliados contra geologia, geometria de aquisição e resíduos.

## 8. Lista mínima de verificação

1. Confirme SRC, unidades horizontais/verticais, espaçamento e cobertura NoData.
2. Preserve dados brutos e corrigidos com proveniência.
3. Avalie nivelamento de linhas e resíduos de cruzamentos antes da interpolação.
4. Teste padding, taper, comprimento de onda de corte e distância de continuação.
5. Compare derivadas espaciais e FFT quando o comportamento de borda for importante.
6. Documente direção do campo, época, densidade e hipóteses de magnetização.
7. Revise mapas residuais e testes de sensibilidade de toda inversão.
8. Não interprete um máximo filtrado como evidência única de profundidade, litologia ou mineralização.

## 9. Leitura aberta e confiável

A aba **Repositórios confiáveis** contém links diretos para Harmonica, Verde, Boule, Choclo, GMT, xrft, SimPEG, discretize, ppigrf, QGIS e outros projetos oficiais. Consulte a documentação e as licenças originais antes de reproduzir métodos ou código.

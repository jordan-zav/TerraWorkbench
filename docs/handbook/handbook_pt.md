# Manual prático do TerraWorkbench

Os mesmos capítulos, equações e links primários estão disponíveis em inglês, espanhol e português. As referências históricas de campos potenciais são preservadas separadamente. Este manual documenta hipóteses e controles; não afirma cobertura completa nem validação de campo.

## Importação GRD e fluxos de filtros

Importe a grade, confira coordenadas e unidades, escolha um filtro, edite seus parâmetros e execute a sequência. O leitor GRD binário Geosoft cria um GeoTIFF no destino escolhido; a origem permanece intacta. A extensão GRD sozinha não identifica a codificação. As saídas do fluxo são temporárias quando nenhuma pasta é selecionada. Uma pasta escolhida recebe uma subpasta por execução, receita e intermediários opcionais. Salvar a sequência permite reutilizar parâmetros, não certifica dados de entrada idênticos. Confira cada etapa antes de interpretar a imagem final.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

Contexto do capítulo:

- [GDAL raster data model](https://gdal.org/en/stable/user/raster_data_model.html)

## Coordenadas, unidades e dados ausentes

Atribuir um SRC descreve coordenadas existentes; reprojetar altera essas coordenadas. Não atribua outro SRC para corrigir dados mal posicionados. Registre unidades horizontais, referência de elevação e se a altura corresponde ao terreno, sensor ou afastamento do terreno. O processamento baseado em distâncias exige um SRC projetado métrico. O tamanho da célula e o espaçamento das amostras são diferentes. Confira máscaras NoData, orientação, centros de pixel e escala/deslocamento GDAL ao comparar rasters. Zero é uma medição, não um marcador automático de ausência. Um SRC local não certifica uma transformação de datum vertical.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

Contexto do capítulo:

- [GDAL raster data model](https://gdal.org/en/stable/user/raster_data_model.html)

## Bases de dados, canais e rastreabilidade

Preserve canais importados imutáveis e crie versões derivadas com unidades explícitas e nomes coerentes. O armazenamento combina um catálogo SQLite com dados Parquet por colunas; leia apenas os canais necessários. Confira delimitador, linha de cabeçalhos, separador decimal e ausências na importação. Os filtros devem respeitar linhas, lacunas e amostragem. Um limite de segurança por trecho não equivale à capacidade total da base. As receitas identificam versões e etapas. Reutilizar uma receita após substituir uma entrada exige revisão. A linhagem documenta o histórico, não garante correção científica.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

Contexto do capítulo:

- [GDAL raster data model](https://gdal.org/en/stable/user/raster_data_model.html)

## Interpolação e controle de linhas

Corrija tempos, estação-base e efeitos da aquisição antes de nivelar cruzamentos e interpolar. Examine resíduos por linha e direção. O tamanho de célula não recupera comprimentos de onda não amostrados. Compare métodos com validação espacial, não com vizinhos aleatórios que deixam vazar informação espacial. Registre raio, vizinhos, suavização e distância de exclusão. Um retângulo completo pode conter extrapolação sem suporte. Mascare células distantes e compare outros espaçamentos. Fontes equivalentes exigem profundidade, amortecimento e controles de memória; são uma representação interpolante, não um corpo geológico único. O micronivelamento não deve eliminar geologia paralela ao voo.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

### Propriedades aparentes de camada

Use uma grade completa com linhas que aumentam ao norte e colunas a leste. A camada contínua periódica tem profundidade do topo e espessura prescritas; o contraste de densidade é kg/m³ e a suscetibilidade é SI. Intensidade magnética, inclinação positiva para baixo e declinação a partir do norte da grade são explícitas. A inversa remove a média observada e adiciona o fundo escolhido. A regularização usa unidades de dados/propriedade e os limites de ganho suas recíprocas. Revise resíduos e recuperação espectral; direções ausentes e frequências suprimidas não são geologia recuperada. Não é o modelo proprietário de prismas infinitos nem suscetibilidade cgs. Não remove IGRF, corrige terreno ou certifica dados automaticamente.

m_hat(k) = conj(K) d(k) / (|K|² + lambda²)

Parâmetros / grandezas: kind, top_depth_m, thickness_m, background, regularization_response, max_inverse_gain, minimum_wavelength_m

Fontes de contexto:

- [Harmonica prism gravity: units and coordinate conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)
- [Harmonica prism magnetic field: conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_magnetic.html)

### Fase, textura e caminhos de feições

Os atributos básicos log-Gabor/Riesz usam comprimentos de onda, largura de banda e ruído explícitos; o alinhamento não é ponderado e não equivale à congruência de fase completa ou CET. A entropia quantizada depende de janela, intervalo e histograma. A entropia axial também depende da origem dos intervalos e suporte válido. Os caminhos exigem máscara booleana explícita, espaçamento projetado em metros e centro do primeiro pixel. Ramificações e ciclos mantêm geometria de pixel sem suavização ou união de lacunas. São feições matemáticas, não falhas ou litologias interpretadas.

H = -sum(p log2 p)

Parâmetros / grandezas: wavelengths_m, sigma_on_f, noise_threshold, value_range, bin_origin_degrees, feature_mask, origin_xy

Fontes de contexto:

- [Monogenic phase attributes](https://peterkovesi.github.io/ImagePhaseCongruency.jl/stable/functions/)
- [scikit-image morphology](https://scikit-image.org/docs/stable/api/skimage.morphology.html)

### Métodos de interpolação e suporte

IDW depende da potência da distância e dos vizinhos; o vizinho mais próximo não adiciona suavidade. Splines globais de placa fina e aproximações TPS locais diferem em suporte e custo. O solver multinível experimental de curvatura mínima é outro método, não uma promessa de equivalência proprietária. Interpolação sinc exige amostragem e suporte justificáveis. Avalie blocos espaciais reservados e documente extrapolação distante. Uma célula menor melhora visualização, não resolução da aquisição.

IDW: z(x) = sum(w_i z_i)/sum(w_i); w_i = distance_i^(-p)

Parâmetros / grandezas: METHOD, CELL_SIZE, NEIGHBORS, SEARCH_RADIUS, POWER, SMOOTHING

Fontes de contexto:

- [Verde spatial cross-validation](https://www.fatiando.org/verde/latest/tutorials/model_selection.html)

### Correções de aquisição e tempos

O lag com sinal altera a posição de uma observação no tempo/trajetória; documente sinal e estimativa com evidência repetível. Interpole a estação-base apenas no suporte temporal aceito. Coeficientes de rumo modelam resposta da aquisição e não devem absorver diferenças geológicas. A gravidade móvel exige época de deriva consistente, maré explícita e sinal Eötvös declarado. Preserve canais corrigidos e originais. Reamostragem, interpolação de lacunas e rotações são etapas separadas com registro.

Parâmetros / grandezas: LAG, BASE_TIME, BASE_VALUE, HEADING, DRIFT, TIDE, EOTVOS_MODE

Fontes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### Nivelamento com amarrações e micronivelamento

Cruzamentos restringem diferenças entre linhas de voo e amarração. Confira conectividade, distância de interseção e resíduos antes de ajustar correções constantes ou polinomiais. Não trate uma rede sem âncora como se tivesse datum absoluto. O micronivelamento direcional trata corrugação residual após correções primárias e cruzamentos. Compare a correção removida com a amplitude geológica; examine estruturas paralelas e transversais ao voo. Uma imagem mais limpa não demonstra por si só melhores medições.

Parâmetros / grandezas: LINE_ID, LINE_TYPE, TIE_VALUES, POLYNOMIAL_DEGREE, AZIMUTH

Fontes de contexto:

- [Minty (1991): Simple Micro-Levelling for Aeromagnetic Data](https://doi.org/10.1071/EG991591)

Contexto do capítulo:

- [Verde spatial cross-validation](https://www.fatiando.org/verde/latest/tutorials/model_selection.html)
- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)
- [Monogenic phase attributes](https://peterkovesi.github.io/ImagePhaseCongruency.jl/stable/functions/)
- [scikit-image morphology](https://scikit-image.org/docs/stable/api/skimage.morphology.html)

## Filtros FFT e seleção de parâmetros

Comprimentos de onda e alturas de continuação usam unidades do SRC. Compare cortes relacionados à amostragem e à escala-alvo. A ordem Butterworth controla a transição; uma ordem maior não é necessariamente melhor. Remover média/plano, adicionar preenchimento refletido e suavizar bordas modifica o comportamento marginal; registre isso e compare também o interior. A continuação para cima atenua ondas curtas. A continuação para baixo amplifica ruído e exige estabilização e limites de ganho. Restaure a tendência apenas quando fisicamente adequado. A mediana circular espacial trata picos isolados; é não linear e não é uma transferência Fourier. A base de dados não é um domínio numérico.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

H_up(k, h) = exp(-|k| h); k in rad / length; h > 0

### Tendência, preenchimento e suavização marginal

Remover média ou plano altera o conteúdo de número de onda zero/baixo. O preenchimento refletido reduz saltos, mas cria uma extensão artificial; a suavização pondera essa extensão antes da FFT. A inversa recorta à geometria original e recupera sua máscara. Restaurar tendência pode ser adequado em suavizações, mas geralmente não em uma derivada. Compare estatísticas de borda e interior separadamente e preserve os parâmetros de condicionamento na receita.

k = 2 pi / wavelength; Nyquist per axis = pi / spacing

Parâmetros / grandezas: FFT_DETREND_ORDER, FFT_PADDING_PERCENT, FFT_TAPER_PERCENT, FFT_RESTORE_TREND

Fontes de contexto:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

### Bandas Butterworth, ideais e cosseno

O kernel Butterworth espacial é definido diretamente no número de onda radial; não o confunda com o projeto digital temporal. Cortes de comprimento de onda longo e curto correspondem inversamente ao número de onda. A banda passante multiplica respostas baixa/alta; a rejeição complementa a banda. Bordas ideais geram oscilações; transições suaves trocam seletividade por menos oscilação. Compare corte e ordem, não apenas cores. O gaussiano tem outra transferência e não deve receber o mesmo nome.

B_LP = [1+(k/kc)^(2n)]^(-1/2); B_HP = [1+(kc/k)^(2n)]^(-1/2)

Parâmetros / grandezas: WAVELENGTH, LONG_WAVELENGTH, SHORT_WAVELENGTH, ORDER

Fontes de contexto:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

### Continuação e integração de derivadas

A continuação para cima é uma operação de banda baixa do campo potencial. A continuação para baixo estabilizada combina ganho exponencial, limite e suavização; limitar o ganho altera o operador ideal. Integrar uma derivada horizontal exige uma política no seu eixo de número de onda zero; uma constante não é recuperada apenas de derivadas. Documente piso ou estabilização e confira amplificação espectral. A pseudogravidade depende de magnetização e escala; não é uma observação gravimétrica absoluta.

H_up = exp(-|k|h); H_down = min(exp(|k|h),Gmax) B_LP; Ix = 1/(i kx)

Parâmetros / grandezas: HEIGHT, MAX_GAIN, LOWPASS_WAVELENGTH, ORDER

Fontes de contexto:

- [Harmonica upward continuation](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.upward_continuation.html)

### Mediana circular, suavização e ganho

A mediana circular usa uma vizinhança por distância em pixels; seu raio não é um comprimento de onda físico. Preserve ausências originais e confira mudanças em alvos isolados. A suavização de nove pontos aplica repetidamente um kernel local normalizado; as iterações alteram a suavização efetiva. O controle automático de ganho reescala amplitudes locais e não preserva uma escala magnética ou gravimétrica calibrada. Preserve um ramo quantitativo antes dos realces. Esses produtos não lineares/adaptativos não equivalem a uma única transferência FFT.

Parâmetros / grandezas: RADIUS, PASSES, GAIN_CAP, RMS_FLOOR

Fontes de contexto:

- [SciPy multidimensional image processing](https://docs.scipy.org/doc/scipy/reference/ndimage.html)
- [scikit-image morphology](https://scikit-image.org/docs/stable/api/skimage.morphology.html)

Contexto do capítulo:

- [Harmonica upward continuation](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.upward_continuation.html)
- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

## Derivadas magnéticas e direção do campo

DX e DY dependem da orientação das coordenadas; DZ depende do sinal vertical. Derivadas amplificam ruído de onda curta. Compare gradiente horizontal, amplitude do gradiente total e tilt com a anomalia original. RTP e RTE exigem direção do campo e uma direção de magnetização assumida. IGRF precisa de data e altitude; não substitua silenciosamente altitude do sensor por elevação do terreno. RTP em baixa inclinação pode ser instável mesmo com um mapa suave. Remanência pode invalidar uma interpretação apenas induzida. Um máximo não prova falha, profundidade ou litologia; confronte observações independentes.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

HGM = sqrt(DX² + DY²); TGA = sqrt(DX² + DY² + DZ²); tilt = atan2(DZ, HGM)

### Componentes e integração de gradientes

A conversão de componentes supõe um semiespaço harmônico sem fontes. Campo total significa projeção de anomalia pequena, não norma vetorial exata. Componentes de entrada e saída e média de saída são explícitas. A reconstrução usa derivadas leste, norte e para cima em nT/m, com pesos relativos positivos. A média de referência é prescrita. Revise ganhos, amortecimento, direções não resolvidas e eixos de Nyquist excluídos em grades pares. Uma tabela radial usa números de onda angulares em rad/m e ganho DC explícito; mantém seu ganho final após o último nó.

dT/dz_up = -k T; T(0) = prescribed mean

Parâmetros / grandezas: input_component, output_component, output_mean_nt, gradient_up, reference_mean_nt, wavenumbers_rad_per_m

Fontes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### Ajuste de dipolos compactos

Posições são ENU em metros e momentos A·m². Quantidade de fontes, sementes, erros independentes, limites e distância mínima ao sensor são prescritos. Ajuste componentes vetoriais ou projeção linear do campo total. Um otimizador convergente com jacobiano de posto deficiente não é um ajuste identificável bem-sucedido; a covariância local fica indisponível. Revise limites ativos e resíduos. A aproximação não identifica forma, classe UXO ou conteúdo explosivo.

B = mu0/(4 pi) [3 r (m·r)/r^5 - m/r^3]

Parâmetros / grandezas: observation_xyz, moments_a_m2, minimum_distance_m, rank_tolerance

Fontes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)
- [SimPEG](https://docs.simpeg.xyz/latest/)

### Derivadas espaciais e Fourier

DX e DY usam espaçamento de coordenadas, não índices de pixel. A primeira derivada para cima muda de sinal se a vertical positiva for para baixo. A diferenciação FFT supõe uma superfície horizontal regular e extensão periódica após o pré-processamento. Compare separadamente primeira e segunda derivada: a segunda amplifica mais os números de onda altos. Confira unidades de campo por comprimento ou comprimento ao quadrado. Revise independentemente bordas mascaradas e lacunas interpoladas.

Dx: i kx; Dy: i ky; Dz_up: -|k|; Dzz: |k|²

Parâmetros / grandezas: BAND, ORDER, spacing, padding_cells

Fontes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### Atributos de gradiente e angulares

O gradiente horizontal e a amplitude do gradiente total têm unidades físicas de derivada; tilt e atributos normalizados são ângulos ou razões adimensionais. Uma derivada horizontal direcional deve declarar referência do azimute e convergência das coordenadas. Normalizar pode realçar visualmente áreas fracas e ruidosas; examine uma máscara de amplitude junto aos atributos angulares. Picos se deslocam com geometria e interferência das fontes. Um limiar angular não classifica falhas sem evidência independente.

HGM = sqrt(Tx²+Ty²); TGA = sqrt(Tx²+Ty²+Tz²); tilt = atan2(Tz,HGM)

Parâmetros / grandezas: AZIMUTH, gradient_x, gradient_y, gradient_z

Fontes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

### RTP, RTE e direção IGRF

Distinga direção do campo indutor e magnetização da fonte. Data, altitude e posição geográfica determinam uma direção IGRF, não a componente remanente. Examine estabilização do ganho em baixa inclinação e compare direções próximas. A transformação não corrige nivelamento nem uma subtração incorreta do campo principal. Preserve a anomalia original e registre direções manuais ou calculadas. Transformações gerais e pseudogravidade dependem do modelo de magnetização assumido.

I > 0: downward; D: clockwise from geographic North

Parâmetros / grandezas: INCLINATION, DECLINATION, MAX_GAIN, SURVEY_YEAR, SURVEY_MONTH, SURVEY_DAY

Fontes de contexto:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

Contexto do capítulo:

- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)

## Correções gravimétricas e isostasia

Distinga gravidade observada, perturbação e anomalias. Registre latitude, referência de altura, época de deriva, marés, correção de movimento e densidade de redução. Confira o sinal antes de somar cada correção. Terreno, placa Bouguer e curvatura esférica não são intercambiáveis. Não corrija novamente anomalias Bouguer completas publicadas como se fossem observações brutas. A isostasia Airy supõe compensação local; a flexura admite suporte regional e exige parâmetros elásticos e bordas. Acompanhe a interpretação com sensibilidade à densidade e profundidade de referência. O residual depende do modelo; não mede automaticamente um excesso de massa crustal.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

CBA = SBA + terrain - Bullard B

### Atração adaptativa de um MDT finito

O modelo usa estações ENU explícitas, um MDT regular completo e um plano de referência prescrito. A rocha acima desse plano tem densidade da crosta; abaixo usa contraste água menos crosta. Células próximas mantêm prismas exatos. Grupos distantes conservam massa com sinal e centroide; as maiores cotas são refinadas até sua soma cumprir a tolerância em mGal. A cota exclui erros numéricos, de terreno, densidade, datum vertical, curvatura terrestre e terreno externo ausente. A saída é atração, não correção completa de terreno, Bouguer ou marés. Uma tolerância estrita pode exigir soma exata densa; os orçamentos não limitam RAM nem duração.

E_group <= 12 G 10^5 J / (d - R)^4; d > R

Parâmetros / grandezas: observation_xyz, reference_elevation_m, absolute_tolerance_mgal, leaf_cells, max_prism_evaluations

Fontes de contexto:

- [Barnes and Hut: hierarchical force calculation](https://doi.org/10.1038/324446a0)
- [Harmonica prism gravity: units and coordinate conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)

### Gravidade normal e redução de altura

O algoritmo GRS80 local avalia Somigliana na latitude da superfície elipsoidal de referência. Sua subtração de latitude não equivale a avaliar o campo normal na altura do sensor. O termo linear configurável de ar livre é uma aproximação separada. Registre a superfície de referência de cada termo antes de chamar o resultado de perturbação ou anomalia. Uma elevação geométrica não deve ser interpretada silenciosamente como altura ortométrica. Não combine convenções incompatíveis de produtos publicados.

gamma(phi) = gamma_e (1+k sin²(phi))/sqrt(1-e² sin²(phi)); FAA = g_obs-gamma(phi)+a h

Parâmetros / grandezas: ELEVATION, FREE_AIR_GRADIENT, INPUT, BAND

Fontes de contexto:

- [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html)

### Placa Bouguer, terreno e curvatura

A placa infinita remove uma massa idealizada entre datum e estação. Prismas de terreno representam relevo em relação à referência; Bullard B trata curvatura esférica na convenção terrestre implementada. São correções distintas com sinal, não filtros intercambiáveis. A densidade afeta cada termo de massa e deve ser consistente na sequência. Examine cobertura do MDE, afastamento do receptor, singularidades e sensibilidade de discretização. Uma correção com relevo incompleto não produz automaticamente Bouguer completa.

slab = 2 pi G rho h; SBA = FAA-slab; CBA = SBA+terrain-BullardB

Parâmetros / grandezas: CRUST_DENSITY, WATER_DENSITY, CLEARANCE, DEM, MAX_CELLS

Fontes de contexto:

- [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html)

### Compensação Airy e suporte elástico

A profundidade Airy usa contraste de densidade crosta/manto e Moho de referência; produz uma interface compensadora assumida, não um Moho sísmico observado. Calcule seu efeito gravimétrico antes do residual isostático. O kernel de placa elástica responde à pressão prescrita com bordas periódicas. Declare carga média, tamanho do domínio e constantes elásticas. Uma varredura de espessuras ajusta deslocamentos sob hipóteses fixas; não infere automaticamente incerteza geológica nem gravidade.

D = E Te³/[12(1-nu²)]; w(k) = q(k)/(D |k|⁴ + delta_rho g)

Parâmetros / grandezas: REFERENCE_MOHO, CRUST_DENSITY, MANTLE_DENSITY, elastic_thickness_m, load_pa

Fontes de contexto:

- [GMT grdflexure: elastic and rheological plate models](https://docs.generic-mapping-tools.org/6.5/supplements/potential/grdflexure.html)
- [Harmonica prism gravity: units and coordinate conventions](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)

Contexto do capítulo:

- [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html)
- [Harmonica transformations](https://www.fatiando.org/harmonica/latest/user_guide/transformations.html)
- [Barnes and Hut: hierarchical force calculation](https://doi.org/10.1038/324446a0)

## Radiometria e calibração do detector

Separe contagens, taxas e K/eU/eTh calibrados. Corrija observações brutas com coeficientes do levantamento para tempo morto, fundo, stripping, altura e sensibilidade; não reutilize coeficientes nominais sem revisão. Razões exigem proteção do denominador e máscaras compatíveis. Examine radônio, umidade e altura. Urânio equivalente supõe condições da cadeia de decaimento; não é química direta de urânio. O ternário é visualização, não medições independentes. Preserve incerteza e resíduos de calibração.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

### Contagens brutas versus produtos calibrados

Siga a sequência específica do detector e preserve canais de contagem originais. Tempo morto não paralisável, subtração de fundo, normalização de altura e stripping atuam em quantidades distintas. Uma grade de concentrações calibradas não deve receber novamente a sequência bruta. Examine valores corrigidos negativos sem cortá-los silenciosamente. Resposta de altura e sensibilidade exigem evidência de calibração/aquisição. Urânio e tório equivalentes dependem de hipóteses das séries de decaimento; razões e dose exigem unidades e máscaras compatíveis.

Parâmetros / grandezas: DEAD_TIME, BACKGROUND, HEIGHT, ATTENUATION, SENSITIVITY, RESPONSE_MATRIX

Fontes de contexto:

- [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf)

### Calibração espectral e covariância

Use vários picos de calibração para examinar não linearidade energética. Reagrupar distribui contagens fracionárias e correlaciona intervalos; variâncias diagonais não bastam. A sobreposição de janelas também produz covariância. NASVD e MNF exigem hipóteses explícitas de posto/ruído e podem produzir reconstruções negativas. A incerteza de calibração é compartilhada entre pontos mesmo quando apenas covariância marginal é retornada. Valide com registros independentes e preserve nomes, unidades e ordem da matriz de resposta.

E = offset+gain channel; Cov(Ax) = A Cov(x) Aᵀ

Parâmetros / grandezas: channel_peaks, energy_peaks, input_edges, output_edges, rank, rate_covariance

Fontes de contexto:

- [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf)

Contexto do capítulo:

- [IAEA-TECDOC-1363](https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf)

## Euler, Werner, SPI e profundidade espectral

As profundidades dependem do tipo de fonte assumido, amostragem e fundo. Em Euler varie índice estrutural, janela, derivadas e limites de aceitação. Rejeite janelas mal condicionadas e examine agrupamentos, não todos os candidatos como fontes. Werner/SPI de perfil não equivalem a uma inversão 3D arbitrária. Inclinações espectrais exigem um intervalo de frequências declarado e suporte estatístico; fontes misturadas e bordas enviesam a profundidade. Compare casos sintéticos, outras janelas e geologia. Essas técnicas não determinam de forma única o limite de um corpo nem reservas.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

(x-x0) Tx + (y-y0) Ty + (z-z0) Tz = N (B-T)

### Aceitação Euler e geometria de perfis

Use derivadas e coordenadas em unidades consistentes e z positiva para cima. Um índice estrutural zero não identifica um fundo arbitrário; a implementação estima o deslocamento de contato identificável. Condição, resíduo e erro de profundidade são critérios independentes de aceitação. Euler de perfil supõe fonte localmente bidimensional e não resolve localização ao longo do rumo. Preserve contagens de rejeições e compare índices, alturas e tamanhos de janela. Revise explicitamente soluções externas ao domínio observado.

(x-x0)Tx+(y-y0)Ty+(z-z0)Tz = N(B-T)

Parâmetros / grandezas: structural_index, window_size, stride, max_condition, max_relative_depth_error, depth_bounds

Fontes de contexto:

- [Harmonica Euler deconvolution](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.EulerDeconvolution.html)

### Werner, SPI e ajuste espectral

Werner supõe lâmina fina, polinômio de interferência declarado e observações niveladas. SPI usa picos de número de onda local; amostras fora dos picos não são profundidades independentes. Seus fatores geométricos diferem entre contatos, lâminas e cilindros horizontais. Profundidade espectral usa intervalo e expoente geométrico escolhidos; ajustar uma reta a tudo ignora populações misturadas. Compare picos, resíduos e sensibilidade ao intervalo. Fachadas por perfis não transformam essas hipóteses em reconstrução tridimensional geral.

K = abs((Tx Txz-Tz Txx)/(Tx²+Tz²)); SPI depth = (index+1)/K at peaks

Parâmetros / grandezas: background_degree, source_model, peak_distance, fit_range, geometry_exponent

Fontes de contexto:

- [Ku and Sharp (1983): Werner deconvolution](https://doi.org/10.1190/1.1441505)
- [Thurston and Smith (1997): SPI method](https://doi.org/10.1190/1.1444190)
- [Spector and Grant (1970): statistical aeromagnetic models](https://doi.org/10.1190/1.1440092)

Contexto do capítulo:

- [Harmonica Euler deconvolution](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.EulerDeconvolution.html)

## Inversão, resíduos e sensibilidade

Escolha explicitamente propriedade física, operador direto, malha, incertezas, limites e regularização. Separe posições do sensor e superfície topográfica. Repita variando célula, profundidade, extensão, modelo inicial/de referência e peso de regularização. Inspecione observados, preditos e resíduos por linha e localização, não apenas um desajuste escalar. Convergência não elimina não unicidade. O gradiente cruzado favorece similaridade estrutural, não uma relação fixa densidade–suscetibilidade. Motores opcionais e versões devem ficar na rastreabilidade. Um solver que atinge o máximo de iterações não deve ser rotulado como solução convergente.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

phi(m) = phi_d(m) + beta phi_m(m); r_i = (d_pred_i - d_obs_i) / sigma_i

### Densidade, suscetibilidade e MVI

A inversão de densidade estima contraste em relação à redução/referência. A inversão magnética escalar supõe direção de magnetização e parametrização de suscetibilidade; a vetorial admite componentes direcionais, mas aumenta a ambiguidade. A elevação do receptor não é por padrão a topografia das células ativas. Extensão, profundidade e limites físicos afetam a estrutura recuperada. Confira convergência separadamente da plausibilidade geológica e compare parametrizações. A geometria VTK é uma malha numérica, não um limite geológico mapeado independentemente.

Parâmetros / grandezas: CELL_SIZE, MODEL_DEPTH, MESH_TYPE, TOPOGRAPHY, LOWER_BOUND, UPPER_BOUND

Fontes de contexto:

- [SimPEG](https://docs.simpeg.xyz/latest/)
- [SimPEG L2 data misfit](https://docs.simpeg.xyz/latest/content/api/generated/simpeg.data_misfit.L2DataMisfit.html)

### Inversão magnética vetorial esférica

Uma inicialização cartesiana suave é refinada em amplitude e ângulos periódicos. As normas de amplitude e de gradientes angulares são escolhidas separadamente; normas esparsas exigem IRLS. Limites de magnitude diferem dos limites de componentes cartesianas. A elevação interna é positiva para cima e o azimute começa no Leste; as saídas preservam suscetibilidade efetiva cartesiana ENU. A direção é indefinida quando a amplitude é zero. Compare ajuste ponderado pelo ruído, precisão interna e recuperação do modelo separadamente. O suporte geométrico e as referências são hipóteses explícitas, não informações recuperadas automaticamente dos dados magnéticos. Ângulos coerentes não resolvem toda ambiguidade de profundidade ou volume.

m = a[cos(theta)cos(phi), cos(theta)sin(phi), sin(theta)]

Parâmetros / grandezas: mvi_parameterization, mvi_cartesian_iterations, mvi_amplitude_max, mvi_angle_norms, regularization_norms, irls_iterations

Fontes de contexto:

- [Fournier, Heagy and Oldenburg (2020), Sparse magnetic vector inversion in spherical coordinates](https://doi.org/10.1190/geo2019-0244.1)
- [SimPEG](https://docs.simpeg.xyz/latest/)

### Incerteza, IRLS e estrutura conjunta

A incerteza controla pesos e deve refletir erros de medição/modelo, não um ajuste-alvo arbitrário. O peso regularizador equilibra ajuste e hipóteses. Normas esparsas e IRLS alteram o problema; uma covariância linear gaussiana fixa não se aplica automaticamente depois. O gradiente cruzado favorece gradientes alinhados sem impor razão densidade/suscetibilidade. Teste pesos de acoplamento, distribuições residuais e referências. Mantenha explícita a falta de convergência; um modelo atraente não substitui experimentos de sensibilidade.

phi = phi_d+beta phi_m; cross-gradient = grad(m1) × grad(m2)

Parâmetros / grandezas: UNCERTAINTY, LP_NORM, IRLS_ITERATIONS, beta, regularization, reference

Fontes de contexto:

- [SimPEG](https://docs.simpeg.xyz/latest/)

Contexto do capítulo:

- [SimPEG L2 data misfit](https://docs.simpeg.xyz/latest/content/api/generated/simpeg.data_misfit.L2DataMisfit.html)
- [SimPEG](https://docs.simpeg.xyz/latest/)

## Resistividade DC, IP e potencial espontâneo

A resistividade DC exige geometria de eletrodos, polaridade de corrente, diferença de potencial e fator geométrico compatível. Resistividade aparente não é uma propriedade direta do voxel. Examine reciprocidade, contatos e topografia. IP e condutividade complexa precisam de convenções de frequência/tempo e sinal; unidades de cargabilidade não são intercambiáveis. Potencial espontâneo exige eletrodo de referência e sinal; separe o ajuste de fontes e bordas da interpretação. Modelos estratificados supõem invariância lateral. Modelagem e inversão PDE exigem sensibilidade de malha e bordas. Estas entradas experimentais não são um sistema instrumental completo.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

rho_a = K delta_V / I

### Geometria ABMN, IP e polaridade

ABMN armazena índices, não distâncias; B/N remoto usa o sentinela documentado. O fator de semiespaço exige plano de eletrodos compatível. Preserve sinais de tensão/corrente e sinalize resistividade aparente negativa, sem valor absoluto. O controle recíproco distingue quadripolos invertidos e repetições de mesma orientação. IP integrada é média normalizada da janela, não integral temporal sem normalização. Cole–Cole de resistividade exige sua convenção fasorial; parâmetros de condutividade não se tornam equivalentes ao renomeá-los. A inversão temporal também aceita históricos finitos prescritos de corrente com sinal, supondo polarização nula antes do primeiro evento. Informe cada mudança e escolha normalização DC ou pelo primário anterior ao desligamento final; dados e erros são V/V. A modelagem de empilhamentos exige selecionar intervalos sem corrente, pesos e uma convenção explícita de média de razões ou razão de somas. Ajusta dados V/V já empilhados sem inferir processamento instrumental nem redução de ruído. Prehistória desconhecida, filtros do receptor e indução exigem modelagem separada.

K_half = 2 pi/(1/AM-1/BM-1/AN+1/BN); rho_a = K V/I

Parâmetros / grandezas: electrodes, abmn, space, current_a, voltage_v, gate_s

Fontes de contexto:

- [SimPEG DC resistivity](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.static.resistivity.html)
- [Spectral induced polarization: frequency domain versus time domain laboratory data, Appendix C](https://doi.org/10.1093/gji/ggab071)
- [Understanding the Fate of H2S Injected in Basalts by Means of Time-Domain Induced Polarization Geophysical Logging](https://doi.org/10.1029/2023JB028316)

### Malhas PDE e fontes de potencial espontâneo

Use geometria da malha, regiões ativas, fontes/receptores e bordas explícitos. Em SP de fontes prescritas, a implementação usa faces externas isolantes e modelos individualmente neutros. Não equivale a semiespaço infinito nem interpretação eletrocinética automática. O ajuste de amplitudes mantém condutividade e geometria fixas. Confira distância às bordas, refinamento e eletrodo de referência. A covariância condicional exclui incerteza da condutividade, geometria das fontes e acoplamento hidráulico.

Parâmetros / grandezas: mesh_widths, mesh_origin, conductivity_s_m, source_templates_a_m3, reference_m

Fontes de contexto:

- [SimPEG DC resistivity](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.static.resistivity.html)

Contexto do capítulo:

- [SimPEG DC resistivity](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.static.resistivity.html)

## FDEM, TEM e magnetotelúrica

Registre geometria fonte/receptor, frequência ou forma de onda, componente, orientação e normalização. Importam os sinais em fase/quadratura e ppm versus campo absoluto em FDEM. Janelas TEM são integrais temporais finitas; use a forma de onda registrada e o tempo zero correto. Exclua explicitamente janelas contaminadas ou negativas. A impedância MT exige unidades elétricas/magnéticas e convenção Fourier antes de resistividade aparente e fase. Um modelo 1D não representa estrutura lateral arbitrária. Repita ajustes de condutividade com outros modelos iniciais e limites; um ajuste excelente não demonstra resolução em profundidade nem unicidade geológica.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

rho_a = |Z_EH|² / (mu0 omega); omega = 2 pi f

### EM estratificado e tridimensional

O modelo estratificado usa espessuras de camadas finitas e um semiespaço final. Momento, orientação e afastamento do receptor são explícitos. Campo secundário em tesla não equivale a ppm sem normalização primária justificada. Ajustar zonas 3D é um ajuste local limitado com orçamento de modelagens diretas, não inversão ilimitada de voxels. Teste extensão e condutividades iniciais; memória LU pode exceder estimativas simples. Erros real/imaginário correlacionados exigem a ordem de covariância declarada.

Parâmetros / grandezas: frequency_hz, thicknesses_m, source_m, receiver_m, moment_a_m2, data_covariance_t2

Fontes de contexto:

- [SimPEG electromagnetic methods](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.html)

### Janelas TEM e impedância MT

Desligamento ideal, rampas finitas e formas de onda registradas são histórias de fonte distintas. Integre janelas TEM finitas, não apenas seus centros; teste a ordem de quadratura. A impedância MT deve distinguir ohms E/H e unidades E/B. Preserve sinais xy/yx e não dobre a fase silenciosamente. O tensor de fase remove uma distorção galvânica ideal real à esquerda, mas não recupera amplitude da resistividade nem deslocamento estático. Ajustes estratificados mantêm espessuras fixas salvo parametrização explícita diferente.

rho_a = |Z_EH|²/(mu0 omega); Phi = Re(Z)^(-1) Im(Z)

Parâmetros / grandezas: gates_s, waveform_times_s, quadrature_order, impedance_ohm, thicknesses_m

Fontes de contexto:

- [SimPEG electromagnetic methods](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.html)

Contexto do capítulo:

- [SimPEG electromagnetic methods](https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.html)

## Georradar, formas de onda e sísmica passiva

Confirme eixo de amostras, intervalo, tempo zero e espaçamento de traços antes de filtrar. Dewow subtrai uma média temporal local; remover fundo compartilhado pode suprimir refletores horizontais reais. A banda passante deve respeitar Nyquist. Ganho altera amplitudes e não é inversão física. A profundidade do georradar exige velocidade justificável; migração exige geometria e hipóteses corretas. Em espectros passivos confira janelas, transientes, orientação e suavização. Um pico H/V não equivale automaticamente a uma espessura única. Preserve um ramo de amplitudes originais e compare traços, não apenas imagens realçadas.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

f_Nyquist = 1 / (2 dt); depth_GPR = velocity time_two_way / 2

### Condicionamento de traços, detecções e profundidade

As matrizes usam ordem traço por tempo. Dewow exige janela ímpar que caiba no registro; remover fundo atua entre traços, não no tempo. Butterworth temporal deve ficar abaixo de Nyquist e precisa de amostras suficientes para as bordas. Tempo zero, ganho e migração alteram informações distintas. NMO estica sinais; mascare estiramentos excessivos e documente cobertura. Detecções STA/LTA e picos H/V são indicadores para revisão, não classificações automáticas nem profundidades geológicas únicas.

0 < f_low < f_high < 1/(2 dt); depth = v t_two_way / 2

Parâmetros / grandezas: traces, dt_s, window_samples, low_hz, high_hz, maximum_stretch

Fontes de contexto:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

Contexto do capítulo:

- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

## Perfis de poço e transformações petrofísicas

Confira mnemônicos LAS, unidades, valores nulos, sentido da profundidade e metadados antes de escolher curvas. Separe profundidade medida e vertical verdadeira. Reamostragem e deslocamentos devem preservar intervalos nulos e ser documentados por curva. Transformações petrofísicas exigem hipóteses da formação, fluidos e calibração. Equações do tipo Archie não corrigem universalmente argilas. Não infira unidades de porosidade apenas pelas magnitudes. Compare curvas transformadas com originais e laboratório independente. Exportar LAS atualizado deve preservar curvas não modificadas e metadados; uma exportação correta não valida o modelo geológico.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

### Unidades LAS, trajetória e reamostragem

Amostras LAS preservam unidades originais; a saída de profundidade apenas converte metro/pé explícitos ou uma substituição registrada. Atualizar curvas não autoriza alterar a coluna de profundidade. Reconstruir trajetória exige boca do poço, profundidades medidas e convenções de orientação. Não confunda profundidade medida e vertical verdadeira. Preserve nulos e reversões para controle antes de reamostrar. Deslocamentos devem usar intervalos de correlação justificáveis, não apenas maximizar coincidência entre formações diferentes.

international foot = 0.3048 m

Parâmetros / grandezas: text, depth_unit_override, curve_values, collar_enu_m, measured_depth_m

Fontes de contexto:

- [lasio documentation](https://lasio.readthedocs.io/en/latest/)
- [Taylor (1972): well surveying calculations](https://doi.org/10.2118/3362-PA)

Contexto do capítulo:

- [lasio documentation](https://lasio.readthedocs.io/en/latest/)

## Validação, rastreabilidade e conclusões prudentes

Separe testes unitários, comparação numérica, testes de GUI e validação de campo. Aprovar um caso sintético não estabelece equivalência comercial. Arquive receita, versões ou hashes das entradas, unidades, parâmetros, versões de bibliotecas e estatísticas residuais. O hash de um módulo não cobre dependências transitivas. Distinga tarefas concluídas, falhas, canceladas e sem convergência. Limites de saída não limitam RAM nem tempo do solver. Cancelar pode aguardar um ponto de controle. Confira sensibilidade em intervalos justificáveis e documente diferenças pendentes. Mantenha levantamentos privados e aquisição fora de documentação e pacotes públicos.

Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.

Contexto do capítulo:

- [SimPEG](https://docs.simpeg.xyz/latest/)

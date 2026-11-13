"""Equivalent, authored EN/ES/PT handbook. No Qt or scientific engine imports.

Original summaries and operational guidance, not copied upstream documentation.
Equations and reference links are shared so language cannot change conventions.
Historical long references remain packaged separately and are not deleted.
"""

from html import escape
import importlib.util
from pathlib import Path


def _method_notes():
    # Also supports the host-free documentation exporter and validation scripts.
    spec = importlib.util.spec_from_file_location(
        "tw_knowledge_methods", Path(__file__).with_name("knowledge_methods.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_METHOD_MODULE = _method_notes()
METHODS = _METHOD_MODULE.METHODS
METHOD_REFERENCES = _METHOD_MODULE.METHOD_REFERENCES

LANGUAGES = ("en", "es", "pt")
REFERENCES = {
    "ip_stack": (
        "Understanding the Fate of H2S Injected in Basalts by Means of Time-Domain Induced Polarization Geophysical Logging",
        "https://doi.org/10.1029/2023JB028316",
    ),
    "ip_waveform": (
        "Spectral induced polarization: frequency domain versus time domain laboratory data, Appendix C",
        "https://doi.org/10.1093/gji/ggab071",
    ),
    "flexure": (
        "GMT grdflexure: elastic and rheological plate models",
        "https://docs.generic-mapping-tools.org/6.5/supplements/potential/grdflexure.html",
    ),
    "prism_gravity": (
        "Harmonica prism gravity: units and coordinate conventions",
        "https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html",
    ),
    "prism_magnetic": (
        "Harmonica prism magnetic field: conventions",
        "https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_magnetic.html",
    ),
    "ndimage": (
        "SciPy multidimensional image processing",
        "https://docs.scipy.org/doc/scipy/reference/ndimage.html",
    ),
    "microleveling": (
        "Minty (1991): Simple Micro-Levelling for Aeromagnetic Data",
        "https://doi.org/10.1071/EG991591",
    ),
    "werner": (
        "Ku and Sharp (1983): Werner deconvolution",
        "https://doi.org/10.1190/1.1441505",
    ),
    "spi": (
        "Thurston and Smith (1997): SPI method",
        "https://doi.org/10.1190/1.1444190",
    ),
    "spectral_depth": (
        "Spector and Grant (1970): statistical aeromagnetic models",
        "https://doi.org/10.1190/1.1440092",
    ),
    "well_survey": (
        "Taylor (1972): well surveying calculations",
        "https://doi.org/10.2118/3362-PA",
    ),
    "treecode": (
        "Barnes and Hut: hierarchical force calculation",
        "https://doi.org/10.1038/324446a0",
    ),
    "kovesi": (
        "Monogenic phase attributes",
        "https://peterkovesi.github.io/ImagePhaseCongruency.jl/stable/functions/",
    ),
    "skimage": (
        "scikit-image morphology",
        "https://scikit-image.org/docs/stable/api/skimage.morphology.html",
    ),
    "harmonica": (
        "Harmonica transformations",
        "https://www.fatiando.org/harmonica/latest/user_guide/transformations.html",
    ),
    "upward": (
        "Harmonica upward continuation",
        "https://www.fatiando.org/harmonica/latest/api/generated/harmonica.upward_continuation.html",
    ),
    "verde": (
        "Verde spatial cross-validation",
        "https://www.fatiando.org/verde/latest/tutorials/model_selection.html",
    ),
    "gdal": (
        "GDAL raster data model",
        "https://gdal.org/en/stable/user/raster_data_model.html",
    ),
    "gravity": (
        "Boule normal gravity",
        "https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html",
    ),
    "iaea": (
        "IAEA-TECDOC-1363",
        "https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf",
    ),
    "simpeg": ("SimPEG", "https://docs.simpeg.xyz/latest/"),
    "mvi_spherical": (
        "Fournier, Heagy and Oldenburg (2020), Sparse magnetic vector inversion in spherical coordinates",
        "https://doi.org/10.1190/geo2019-0244.1",
    ),
    "misfit": (
        "SimPEG L2 data misfit",
        "https://docs.simpeg.xyz/latest/content/api/generated/simpeg.data_misfit.L2DataMisfit.html",
    ),
    "electrical": (
        "SimPEG DC resistivity",
        "https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.static.resistivity.html",
    ),
    "em": (
        "SimPEG electromagnetic methods",
        "https://docs.simpeg.xyz/latest/content/api/simpeg.electromagnetics.html",
    ),
    "scipy": (
        "SciPy signal processing",
        "https://docs.scipy.org/doc/scipy/reference/signal.html",
    ),
    "las": ("lasio documentation", "https://lasio.readthedocs.io/en/latest/"),
    "euler": (
        "Harmonica Euler deconvolution",
        "https://www.fatiando.org/harmonica/latest/api/generated/harmonica.EulerDeconvolution.html",
    ),
}

# id, localized title, localized paragraphs, common equations, reference IDs.
CHAPTERS = (
    (
        "workflow",
        (
            "GRD import and filter workflows",
            "Importación GRD y flujos de filtros",
            "Importação GRD e fluxos de filtros",
        ),
        (
            "Import the grid, verify coordinates and units, choose a filter, edit its parameters, then run the ordered stack. The Geosoft binary GRD reader creates a GeoTIFF at your chosen destination; the source stays unchanged. A GRD extension alone does not identify its encoding. Workflow outputs are temporary when no output directory is selected. A chosen directory receives a separate run folder, recipe and optional intermediate rasters. Save the stack to reuse settings, not to certify identical source data. Check each stage before interpreting the final image.",
            "Importa la grilla, verifica coordenadas y unidades, elige un filtro, edita sus parámetros y ejecuta la secuencia. El lector GRD binario Geosoft crea un GeoTIFF en la ubicación elegida; no cambia el original. La extensión GRD por sí sola no identifica la codificación. Las salidas del flujo son temporales si no eliges carpeta. Una carpeta elegida recibe una subcarpeta por ejecución, receta e intermedios opcionales. Guardar la pila permite reutilizar parámetros, no certifica datos de entrada idénticos. Revisa cada etapa antes de interpretar la imagen final.",
            "Importe a grade, confira coordenadas e unidades, escolha um filtro, edite seus parâmetros e execute a sequência. O leitor GRD binário Geosoft cria um GeoTIFF no destino escolhido; a origem permanece intacta. A extensão GRD sozinha não identifica a codificação. As saídas do fluxo são temporárias quando nenhuma pasta é selecionada. Uma pasta escolhida recebe uma subpasta por execução, receita e intermediários opcionais. Salvar a sequência permite reutilizar parâmetros, não certifica dados de entrada idênticos. Confira cada etapa antes de interpretar a imagem final.",
        ),
        "",
        ("gdal",),
    ),
    (
        "coordinates",
        (
            "Coordinates, units and missing data",
            "Coordenadas, unidades y datos ausentes",
            "Coordenadas, unidades e dados ausentes",
        ),
        (
            "Assigning a CRS describes existing coordinates; reprojection changes them. Do not assign a new CRS to repair wrongly positioned data. Record horizontal units, elevation reference and whether height means ground, sensor or clearance. A projected metric CRS is required for distance-based grid processing. Grid spacing and sample spacing are different. Check NoData masks, orientation, pixel centres and GDAL scale/offset before comparing rasters. Zero is a measurement, not an automatic missing-data marker. A local projected CRS does not certify a vertical datum conversion.",
            "Asignar un SRC describe coordenadas existentes; reproyectar las cambia. No asignes otro SRC para reparar datos mal ubicados. Registra unidades horizontales, referencia de elevación y si la altura corresponde al terreno, sensor o separación sobre el terreno. El procesamiento basado en distancias requiere un SRC proyectado métrico. El tamaño de celda y el espaciado de muestras son distintos. Comprueba máscaras NoData, orientación, centros de píxel y escala/desplazamiento GDAL al comparar rásteres. Cero es una medición, no un marcador automático de ausencia. Un SRC local no certifica una transformación de datum vertical.",
            "Atribuir um SRC descreve coordenadas existentes; reprojetar altera essas coordenadas. Não atribua outro SRC para corrigir dados mal posicionados. Registre unidades horizontais, referência de elevação e se a altura corresponde ao terreno, sensor ou afastamento do terreno. O processamento baseado em distâncias exige um SRC projetado métrico. O tamanho da célula e o espaçamento das amostras são diferentes. Confira máscaras NoData, orientação, centros de pixel e escala/deslocamento GDAL ao comparar rasters. Zero é uma medição, não um marcador automático de ausência. Um SRC local não certifica uma transformação de datum vertical.",
        ),
        "",
        ("gdal",),
    ),
    (
        "channels",
        (
            "Databases, channels and provenance",
            "Bases de datos, canales y trazabilidad",
            "Bases de dados, canais e rastreabilidade",
        ),
        (
            "Keep immutable imported channels and create derived versions with explicit units and meaningful names. The survey store combines a SQLite catalogue and column-oriented Parquet data; read selected columns instead of loading every channel. Inspect import delimiter, header row, decimal separator and missing values. Filters must respect line boundaries, gaps and sampling. A segment safety limit is not a total database capacity. Recipes identify channel versions and processing steps. Reusing a recipe after replacing an input must be reviewed. Channel lineage explains processing history, not scientific correctness.",
            "Conserva canales importados inmutables y crea versiones derivadas con unidades explícitas y nombres coherentes. El almacén combina un catálogo SQLite y datos Parquet por columnas; lee solo los canales necesarios. Revisa separador, fila de encabezados, separador decimal y ausencias al importar. Los filtros deben respetar líneas, huecos y muestreo. Un límite de seguridad por tramo no equivale a capacidad total de la base. Las recetas identifican versiones y pasos. Reutilizar una receta después de reemplazar una entrada exige revisión. El linaje documenta la historia, no garantiza corrección científica.",
            "Preserve canais importados imutáveis e crie versões derivadas com unidades explícitas e nomes coerentes. O armazenamento combina um catálogo SQLite com dados Parquet por colunas; leia apenas os canais necessários. Confira delimitador, linha de cabeçalhos, separador decimal e ausências na importação. Os filtros devem respeitar linhas, lacunas e amostragem. Um limite de segurança por trecho não equivale à capacidade total da base. As receitas identificam versões e etapas. Reutilizar uma receita após substituir uma entrada exige revisão. A linhagem documenta o histórico, não garante correção científica.",
        ),
        "",
        ("gdal",),
    ),
    (
        "gridding",
        (
            "Gridding and line quality control",
            "Interpolación y control de líneas",
            "Interpolação e controle de linhas",
        ),
        (
            "Correct timing, base station and acquisition effects before crossover leveling and gridding. Examine residuals by line and direction. Grid cell size cannot recover unsampled wavelengths. Compare interpolation methods with spatial holdout, not random neighbouring points that leak spatial information. Record search radius, neighbours, smoothing and blanking distance. A complete rectangle can contain unsupported extrapolation. Mask distant cells and compare alternative spacing. Equivalent sources require source depth, damping and memory controls; they are an interpolating representation, not a unique geological body. Microleveling must not remove real geology aligned with flight lines.",
            "Corrige tiempos, estación base y efectos de adquisición antes de nivelar cruces e interpolar. Examina residuos por línea y dirección. El tamaño de celda no recupera longitudes de onda no muestreadas. Compara métodos con validación espacial, no con vecinos aleatorios que filtran información espacial. Registra radio, vecinos, suavizado y distancia de exclusión. Un rectángulo completo puede contener extrapolación sin soporte. Enmascara celdas distantes y compara otros espaciados. Las fuentes equivalentes requieren profundidad, amortiguación y controles de memoria; son una representación interpolante, no un cuerpo geológico único. La micronivelación no debe eliminar geología paralela al vuelo.",
            "Corrija tempos, estação-base e efeitos da aquisição antes de nivelar cruzamentos e interpolar. Examine resíduos por linha e direção. O tamanho de célula não recupera comprimentos de onda não amostrados. Compare métodos com validação espacial, não com vizinhos aleatórios que deixam vazar informação espacial. Registre raio, vizinhos, suavização e distância de exclusão. Um retângulo completo pode conter extrapolação sem suporte. Mascare células distantes e compare outros espaçamentos. Fontes equivalentes exigem profundidade, amortecimento e controles de memória; são uma representação interpolante, não um corpo geológico único. O micronivelamento não deve eliminar geologia paralela ao voo.",
        ),
        "",
        ("verde", "harmonica", "kovesi", "skimage"),
    ),
    (
        "fft",
        (
            "FFT filters and parameter selection",
            "Filtros FFT y selección de parámetros",
            "Filtros FFT e seleção de parâmetros",
        ),
        (
            "Wavelengths and continuation heights use grid CRS units. Compare several cutoffs tied to survey spacing and target scale. Butterworth order controls transition sharpness; a higher order is not inherently better. Mean/plane removal, reflected padding and taper change edge behaviour; record them and compare the interior separately. Upward continuation attenuates short wavelengths. Downward continuation amplifies noise and requires stabilization and gain limits. Restore the removed trend only when physically appropriate. Apply spatial circular median to isolated spikes; it is nonlinear and not a Fourier transfer function. Do not treat database storage as a numerical domain.",
            "Las longitudes de onda y alturas de continuación usan unidades del SRC. Compara cortes relacionados con el muestreo y la escala objetivo. El orden Butterworth controla la transición; un orden mayor no es necesariamente mejor. Quitar media/plano, añadir relleno reflejado y suavizar bordes modifica el comportamiento marginal; regístralo y compara también el interior. La continuación ascendente atenúa ondas cortas. La descendente amplifica ruido y requiere estabilización y límites de ganancia. Restaura la tendencia solo cuando corresponda físicamente. La mediana circular espacial trata picos aislados; es no lineal y no es una transferencia Fourier. La base de datos no es un dominio numérico.",
            "Comprimentos de onda e alturas de continuação usam unidades do SRC. Compare cortes relacionados à amostragem e à escala-alvo. A ordem Butterworth controla a transição; uma ordem maior não é necessariamente melhor. Remover média/plano, adicionar preenchimento refletido e suavizar bordas modifica o comportamento marginal; registre isso e compare também o interior. A continuação para cima atenua ondas curtas. A continuação para baixo amplifica ruído e exige estabilização e limites de ganho. Restaure a tendência apenas quando fisicamente adequado. A mediana circular espacial trata picos isolados; é não linear e não é uma transferência Fourier. A base de dados não é um domínio numérico.",
        ),
        "H_up(k, h) = exp(-|k| h); k in rad / length; h > 0",
        ("upward", "scipy"),
    ),
    (
        "magnetics",
        (
            "Magnetic derivatives and field direction",
            "Derivadas magnéticas y dirección del campo",
            "Derivadas magnéticas e direção do campo",
        ),
        (
            "DX and DY depend on coordinate orientation; DZ depends on the vertical sign convention. Derivatives amplify short-wavelength noise. Compare horizontal gradient, total gradient amplitude and tilt with the unfiltered anomaly. RTP and RTE require inducing-field direction and an assumed magnetization direction. IGRF also requires date and altitude; do not silently substitute terrain elevation for sensor altitude. Low-inclination RTP may be unstable even with a smooth-looking map. Remanence can invalidate induced-only interpretation. An edge maximum is not proof of a fault, depth or lithology; compare independent geological observations.",
            "DX y DY dependen de la orientación de coordenadas; DZ depende del signo vertical. Las derivadas amplifican ruido de onda corta. Compara gradiente horizontal, amplitud de gradiente total y tilt con la anomalía original. RTP y RTE requieren dirección del campo y una dirección de magnetización supuesta. IGRF necesita fecha y altitud; no sustituyas silenciosamente altitud del sensor por elevación del terreno. RTP a baja inclinación puede ser inestable aunque el mapa parezca suave. La remanencia puede invalidar una interpretación solo inducida. Un máximo no demuestra falla, profundidad ni litología; contrasta observaciones independientes.",
            "DX e DY dependem da orientação das coordenadas; DZ depende do sinal vertical. Derivadas amplificam ruído de onda curta. Compare gradiente horizontal, amplitude do gradiente total e tilt com a anomalia original. RTP e RTE exigem direção do campo e uma direção de magnetização assumida. IGRF precisa de data e altitude; não substitua silenciosamente altitude do sensor por elevação do terreno. RTP em baixa inclinação pode ser instável mesmo com um mapa suave. Remanência pode invalidar uma interpretação apenas induzida. Um máximo não prova falha, profundidade ou litologia; confronte observações independentes.",
        ),
        "HGM = sqrt(DX² + DY²); TGA = sqrt(DX² + DY² + DZ²); tilt = atan2(DZ, HGM)",
        ("harmonica",),
    ),
    (
        "gravity",
        (
            "Gravity corrections and isostasy",
            "Correcciones gravimétricas e isostasia",
            "Correções gravimétricas e isostasia",
        ),
        (
            "Distinguish observed gravity, gravity disturbance and anomalies. Record latitude, height reference, drift epoch, tides, motion correction and reduction density. Check the sign of every correction before adding it. Terrain correction, Bouguer slab and spherical curvature are not interchangeable. Published complete Bouguer anomalies should not be corrected again as raw observations. Airy isostasy assumes local compensation; elastic flexure permits regional support and requires elastic parameters and boundaries. Density and reference-depth sensitivity should accompany interpretation. A residual is model-dependent, not automatically a measured crustal mass excess.",
            "Distingue gravedad observada, perturbación y anomalías. Registra latitud, referencia de altura, época de deriva, mareas, corrección por movimiento y densidad de reducción. Verifica el signo antes de sumar cada corrección. Terreno, placa Bouguer y curvatura esférica no son intercambiables. No corrijas otra vez anomalías Bouguer completas publicadas como si fueran observaciones crudas. La isostasia Airy supone compensación local; la flexura admite soporte regional y requiere parámetros elásticos y bordes. Acompaña la interpretación con sensibilidad a densidad y profundidad de referencia. El residual depende del modelo; no mide automáticamente un exceso de masa cortical.",
            "Distinga gravidade observada, perturbação e anomalias. Registre latitude, referência de altura, época de deriva, marés, correção de movimento e densidade de redução. Confira o sinal antes de somar cada correção. Terreno, placa Bouguer e curvatura esférica não são intercambiáveis. Não corrija novamente anomalias Bouguer completas publicadas como se fossem observações brutas. A isostasia Airy supõe compensação local; a flexura admite suporte regional e exige parâmetros elásticos e bordas. Acompanhe a interpretação com sensibilidade à densidade e profundidade de referência. O residual depende do modelo; não mede automaticamente um excesso de massa crustal.",
        ),
        "CBA = SBA + terrain - Bullard B",
        ("gravity", "harmonica", "treecode"),
    ),
    (
        "radiometry",
        (
            "Radiometry and detector calibration",
            "Radiometría y calibración del detector",
            "Radiometria e calibração do detector",
        ),
        (
            "Separate counts, count rates and calibrated K/eU/eTh. Correct raw observations with survey-specific dead-time, background, stripping, height and sensitivity coefficients; never reuse nominal coefficients blindly. Ratios need denominator guards and compatible masks. Inspect radon, moisture and clearance. Equivalent uranium assumes decay-chain conditions; it is not direct uranium chemistry. Ternary colours are a display, not independent measurements. Keep uncertainty and calibration residuals with the products.",
            "Separa conteos, tasas y K/eU/eTh calibrados. Corrige observaciones crudas con coeficientes del levantamiento para tiempo muerto, fondo, stripping, altura y sensibilidad; no reutilices coeficientes nominales sin revisión. Las razones requieren protección del denominador y máscaras compatibles. Examina radón, humedad y altura. El uranio equivalente supone condiciones de la cadena de decaimiento; no es química directa de uranio. El ternario es visualización, no mediciones independientes. Conserva incertidumbre y residuos de calibración.",
            "Separe contagens, taxas e K/eU/eTh calibrados. Corrija observações brutas com coeficientes do levantamento para tempo morto, fundo, stripping, altura e sensibilidade; não reutilize coeficientes nominais sem revisão. Razões exigem proteção do denominador e máscaras compatíveis. Examine radônio, umidade e altura. Urânio equivalente supõe condições da cadeia de decaimento; não é química direta de urânio. O ternário é visualização, não medições independentes. Preserve incerteza e resíduos de calibração.",
        ),
        "",
        ("iaea",),
    ),
    (
        "depth",
        (
            "Euler, Werner, SPI and spectral depth",
            "Euler, Werner, SPI y profundidad espectral",
            "Euler, Werner, SPI e profundidade espectral",
        ),
        (
            "Source-depth estimates depend on an assumed source class, sampling and background. For Euler, vary structural index, window size, derivative method and acceptance limits. Reject poorly conditioned windows and inspect clustered solutions rather than plotting every candidate as a source. Profile Werner/SPI results are not arbitrary 3D inversions. Spectral slopes require a declared frequency interval and statistical support; mixed source populations and edges can bias depth. Compare against synthetic cases, other windows and geology. None of these techniques uniquely determines a body boundary or reserves.",
            "Las profundidades dependen del tipo de fuente supuesto, muestreo y fondo. En Euler varía índice estructural, ventana, derivadas y límites de aceptación. Descarta ventanas mal condicionadas y examina agrupaciones, no todos los candidatos como fuentes. Werner/SPI de perfil no equivalen a una inversión 3D arbitraria. Las pendientes espectrales necesitan un intervalo de frecuencias declarado y soporte estadístico; fuentes mezcladas y bordes sesgan la profundidad. Compara casos sintéticos, otras ventanas y geología. Estas técnicas no determinan de forma única el límite de un cuerpo ni reservas.",
            "As profundidades dependem do tipo de fonte assumido, amostragem e fundo. Em Euler varie índice estrutural, janela, derivadas e limites de aceitação. Rejeite janelas mal condicionadas e examine agrupamentos, não todos os candidatos como fontes. Werner/SPI de perfil não equivalem a uma inversão 3D arbitrária. Inclinações espectrais exigem um intervalo de frequências declarado e suporte estatístico; fontes misturadas e bordas enviesam a profundidade. Compare casos sintéticos, outras janelas e geologia. Essas técnicas não determinam de forma única o limite de um corpo nem reservas.",
        ),
        "(x-x0) Tx + (y-y0) Ty + (z-z0) Tz = N (B-T)",
        ("euler",),
    ),
    (
        "inversion",
        (
            "Inversion, residuals and sensitivity",
            "Inversión, residuos y sensibilidad",
            "Inversão, resíduos e sensibilidade",
        ),
        (
            "Choose the physical property, forward operator, mesh, uncertainties, bounds and regularization explicitly. Separate sensor positions from the topographic surface. Repeat with altered cell size, depth, padding, starting/reference model and regularization weight. Inspect observed, predicted and residual data by line and spatial location, not only a scalar misfit. Convergence does not remove non-uniqueness. A cross-gradient promotes structural similarity, not a fixed density–susceptibility relationship. Optional engines and versions belong in provenance. A solver that reaches an iteration limit must not be labelled a converged solution.",
            "Elige explícitamente propiedad física, operador directo, malla, incertidumbres, límites y regularización. Separa posiciones del sensor y superficie topográfica. Repite variando celda, profundidad, extensión, modelo inicial/de referencia y peso de regularización. Inspecciona observados, predichos y residuos por línea y ubicación, no solo un desajuste escalar. Convergencia no elimina no unicidad. El gradiente cruzado favorece similitud estructural, no una relación fija densidad–susceptibilidad. Motores opcionales y versiones deben quedar en la trazabilidad. Un solver que alcanza el máximo de iteraciones no debe etiquetarse como solución convergente.",
            "Escolha explicitamente propriedade física, operador direto, malha, incertezas, limites e regularização. Separe posições do sensor e superfície topográfica. Repita variando célula, profundidade, extensão, modelo inicial/de referência e peso de regularização. Inspecione observados, preditos e resíduos por linha e localização, não apenas um desajuste escalar. Convergência não elimina não unicidade. O gradiente cruzado favorece similaridade estrutural, não uma relação fixa densidade–suscetibilidade. Motores opcionais e versões devem ficar na rastreabilidade. Um solver que atinge o máximo de iterações não deve ser rotulado como solução convergente.",
        ),
        "phi(m) = phi_d(m) + beta phi_m(m); r_i = (d_pred_i - d_obs_i) / sigma_i",
        ("misfit", "simpeg"),
    ),
    (
        "electrical",
        (
            "DC resistivity, IP and self potential",
            "Resistividad DC, IP y potencial espontáneo",
            "Resistividade DC, IP e potencial espontâneo",
        ),
        (
            "DC resistivity needs electrode geometry, current polarity, potential difference and a compatible geometric factor. Apparent resistivity is not a direct voxel property. Inspect reciprocal error, contact problems and topography. IP and complex conductivity need frequency/time and sign conventions; chargeability units are not interchangeable. Self potential needs a reference electrode and sign; fit source geometry and boundary conditions separately from interpretation. Layered responses assume lateral invariance. PDE forward modelling and inversion require mesh and boundary sensitivity. These experimental Core entries are not a complete instrument-processing system.",
            "La resistividad DC necesita geometría de electrodos, polaridad de corriente, diferencia de potencial y factor geométrico compatible. La resistividad aparente no es una propiedad directa del vóxel. Examina reciprocidad, contactos y topografía. IP y conductividad compleja necesitan convenciones de frecuencia/tiempo y signo; las unidades de cargabilidad no son intercambiables. El potencial espontáneo requiere electrodo de referencia y signo; separa el ajuste de fuentes y bordes de la interpretación. Los modelos estratificados suponen invariancia lateral. Modelado e inversión PDE requieren sensibilidad de malla y bordes. Estas entradas experimentales no son un sistema instrumental completo.",
            "A resistividade DC exige geometria de eletrodos, polaridade de corrente, diferença de potencial e fator geométrico compatível. Resistividade aparente não é uma propriedade direta do voxel. Examine reciprocidade, contatos e topografia. IP e condutividade complexa precisam de convenções de frequência/tempo e sinal; unidades de cargabilidade não são intercambiáveis. Potencial espontâneo exige eletrodo de referência e sinal; separe o ajuste de fontes e bordas da interpretação. Modelos estratificados supõem invariância lateral. Modelagem e inversão PDE exigem sensibilidade de malha e bordas. Estas entradas experimentais não são um sistema instrumental completo.",
        ),
        "rho_a = K delta_V / I",
        ("electrical",),
    ),
    (
        "em",
        (
            "FDEM, TEM and magnetotellurics",
            "FDEM, TEM y magnetotelúrica",
            "FDEM, TEM e magnetotelúrica",
        ),
        (
            "Record source/receiver geometry, frequency or waveform, component, orientation and normalization. FDEM in-phase/quadrature signs and ppm versus absolute fields matter. TEM gates are finite time integrals; use the recorded waveform and correct time zero. Exclude contaminated or negative-time gates explicitly. MT impedance requires declared electric/magnetic units and Fourier convention before apparent resistivity and phase. A 1D layered earth cannot represent arbitrary lateral structure. Repeat conductivity fits across starting models and bounds; an excellent curve fit alone does not establish depth resolution or geological uniqueness.",
            "Registra geometría fuente/receptor, frecuencia o forma de onda, componente, orientación y normalización. Importan los signos en fase/cuadratura y ppm frente a campo absoluto en FDEM. Las ventanas TEM son integrales temporales finitas; usa la forma de onda registrada y el tiempo cero correcto. Excluye explícitamente ventanas contaminadas o negativas. La impedancia MT requiere unidades eléctricas/magnéticas y convención Fourier antes de resistividad aparente y fase. Un modelo 1D no representa estructura lateral arbitraria. Repite ajustes de conductividad con otros modelos iniciales y límites; un ajuste excelente no demuestra resolución en profundidad ni unicidad geológica.",
            "Registre geometria fonte/receptor, frequência ou forma de onda, componente, orientação e normalização. Importam os sinais em fase/quadratura e ppm versus campo absoluto em FDEM. Janelas TEM são integrais temporais finitas; use a forma de onda registrada e o tempo zero correto. Exclua explicitamente janelas contaminadas ou negativas. A impedância MT exige unidades elétricas/magnéticas e convenção Fourier antes de resistividade aparente e fase. Um modelo 1D não representa estrutura lateral arbitrária. Repita ajustes de condutividade com outros modelos iniciais e limites; um ajuste excelente não demonstra resolução em profundidade nem unicidade geológica.",
        ),
        "rho_a = |Z_EH|² / (mu0 omega); omega = 2 pi f",
        ("em",),
    ),
    (
        "waveforms",
        (
            "GPR, waveforms and passive seismic",
            "Georradar, formas de onda y sísmica pasiva",
            "Georradar, formas de onda e sísmica passiva",
        ),
        (
            "Confirm the sample axis, interval, time zero and trace spacing before filtering. Dewow removes a local time mean; background subtraction removes shared trace content and can also suppress real horizontal reflectors. Bandpass limits must respect Nyquist. Gain changes amplitudes and is not a physical inversion. GPR depth needs a defensible velocity; migration requires the correct geometry and assumptions. For passive spectra, inspect windows, transients, component orientation and smoothing. An H/V peak is not automatically a unique layer thickness. Keep a raw-amplitude branch and compare processed traces, not just enhanced images.",
            "Confirma eje de muestras, intervalo, tiempo cero y espaciado de trazas antes de filtrar. Dewow resta una media temporal local; quitar fondo compartido puede suprimir reflectores horizontales reales. El pasabanda debe respetar Nyquist. La ganancia cambia amplitudes y no es inversión física. La profundidad de georradar necesita velocidad defendible; migración requiere geometría y supuestos correctos. En espectros pasivos revisa ventanas, transitorios, orientación y suavizado. Un pico H/V no equivale automáticamente a un espesor único. Conserva una rama de amplitudes originales y compara trazas, no solo imágenes realzadas.",
            "Confirme eixo de amostras, intervalo, tempo zero e espaçamento de traços antes de filtrar. Dewow subtrai uma média temporal local; remover fundo compartilhado pode suprimir refletores horizontais reais. A banda passante deve respeitar Nyquist. Ganho altera amplitudes e não é inversão física. A profundidade do georradar exige velocidade justificável; migração exige geometria e hipóteses corretas. Em espectros passivos confira janelas, transientes, orientação e suavização. Um pico H/V não equivale automaticamente a uma espessura única. Preserve um ramo de amplitudes originais e compare traços, não apenas imagens realçadas.",
        ),
        "f_Nyquist = 1 / (2 dt); depth_GPR = velocity time_two_way / 2",
        ("scipy",),
    ),
    (
        "borehole",
        (
            "Borehole logs and petrophysical transforms",
            "Registros de pozo y transformaciones petrofísicas",
            "Perfis de poço e transformações petrofísicas",
        ),
        (
            "Read LAS curve mnemonics, units, null values, depth direction and well metadata before selecting curves. Keep measured depth distinct from true vertical depth. Resampling and depth shifts must preserve null intervals and be documented per curve. Petrophysical transforms require formation-specific assumptions, fluid properties and calibration. Archie-type equations are not universal clay corrections. Do not infer porosity units from magnitudes alone. Compare transformed curves with original logs and independent laboratory data. Exporting updated LAS must preserve unmodified curves and source metadata; export success does not validate the geological model.",
            "Revisa mnemónicos LAS, unidades, valores nulos, sentido de profundidad y metadatos antes de elegir curvas. Separa profundidad medida y vertical verdadera. Remuestreo y desplazamientos deben preservar intervalos nulos y documentarse por curva. Las transformaciones petrofísicas requieren supuestos de formación, fluidos y calibración. Las ecuaciones tipo Archie no corrigen universalmente arcillas. No infieras unidades de porosidad solo por magnitudes. Compara curvas transformadas con originales y laboratorio independiente. Exportar LAS actualizado debe preservar curvas no modificadas y metadatos; una exportación correcta no valida el modelo geológico.",
            "Confira mnemônicos LAS, unidades, valores nulos, sentido da profundidade e metadados antes de escolher curvas. Separe profundidade medida e vertical verdadeira. Reamostragem e deslocamentos devem preservar intervalos nulos e ser documentados por curva. Transformações petrofísicas exigem hipóteses da formação, fluidos e calibração. Equações do tipo Archie não corrigem universalmente argilas. Não infira unidades de porosidade apenas pelas magnitudes. Compare curvas transformadas com originais e laboratório independente. Exportar LAS atualizado deve preservar curvas não modificadas e metadados; uma exportação correta não valida o modelo geológico.",
        ),
        "",
        ("las",),
    ),
    (
        "validation",
        (
            "Validation, provenance and safe conclusions",
            "Validación, trazabilidad y conclusiones prudentes",
            "Validação, rastreabilidade e conclusões prudentes",
        ),
        (
            "Separate unit tests, numerical reference comparisons, GUI tests and field validation. A synthetic pass does not establish commercial-software equivalence. Archive the recipe, input versions or checksums, units, parameters, library versions and residual statistics. Module checksums do not cover transitive dependencies. Distinguish completed, failed, cancelled and not-converged jobs. Output-size guards do not limit solver RAM or runtime. Cancellation may wait for a kernel checkpoint. Review sensitivity to defensible parameter ranges and document unresolved discrepancies. Keep private surveys and acquisition details outside published documentation and packages.",
            "Separa pruebas unitarias, comparación numérica, pruebas de GUI y validación de campo. Aprobar un caso sintético no establece equivalencia comercial. Archiva receta, versiones o hashes de entradas, unidades, parámetros, versiones de librerías y estadísticas residuales. El hash de un módulo no cubre dependencias transitivas. Distingue tareas completadas, fallidas, canceladas y sin converger. Los límites de salida no limitan RAM ni tiempo del solver. Cancelar puede esperar un punto de control. Revisa sensibilidad en rangos defendibles y documenta diferencias pendientes. Mantén levantamientos privados y adquisición fuera de documentación y paquetes públicos.",
            "Separe testes unitários, comparação numérica, testes de GUI e validação de campo. Aprovar um caso sintético não estabelece equivalência comercial. Arquive receita, versões ou hashes das entradas, unidades, parâmetros, versões de bibliotecas e estatísticas residuais. O hash de um módulo não cobre dependências transitivas. Distinga tarefas concluídas, falhas, canceladas e sem convergência. Limites de saída não limitam RAM nem tempo do solver. Cancelar pode aguardar um ponto de controle. Confira sensibilidade em intervalos justificáveis e documente diferenças pendentes. Mantenha levantamentos privados e aquisição fora de documentação e pacotes públicos.",
        ),
        "",
        ("simpeg",),
    ),
)


def method_sources(method_id, locale):
    """Return only the sources relevant to a method, in a stable order."""
    label = ("Context sources", "Fuentes de contexto", "Fontes de contexto")[
        LANGUAGES.index(locale)
    ]
    return (
        label
        + ":\n\n"
        + "\n".join(
            "- [" + REFERENCES[key][0] + "](" + REFERENCES[key][1] + ")"
            for key in METHOD_REFERENCES[method_id]
        )
    )


def citation_scope(locale):
    """Context does not independently certify a local numerical kernel."""
    index = LANGUAGES.index(locale)
    return (
        "Sources and scope: methodological context or library documentation; these links do not independently validate the local implementation, equations or numerical equivalence. The method note above defines its actual assumptions and limits.",
        "Fuentes y alcance: contexto metodológico o documentación de librerías; estos enlaces no validan de forma independiente la implementación local, sus ecuaciones ni su equivalencia numérica. La ficha anterior define sus supuestos y límites reales.",
        "Fontes e alcance: contexto metodológico ou documentação de bibliotecas; estes links não validam de forma independente a implementação local, suas equações ou equivalência numérica. A ficha acima define suas hipóteses e limites reais.",
    )[index]


def chapter_text(chapter_id, locale, *, include_publication_scope=False):
    """Render the same chapter, equations and references in each UI language."""
    index = LANGUAGES.index(locale)
    chapter = next(c for c in CHAPTERS if c[0] == chapter_id)
    _, titles, paragraphs, equation, reference_ids = chapter
    text = "# " + titles[index] + "\n\n" + paragraphs[index]
    if include_publication_scope:
        text += "\n\n" + citation_scope(locale)
    if equation:
        text += "\n\n" + equation
    for method_id, chapter, method_titles, notes, formula, parameters in METHODS:
        if chapter != chapter_id:
            continue
        text += "\n\n## " + method_titles[index] + "\n\n" + notes[index]
        if formula:
            text += "\n\n" + formula
        text += (
            "\n\n"
            + (
                "Parameters / quantities",
                "Parámetros / cantidades",
                "Parâmetros / grandezas",
            )[index]
            + ": "
            + ", ".join(parameters)
        )
        text += "\n\n" + method_sources(method_id, locale)
    text += (
        "\n\n"
        + ("Chapter context", "Contexto del capítulo", "Contexto do capítulo")[index]
        + ":\n\n"
    )
    text += "\n".join(
        "- [" + REFERENCES[key][0] + "](" + REFERENCES[key][1] + ")"
        for key in reference_ids
    )
    return text


def chapter_html(chapter_id, locale):
    """Clickable rich-text equivalent for embedding in process descriptions."""
    index = LANGUAGES.index(locale)
    _, titles, paragraphs, equation, references = next(
        c for c in CHAPTERS if c[0] == chapter_id
    )
    result = (
        "<h3>" + escape(titles[index]) + "</h3><p>" + escape(paragraphs[index]) + "</p>"
    )
    if equation:
        result += "<p>" + escape(equation) + "</p>"
    for method_id, chapter, method_titles, notes, formula, parameters in METHODS:
        if chapter != chapter_id:
            continue
        result += (
            "<h4>"
            + escape(method_titles[index])
            + "</h4><p>"
            + escape(notes[index])
            + "</p>"
        )
        sources = method_sources(method_id, locale)
        result += "<p>" + escape(sources.split("\n\n", 1)[0]) + "</p><ul>"
        for key in METHOD_REFERENCES[method_id]:
            label, url = REFERENCES[key]
            result += (
                '<li><a href="'
                + escape(url, quote=True)
                + '">'
                + escape(label)
                + "</a></li>"
            )
        result += "</ul>"
        if formula:
            result += "<p>" + escape(formula) + "</p>"
        result += (
            "<p>"
            + (
                "Parameters / quantities",
                "Parámetros / cantidades",
                "Parâmetros / grandezas",
            )[index]
            + ": "
            + escape(", ".join(parameters))
            + "</p>"
        )
    result += (
        "<p>"
        + ("Chapter context", "Contexto del capítulo", "Contexto do capítulo")[index]
        + ":</p><ul>"
    )
    for key in references:
        label, url = REFERENCES[key]
        result += (
            '<li><a href="'
            + escape(url, quote=True)
            + '">'
            + escape(label)
            + "</a></li>"
        )
    return result + "</ul>"

# Expansion implementada en Core

## Inversion 3D del 28 de octubre de 2026

La [ampliacion 3D](../validation/reports/inversion3d_extensions.md) agrega operadores de sensibilidad
sin matriz completa, publicacion standalone conjunta, unidades de exportacion
explicitas y cuatro operaciones de resolucion lineal o propiedades de prismas
con geometria conocida. Conserva limites de incertidumbre, presupuestos y
evidencia reproducible sin declarar cerrada toda la inversion geofisica.

## Ampliacion del 28 de octubre de 2026

Ocho operaciones adicionales conectan modelado gravimetrico por poligonos,
ajuste de densidades, reconstruccion calibrada de radon por ventanas/espectros,
fondos variables, variogramas y kriging al catalogo avanzado EN/ES/PT.
El ajuste de redes tambien admite referencias con incertidumbre y conserva
su covarianza comun. Los contratos, referencias independientes y limites estan
en [ampliacion 2D](../validation/reports/2d_extensions.md). La calibracion y validacion atmosferica
de campo siguen requiriendo datos instrumentales; no se declara paridad total.
Los conteos y estados de las secciones siguientes corresponden a sus fechas.

## Extraccion y operadores del 26 de octubre de 2026

Se agregaron API directas de QC, IGRF, terreno y reproyeccion horizontal:
[contratos y limites](../development/standalone_acquisition.md). Los adaptadores historicos
se conservan. El terreno finito sigue siendo de coste cuadratico; no se
declara resuelto todo el procesamiento regional. Hay una alternativa de
[atraccion adaptativa del DEM en estaciones](../reference/methods/adaptive_terrain.md), con
aproximacion lejana y prismas exactos cercanos, registrada como
gravity.terrain_adaptive. El metodo historico no cambia.

Tambien hay conversion de componentes, reconstruccion de TMI desde gradientes
y filtrado radial tabulado: [contratos MAG](../reference/methods/magnetic_component_api.md).
No se consideran por ello completos MAGMAP, GM-SYS, UXO o AGC. Estas API ya
estan conectadas al catalogo avanzado y sus formularios EN/ES/PT.

Hay una base de forward y ajuste local de dipolos magneticos con posiciones
y momentos libres, limites/rango/covarianza y presupuestos explicitos:
[modelos compactos](../reference/methods/compact_magnetics.md). No identifica UXO ni completa AGC.

Se incorporaron atributos de fase multiescala, textura, entropia de orientaciones
y caminos de esqueletos: [contratos estructurales](../reference/methods/structural_attributes.md).
Son API directas, sin clasificacion geologica ni equivalencia CET declarada.

La densidad y susceptibilidad aparentes cuentan con un modelo de capa finita
continuo y periodico, forward e inversa regularizada en unidades SI:
[contratos de propiedades aparentes](../reference/methods/apparent_properties.md). La geometria,
el background y la estabilizacion son explicitos; no se declara paridad con
los operadores DENS/SUSC ni se infiere una solucion geologica unica.

## Registro de la ampliacion anterior

Estado del 23 de octubre de 2026. Este documento describe codigo ejecutable,
no el cumplimiento completo de las 128 propuestas del backlog. La interfaz ahora
incluye un centro de procesos y una consola avanzada; no se modificaron datos
privados. Las API nuevas siguen siendo experimentales.

## Entrada comun

El modulo terraworkbench_core.operations ofrece list_operations,
operation_info y run_operation. El catalogo registra 94 entradas, incluidas
seis entradas a metodos historicos de profundidad de fuentes y 15 conexiones
agregadas el 26 de octubre para los operadores nuevos:
identificador estable, dominio de proceso, contrato, biblioteca opcional y
vinculo con una propuesta. Un vinculo significa cobertura parcial, no cierre
de toda la propuesta. Los kernels historicos conservan sus importaciones.

El centro de procesos permite ejecutar recetas de varios pasos mediante
[workflows del Core](../guides/core_workflows.md), con referencias explicitas a resultados
anteriores, publicacion atomica y detencion ante fallos o falta de convergencia.

    from terraworkbench_core.operations import list_operations, run_operation
    catalog = list_operations()
    result = run_operation(
        "mt.layered_forward",
        frequency_hz=[1., 10., 100.],
        resistivity_ohm_m=[100., 500.],
        thicknesses_m=[200.],
    )

El resultado separa datos y procedencia: SHA-256 de parametros explicitos y
modulo implementador, versiones, UTC y estado. No escribe archivos ni guarda
datos privados. Los hashes no cubren callbacks, valores omitidos por defecto
ni todas las dependencias transitivas. Los errores y cancelaciones se propagan;
un limite de iteraciones se registra como not_converged cuando el solver
devuelve success falso, no como solucion numerica completada.

## Capacidades y limites

| Area | Implementado | Limite importante |
| --- | --- | --- |
| Espectros | PSD normalizada, sectores direccionales, ajuste de profundidad, inversa Wiener y capas matched-filter | Grillas completas y planas; modelo/rangos explicitos; capas prescritas, no geologia inferida; error de regresion no es incertidumbre geologica |
| Fuentes equivalentes | Ajuste y prediccion a alturas variables por bloques | Fuentes y damping explicitos; entrenamiento denso limitado; sin certificado de extrapolacion |
| Gradiometria | Hessiano de prismas, rotacion e invariantes | Base este/norte/arriba, Eotvos, densidad kg/m3; no singularidades ni inversion de tensores |
| Gravedad | Red anclada con drift por instrumento, regresion de densidad | Escala ya calibrada y anclas exactas; sin mareas internas ni carga oceanica |
| Radiometria | Calibracion energetica, rebin, NASVD/MNF, ventanas, espectros, proxy temporal de radon y ajuste GLS de sensibilidad/background a patrones | Patrones tratados como exactos; geometria y correcciones previas explicitas; inversion de ventanas con incertidumbre de coeficientes de primer orden |
| DC | ABMN, factores geometricos, polaridad, reciprocidad, sondeos 1D y PDE 2.5D/3D con inversion | Malla tensorial y terreno explicitos, parametros por zonas o celulas; limites de memoria/trabajo; no mallado ni diseno automatico |
| IP/SIP | Chargeability por compuertas, Cole-Cole y PDE/inversion IP estatica 2.5D/3D | IP espacial linealizada para pequena chargeability con conductividad fija; no inversion completa del decaimiento Cole-Cole |
| FDEM | Forward 1D, forward 3D isotropico y ajuste local de conductividades por zonas | B secundaria en teslas; geometria/malla fijas, LU dispersa limitada, no inversion industrial por voxeles ni anisotropia |
| TEM | Forward 1D step-off y onda lineal por tramos, compuertas, apilado polarizado y ajuste local 1D de conductividad | dB/dt T/s; geometria/espesores fijos, dipolo ideal; sin lazo finito, respuesta instrumental ni inversion espacial |
| MT | Impedancia 1D, unidades, resistividad/fase, tensor de fase e inversion local | E/H en ohms y exp(+i omega t); sin EDI/MTH5 ni estimacion robusta de series temporales |
| Sismica/GPR | Bandpass, dewow, background, time-zero, ganancias, hiperbolas, NMO/stack y candidatos STA/LTA | Arrays calibrados; sin lectura SEG-Y/GPR dedicada, tomografia ni migracion; revisar picks y perdida de amplitud |
| Pasiva/superficiales | H/V por ventanas e imagen de coherencia fase-velocidad | H/V sin suavizado/certificacion; linea regular para dispersion; sin seleccion de modos ni inversion Vs |
| Autopotencial | Fuentes prescritas, inversion lineal, red de referencias y PDE heterogeneo 3D | Conductividad y geometria fijas; PDE en caja aislante; no inferencia hidraulica/electroquimica unica |
| Pozos | LAS 1.2/2.0, QC de profundidad y trayectoria de curvatura minima | Unidades/cabeceras conservadas; solo indice de profundidad m/ft; sin DLIS ni datum inventado |
| Inversion/regional | Resolucion/covarianza, DOI, ensemble lineal, admittance/coherence, flexura elastica y barrido de espesores | Placa uniforme y carga neta prescrita; fronteras periodicas; no posterior no lineal, reologia viscosa ni umbral geologico universal |

Los extras electrical y em reutilizan SimPEG 0.25.x; prisms reutiliza
Harmonica 0.7.x. Todos estan declarados en pyproject.toml y se importan al
ejecutar el metodo, no al descubrir el catalogo. NumPy/SciPy son la base.
El extra borehole declara lasio 0.31/0.32, licencia MIT, importacion diferida.
Para probar LAS se instalo lasio 0.32 en un directorio opcional de la sesion
de desarrollo, sin modificar los entornos existentes. El escritor usa 17
cifras significativas; conserva valores float64, unidades, codigos NoData y
cabeceras, no el formato/comentarios byte por byte. La profundidad es inmutable
en la operacion de reemplazo de muestras.

Los PDE electricos usan explicitamente SciPy sparse LU a traves de pymatsolver,
no BFGS ni el solver nativo de potenciales. El parametro beta y la referencia
son obligatorios; el regularizador por defecto es identidad en espacio de
parametros, NO suavizado espacial ni ponderacion de volumen. Las cotas usan
S/m para DC y V/V para IP. La malla usa x,z con y=0 en 2.5D y ENU en 3D;
electrodos y celulas activas no se ajustan silenciosamente al terreno.

Los limites estructurales no garantizan el pico de RAM de LU. El modelo zonal
permite ensayos pequenos; el limite de parametros de inversion es configurable.
No son motores out-of-core para inversiones industriales. En SimPEG 0.25 el
Jacobiano IP se normaliza explicitamente como su respuesta aparente, para
evitar confundir sensibilidad de voltaje con chargeability V/V.

El adaptador FDEM 1D solicita H secundaria y convierte explicitamente con mu0
a B en aire. No presupone que el nombre de un receptor garantice las unidades
del motor 1D. El adaptador DC agrega un offset exclusivamente numerico cuando
el spline Hankel del motor carece de rango suficiente; descarta esa prediccion
auxiliar y nunca la trata como dato observado.

FDEM 3D usa Simulation3DElectricField de SimPEG y recibe B secundaria directamente
en teslas: NO vuelve a multiplicarla por mu0. Usa conductividad isotropica,
permeabilidad mu0 y aproximacion cuasiestatica sin corrientes de desplazamiento.
Una geometria ENU por fila permite frecuencias repetidas; cada frecuencia unica
requiere una factorizacion. Los presupuestos cuentan celdas, aristas, parametros
y llamadas forward, incluidas las diferencias finitas del ajuste. La cancelacion
se comprueba entre solves, no dentro de LU. Convergencia de malla y distancia a
los bordes deben verificarse para cada survey. Refinar solo el nucleo manteniendo
padding grueso no mostro error monotono en el ensayo inicial; el benchmark de
espacio completo refina TODO el dominio, sin ocultar ese limite.

paired_detector_radon modela d=g+alpha*r y u=beta*g+gamma*r, con respuestas
calibradas explicitas, errores gaussianos y covarianza por registro. El prior
temporal penaliza roughness*sum(delta_r^2/delta_t), solo dentro de segmentos
continuos. El solve tridiagonal y su diagonal de covarianza son O(n), sin
matrices densas por survey. Conserva negativos marcados. Las varianzas son
posteriores marginales condicionadas a ruido, respuestas y roughness fijos;
no incluyen incertidumbre de calibracion. Requiere tasas ya corregidas por
tiempo vivo, aeronave y cosmicos. No reproduce automaticamente una receta IAEA
ni estima Bq/m3 sin calibracion independiente de esas unidades.

fit_radiometric_response ajusta tasas = concentraciones @ sensibilidad.T +
offset mediante GLS blanqueado y SVD. Admite correlacion entre ventanas por
patron y devuelve la covarianza conjunta de sensibilidades y offsets, sin
reescalarla con residuos. Los patrones son exactos y cada registro independiente;
no propaga su incertidumbre certificada ni corrige automaticamente pads, alturas,
tiempo vivo, aeronave o cosmicos. Los nombres y unidades de cada componente
son obligatorios. radiometric_concentrations exige sensibilidad cuadrada e
invertible y agrega incertidumbre de conteo y calibracion con el metodo delta.
Conserva valores negativos. No supone equilibrio radiactivo para eU/eTh.

fit_complex_response y apply_complex_response ajustan y corrigen una ganancia
y offset complejos constantes, con covarianza completa real/imaginaria. Se
deben agrupar calibraciones por frecuencia, geometria y periodo adecuados;
no se aplica una unica calibracion a todo un instrumento sin justificacion.
El ajuste blanquea ruido y normaliza columnas antes del SVD, para que el
diagnostico de rango no confunda unidades pequenas (por ejemplo teslas) con
falta de informacion. Coeficientes y covarianzas vuelven a sus unidades originales.
La referencia es exacta y comparte la convencion fasorial del dato; no se
infiere una fase, campo primario ni conversion ppm automaticamente.
Ambas correcciones por bloques devuelven covarianzas marginales por registro:
la calibracion compartida induce errores correlacionados entre registros que
NO se devuelven como una matriz densa de survey. El metodo delta es de primer
orden, no una posterior exacta de la inversa de una matriz o ganancia incierta.
Las mediciones corregidas deben ser independientes de los patrones usados.
El ajuste FDEM 3D acepta errores real/imaginario independientes O matrices
de covarianza real/imaginaria 2x2 por registro, no ambas alternativas a la vez.
Usa blanqueo Cholesky y reconstruye la prediccion sin un forward adicional.
Las correlaciones ENTRE registros inducidas por calibracion compartida siguen
fuera de esa aproximacion: usar covarianzas marginales no las elimina.

thin_plate_flexure resuelve D*nabla^4(w)+delta_rho*g*w=presion por FFT, con
w positivo hacia abajo y D=E*Te^3/[12*(1-nu^2)]. Carga en Pa, espaciado
(dy,dx) en metros; contraste restaurador y propiedades constantes explicitos.
No rellena NoData, elimina medias, agrega padding ni convierte topografia a
carga. Te=0 da compensacion local; la media se conserva para cualquier Te.
scan_elastic_thickness compara candidatos explicitos con desplazamiento, NO
con gravedad directamente. Devuelve toda la curva, empates y aviso de borde;
una carga uniforme no identifica Te. No produce incertidumbre geologica ni
compensa errores de dominio, densidad, carga o datum. No sustituye Airy existente.

self_potential_pde reutiliza los volumenes finitos centrados en celda de
SimPEG: -div(sigma*grad(phi))=q, con sigma en S/m y q en A/m3. La malla
tensorial ENU es un conductor finito, con flujo normal cero en TODAS sus caras.
No es Robin ni un dominio abierto infinito; no agrega mascara de aire ni
topografia. Cada fuente/plantilla debe integrar corriente total cero. Se fija
un gauge numerico y se devuelve siempre V(observacion)-V(referencia) en voltios;
no extrapola electrodos fuera de los centros de celda.
El ajuste usa plantillas de corriente prescritas, conductividad fija, beta,
referencia y L explicitos (identidad por defecto, no suavizado). Comparte una
factorizacion LU entre bloques de fuentes y devuelve covarianza/resolucion
lineales condicionadas. No infiere acoplamiento electroquimico, flujo hidraulico
ni conductividad. Los limites estructurales no garantizan RAM pico de LU;
la cancelacion se comprueba entre bloques, no dentro de la factorizacion nativa.

## Evidencia y pendientes

Las pruebas de tests/test_geophysics_expansion.py comprueban Parseval,
soluciones conocidas, conservacion de cuentas/covarianza, ruido Poisson,
signos/unidades, reciprocidad, recuperacion sintetica, presupuestos y errores.
FDEM/TEM se contrastan con expresiones analiticas de Geoana, una dependencia
del mismo ecosistema: esto no equivale a una comparacion comercial independiente.
Los ajustes estratificados de multiples capas prueban recuperacion sintetica;
no validan unicidad sobre un survey real.

Las pruebas de tests/test_tem_mnf.py contrastan rampas con la integral de una
respuesta analitica, pulso finito por superposicion, limites de evaluaciones y
cancelacion. La cadena sintetica registros ruidosos, compuertas, apilado y
ajuste 1D conserva signos y ruido temporal correlacionado al integrar cada
repeticion antes de apilarla. No reemplaza una calibracion instrumental real.

MNF aprende la media y rotaciones solo con los espectros de entrenamiento;
permite reconstruir datos independientes sin reajustar el modelo. Conserva
valores negativos y covarianza condicional; no propaga la incertidumbre de la
covarianza de ruido ni selecciona automaticamente el rango. Para cuentas crudas
Poisson, NASVD sigue siendo una opcion separada con sus propios supuestos.

Las pruebas de electrical_pde verifican respuesta de semiespacio en mallas
refinadas, recuperacion DC/IP en ambas dimensiones, una anomalia zonal, aire
activo/inactivo, superficie no plana, polaridad y presupuestos. La prueba
topografica es de consistencia, no una certificacion de precision de terreno.
Waveform_processing prueba senales conocidas, amplitudes, desplazamientos,
hiperbolas, moveout, H/V, picks de umbral y velocidad aparente de onda plana.
SP y pozos incluyen soluciones analiticas, conservacion de corriente, cambio
de referencia, redes desconectadas y trayectoria circular conocida.

test_fdem_3d compara B secundaria con la solucion analitica de espacio completo,
refina globalmente el mismo dominio, verifica escala del momento, orden de
frecuencias repetidas, recuperacion de dos zonas y limites/cancelacion.
test_radiometric_radon contrasta medias y covarianzas con la inversa densa
conjunta de un problema pequeno, y prueba separacion entre segmentos.
La conversion comun rechaza complejos cuando se solicita un array real, en
vez de descartar silenciosamente la fase.

test_calibration contrasta GLS con matrices de precision independientes,
Jacobianos por diferencias centrales y Monte Carlo con datos independientes
para validar la aproximacion de primer orden. test_flexure usa modos Fourier
analiticos, residuo de la ecuacion de placa, limite local y no identificabilidad
de cargas uniformes. No se ha comparado numericamente con GMT ni con un survey.

test_self_potential_pde verifica convergencia frente a una solucion continua
de Neumann, caida de voltaje de un resistor heterogeneo no uniforme, signos,
neutralidad, cambio de referencia y recuperacion sintetica de dos plantillas.
Estos ensayos no validan automaticamente una fuente hidrogeologica real.

Siguen pendientes las extensiones completas del backlog: TEM 3D escalable,
SIP espectral espacial, mareas/carga, VTI, respuesta instrumental/calibraciones,
calibracion completa de radon/espectros, formatos SEG-Y/GPR/DLIS, tomografia/migracion, Vs, flexura viscoelastica, fuentes SP
abiertas/electrocineticas y las inversiones avanzadas restantes.
No hay declaraciones de disponibilidad de esos motores ni placeholders
registrados como operaciones implementadas. Para cerrar metodos faltan
benchmarks independientes, sensibilidad y datos de campo con metadatos.

## Almacenamiento y entrada sin GUI

SurveyStore, survey_text_import y survey_grid_pipeline se distribuyen ahora dentro
del Core. Los modulos antiguos son adaptadores de compatibilidad, sin copias
del parser ni del motor de almacenamiento. El formato sigue siendo SQLite +
Parquet Zstandard, version 1: no se migraron ni tocaron bases reales.
El extra storage declara pyarrow>=16,<26, importado solo al usar almacenamiento.
La API historica terraworkbench_core.text_import se conserva sin cambios;
su lector pandas declara el extra tables. El adaptador raiz text_import sigue
exponiendo la API de surveys, que es distinta de la API historica de tablas.
Se conservan lectura por columnas/bloques, identificadores con ceros iniciales,
unidades, CRS asignado explicitamente, versiones y grafo de procedencia.
Asignar un CRS no transforma coordenadas ni valida un datum automaticamente.
La orquestacion de grillas carga GDAL nativo solo al exportar: esa dependencia
no se agrega silenciosamente al entorno ni se incluye en el wheel puro Python.
Las pruebas instaladas fuera del checkout bloquean imports de los adaptadores
antiguos, ademas de QGIS/Qt, y prueban importacion tipada, canales derivados,
reapertura y linaje. No son una prueba de exportacion GDAL ni de una GUI real.

## Referencias tecnicas

- [SimPEG: API cientifica](https://docs.simpeg.xyz/latest/content/api/index.html).
- [SimPEG: PDE de autopotencial y unidades de fuente](https://docs.simpeg.xyz/latest/content/api/generated/simpeg.electromagnetics.static.self_potential.Simulation3DCellCentered.html).
- [SimPEG: contratos de formas de onda](https://github.com/simpeg/simpeg/blob/main/simpeg/electromagnetics/time_domain/sources.py).
- [Harmonica: API y convenciones](https://www.fatiando.org/harmonica/latest/api/index.html).
- [lasio: lector y escritor LAS](https://lasio.readthedocs.io/en/latest/).
- [IAEA TECDOC-1363: espectrometria gamma](https://www-pub.iaea.org/mtcd/publications/pdf/te_1363_web.pdf).
- [GMT: familia de modelos de flexura y fronteras FFT](https://docs.generic-mapping-tools.org/6.5/supplements/potential/grdflexure.html).
- [MTpy: impedancia y tensor de fase](https://mtpy-v2.readthedocs.io/en/stable/notebooks/mt_object.html).
- [Limitaciones de estimacion espectral de profundidad](https://academic.oup.com/gji/article/169/2/421/623499).

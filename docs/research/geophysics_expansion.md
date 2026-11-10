# Expansion cientifica de TerraWorkbench

Revision del 22 de octubre de 2026. Este documento es un inventario de oportunidades y una propuesta de arquitectura. Las capacidades candidatas no estan implementadas por figurar aqui. La revision combina inspeccion del codigo local y documentacion primaria de proyectos cientificos. No certifica equivalencia con software comercial ni resultados sobre levantamientos reales.

Al 28 de octubre, el catalogo estructurado [geophysics_backlog.json](geophysics_backlog.json) contiene 133 mejoras candidatas distribuidas en 17 familias, contando sus listas actuales. El conteo anterior de 128 en 16 familias estaba desactualizado. Cada familia registra evidencia local, fuentes, datos necesarios, prioridad y un benchmark minimo. Incluye algoritmos, controles cientificos, formatos y herramientas de validacion: no son 133 algoritmos terminados.

La implementacion posterior a esta busqueda se registra por separado en
[operaciones Core y limites](core_expansion_implementation.md). El inventario
de abajo conserva el punto de partida previo a esa implementacion.

## Cobertura inicial y oportunidades

| Familia | Evidencia actual en el repositorio | Expansion propuesta |
| --- | --- | --- |
| MAG y campos potenciales | Filtros, transformaciones, compensacion, nivelacion, Euler, Werner y SPI por perfiles | Profundidad espectral, tensores, susceptibilidad aparente, remanencia, soluciones multiescala |
| Gravedad | Correcciones y Airy en Core; parte de la orquestacion sigue en adaptadores | Redes de estaciones, marea interna, efectos de carga, modelado 2D/2.5D, tesseroids, gradiometria |
| Radiometria | Productos K/U/Th y primitivas parametrizadas de correccion | Estabilizacion energetica, NASVD/MNF, radon temporal, calibracion, covarianzas |
| Inversion | Densidad, susceptibilidad, MVI, controles escalares IRLS y cross-gradient | DOI, sensibilidad/resolucion, conjuntos de modelos, restricciones petrofisicas, time-lapse |
| ERT e IP/SIP | No se encontro un motor dedicado en Core | ABMN, reciprocidad, 1D/2.5D/3D, chargeability, Cole-Cole y Debye |
| TEM/FDEM | No se encontro un motor dedicado en Core | Geometria de bobinas/lazos, formas de onda, respuestas 1D, inversion y restricciones laterales |
| MT y autopotencial | No se encontraron motores dedicados en Core | EDI/MTH5, impedancias, procesamiento robusto, modelos MT y potenciales espontaneos |
| Sismica activa | No se encontro un procesador dedicado | Geometria SEG-Y, primeras llegadas, refraccion, velocidades, stacking y migracion |
| Sismica pasiva y ondas superficiales | No se encontro un motor dedicado | HVSR, MASW, SPAC/f-k, dispersion y modelos Vs |
| GPR | No se encontro un procesador dedicado | Time-zero, dewow, velocidades, migracion, slices y benchmark FDTD |
| Sondeos/petrofisica | El importador generico no constituye soporte completo de logs | LAS/DLIS, control de profundidad, laboratorio, geometria crosshole y estudio de NMR |
| Regional/geologia | Gravedad normal e isostasia Airy | Armonicos esfericos, flexura, admittance/coherence, superficies geologicas y transferencia regional-local |

La presencia de un paquete externo o de una funcion numerica no equivale a un flujo listo. Por ejemplo, el espectro radial existente no estima por si solo profundidad con incertidumbre; las fuentes equivalentes que permanecen en un adaptador QGIS no son automaticamente una API standalone; y una correccion que recibe mareas externas no es un calculador interno de mareas.

## Integraciones con mejor fundamento

Estas son candidatas a motores o referencias de contraste. No se propone incorporar sus interfaces completas ni instalar todo a la vez. Las versiones mostradas por sus sitios pueden diferir de las fijadas actualmente por TerraWorkbench.

| Proyectos | Papel propuesto | Fuente primaria |
| --- | --- | --- |
| Harmonica y Choclo | Forward MAG/GRAV, fuentes equivalentes y kernels de referencia | [Harmonica API](https://www.fatiando.org/harmonica/latest/api/index.html), [Choclo](https://github.com/fatiando/choclo) |
| SimPEG | Adaptadores independientes para DC/IP, FDEM/TEM, MT y mejoras de inversion | [Modulos cientificos](https://docs.simpeg.xyz/latest/content/api/index.html) |
| pyGIMLi | Contraste y posible adaptador para ERT, SIP, refraccion y restricciones conjuntas | [Ejemplos oficiales](https://www.pygimli.org/_examples_auto/index.html) |
| empymod y emg3d | Respuestas EM en medios estratificados y solucion EM difusiva 3D, respectivamente | [empymod](https://github.com/emsig/empymod), [emg3d](https://github.com/emsig/emg3d) |
| MTpy y Aurora | Metadatos/transfer functions MT y procesamiento de senales de fuente natural | [MTpy](https://mtpy-v2.readthedocs.io/en/latest/), [Aurora](https://github.com/simpeg/aurora) |
| ObsPy, PyLops y Pyrocko | Formatos/senales sismicas, operadores inversos/migracion y herramientas de sismologia | [ObsPy](https://docs.obspy.org/), [PyLops](https://pylops.readthedocs.io/en/latest/tutorials/), [Pyrocko](https://pyrocko.org/docs/current/) |
| Geopsy, hvsrpy y swprocess | Ruido ambiental, HVSR y dispersion de ondas superficiales | [Geopsy](https://geopsy.org/), [hvsrpy](https://hvsrpy.readthedocs.io/en/latest/), [swprocess](https://swprocess.readthedocs.io/en/latest/) |
| GPRPy y gprMax | Procesamiento de radar y simulacion electromagnetica FDTD como trabajos distintos | [GPRPy](https://github.com/NSGeophysics/GPRPy), [gprMax](https://docs.gprmax.com/en/latest/) |
| lasio y dlisio | Intercambio de logs LAS y DLIS/LIS, sujeto al soporte concreto de cada formato | [lasio](https://lasio.readthedocs.io/en/latest/), [dlisio](https://dlisio.readthedocs.io/en/latest/) |
| Boule, SHTOOLS y GMT | Referencias geodesicas, campos globales y contraste espectral | [Boule](https://www.fatiando.org/boule/latest/), [SHTOOLS](https://shtools.github.io/SHTOOLS/), [GMT grdfft](https://docs.generic-mapping-tools.org/latest/grdfft.html) |
| GemPy y LoopStructural | Intercambio de geometria y priors geologicos, conservando su incertidumbre | [GemPy](https://www.gempy.org/), [LoopStructural](https://loop3d.org/LoopStructural/) |
| PyGMI | Referencia adicional de flujos geofisicos para comparar alcance y ejemplos | [Repositorio oficial](https://github.com/Patrick-Cole/pygmi) |

Para radiometria, la referencia metodologica inicial es [IAEA-TECDOC-1363](https://www-pub.iaea.org/mtcd/publications/pdf/te_1363_web.pdf). Los espectros, vuelos de calibracion y canales auxiliares son entradas necesarias; una grilla final de concentraciones no permite reconstruirlos.

Para mareas, [pyTMD](https://pytmd.readthedocs.io/en/latest/) merece evaluacion como referencia y adaptador. Predecir altura del oceano o desplazamiento de la corteza no equivale a producir una correccion de gravedad en mGal. Hay que verificar el observable, las convenciones y los modelos externos necesarios.

Las fuentes por familia son puntos de partida, no una afirmacion de que una sola libreria contiene todas sus mejoras propuestas. Algunas opciones requieren formulacion especifica y literatura adicional antes de programarlas. Las licencias de software, coeficientes, modelos globales y datasets deben revisarse para la version concreta seleccionada. No se realizo una auditoria juridica de compatibilidad.

## Orden recomendado

1. Cerrar la base ya util: profundidad espectral con rangos de ajuste explicitos, forward/tensores, sensibilidad de inversion y fuentes equivalentes standalone. Aprovecha NumPy/SciPy y los motores actuales; los metodos nuevos necesitan sus propias especificaciones y benchmarks.
2. Mejorar calidad de MAG/GRAV: convenciones, red de estaciones, incertidumbre de altura y datum, pruebas de referencia y sensibilidad. Las mareas internas exigen un benchmark fisico independiente.
3. Completar radiometria desde espectros: primero estabilizacion y estimacion del ruido, luego reconstruccion, calibracion/radon y propagacion de errores. Mantener separados los coeficientes medidos y los supuestos.
4. Abrir ERT/IP y TEM/FDEM mediante adaptadores opcionales. Empezar por contratos de datos, QC y forward de modelos sencillos antes de permitir inversiones 3D pesadas.
5. Incorporar GPR, MT, sismica y ondas superficiales por modulos completos: lectura, QC, procesamiento, interpretacion, validacion y exportacion. Los logs pueden aportar restricciones y control independiente.
6. Desarrollar despues las extensiones regionales, petrofisicas y conjuntas avanzadas. FWI, DAS, deformacion GNSS/InSAR y otros campos siguen siendo posibles ampliaciones; este inventario no pretende agotar toda la geofisica.

El orden es una propuesta tecnica basada en la reutilizacion y las brechas observadas, no un calendario ni una promesa de implementar simultaneamente todo el inventario.

## Arquitectura y aceptacion

- Core sin QGIS/Qt para contratos, coordenadas, unidades, errores, operaciones numericas y recetas.
- Dependencias opcionales por familia; los motores con dependencias incompatibles pueden ejecutarse en workers aislados con formatos de intercambio definidos.
- Identificadores estables de operaciones, version del metodo, versiones de librerias y hashes de entradas/codigo. La informacion de dependencias debe estar disponible en cada proceso, sin recargar el flujo principal.
- Distinguir dominio fisico y eje de proceso: tiempo, frecuencia, espacio y profundidad. Database/canal/grilla/traza son representaciones de datos, no nuevos dominios fisicos.
- Conservar CRS, datum horizontal y vertical, convencion de z, unidades, tiempos, geometria de fuente/receptor, calibracion, errores y mascaras. Un cero observado no equivale a dato ausente.
- Ejecucion por bloques o matrix-free donde proceda, estimacion previa de memoria y almacenamiento, cancelacion y checkpoints con estado explicito. Respetar los lanzadores, sesiones y bloqueos de desarrollo existentes.
- No declarar soporte de un formato por reconocer su extension: comprobar unidades, cabeceras, geometria, metadatos y round-trip cuando sea posible.
- Exigir respuesta directa conocida o independiente, pruebas de signos/unidades/adjuntos, ruido e interferencia, sensibilidad a parametros y un dataset real con metadatos. Un ajuste bajo no demuestra unicidad ni validez geologica.
- Separar estados propuesto, prototipo sintetico, contrastado con motor independiente, validado con datos reales y disponible en interfaz. No sumar esos estados como si fueran equivalentes.

La busqueda inicial genero documentacion y backlog. El desarrollo posterior
si incorpora operaciones numericas; consultar el registro de implementacion
enlazado arriba. No modifica bases privadas ni convierte propuestas en soporte
completo por el solo hecho de registrarlas.

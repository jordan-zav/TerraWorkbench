# Repositorios abiertos de referencia

Curaduría verificada el **2026-08-29**. “Referencia” significa material para
leer, probar y comparar; no implica que TerraWorkbench dependa de él ni que se
pueda copiar código sin revisar licencia y atribución.

## Núcleo de campos potenciales

| Proyecto | Cobertura útil | Licencia | Uso recomendado |
| --- | --- | --- | --- |
| [Harmonica](https://github.com/fatiando/harmonica) | GRD de Oasis, derivadas, RTP, continuaciones, Gaussianos, Bouguer, prismas/tesseroides, fuentes equivalentes y Euler | BSD-3-Clause | Primera referencia para convenciones, kernels y casos sintéticos |
| [Verde](https://github.com/fatiando/verde) | Gridding, tendencias, block reductions, splines y validación espacial | BSD-3-Clause | Preparación de puntos y validación de interpolación sin fuga espacial |
| [Boule](https://github.com/fatiando/boule) | Elipsoides, gravedad normal y coordenadas geocéntricas | BSD-3-Clause | GRS80/WGS84 y reducción gravimétrica geodésicamente consistente |
| [Choclo](https://github.com/fatiando/choclo) | Kernels Numba de gravedad y magnetismo para puntos y prismas | BSD-3-Clause | Modelado directo rápido y backend de sensibilidades |
| [xrft](https://github.com/xgcm/xrft) | FFT con `xarray`, coordenadas y dimensiones etiquetadas | MIT | Contrastar normalización, frecuencias y reconstrucción del motor FFT |
| [GMT](https://github.com/GenericMappingTools/gmt) | `grdfft`, filtros, derivadas, continuaciones y procesamiento de grillas | LGPL-3.0-or-later | Referencia madura independiente para respuestas espectrales |
| [PyGMT](https://github.com/GenericMappingTools/pygmt) | Interfaz Python a GMT y flujos reproducibles con grillas | BSD-3-Clause | Ejemplos, interoperabilidad y visualización; confirmar qué módulos GMT expone la versión usada |

## Suites comparables y diseño de QGIS

| Proyecto | Cobertura útil | Licencia | Uso recomendado |
| --- | --- | --- | --- |
| [PyGMI](https://github.com/Patrick-Cole/pygmi) | GUI de magnetismo, gravedad, raster, modelado 3D y otros métodos | GPL-3.0 | Comparar arquitectura, nombres, flujos de usuario y pruebas; revisar atribución antes de portar código |
| [SGTool](https://github.com/swaxi/SGTool) | Plugin QGIS/ArcGIS de cálculos de campos potenciales, incluidos RTP y pseudogravedad | MIT | Referencia directa de UX de Processing y formatos aceptados en QGIS |
| [QGIS](https://github.com/qgis/QGIS) | Processing, raster providers, tareas, docks y API del host | GPL-2.0 | Comportamiento nativo, cancelación, feedback y compatibilidad del plugin |
| [QGIS Documentation](https://github.com/qgis/QGIS-Documentation) | Manual de usuario, Processing y desarrollo | CC-BY-SA | Terminología y patrones documentales del ecosistema QGIS |

## Inversión, mallas y modelado directo

| Proyecto | Cobertura útil | Licencia | Uso recomendado |
| --- | --- | --- | --- |
| [SimPEG](https://github.com/simpeg/simpeg) | Inversión GRAV/MAG, MVI, regularización, directivas, incertidumbres y topografía | MIT | Backend principal y referencia de inversión 3D reproducible |
| [discretize](https://github.com/simpeg/discretize) | TensorMesh, TreeMesh, operadores y exportación | MIT | Diseño de mallas, activos topográficos y refinamiento |
| [geoana](https://github.com/simpeg/geoana) | Soluciones analíticas geofísicas | MIT | Oráculos sintéticos pequeños para pruebas |
| [pyGIMLi](https://github.com/gimli-org/pyGIMLi) | FEM/FV, inversión restringida y conjunta, mallas no estructuradas | Apache-2.0 | Segunda implementación independiente para diseño de inversión y regularización |
| [Euler inversion](https://github.com/compgeolab/euler-inversion) | Método moderno, datos y reproducción completa de localización Euler | CC-BY-4.0 | Referencia científica para una futura familia de profundidad/localización |
| [PyNoddy](https://github.com/cgre-aachen/pynoddy) | Modelos geológicos sintéticos y campos potenciales de Noddy | GPL-2.0 | Crear escenarios estructurales sintéticos; no convertirlo en dependencia silenciosa |
| [GemPy](https://github.com/gempy-project/gempy) | Modelado geológico implícito 3D y escenarios estocásticos | EUPL-1.2 | Futuro acoplamiento geología–propiedades–forward, no filtro de grilla |
| [LoopStructural](https://github.com/Loop3D/LoopStructural) | Modelado estructural implícito 3D | MIT | Modelos geológicos condicionantes y geometrías sintéticas |

## Campo principal, formatos e interoperabilidad

| Proyecto | Cobertura útil | Licencia | Uso recomendado |
| --- | --- | --- | --- |
| [ppigrf](https://github.com/IAGA-VMOD/ppigrf) | IGRF-14 puro en Python, geodésico y geocéntrico | MIT | Fuente actual de inclinación, declinación e intensidad del campo principal |
| [ESA MagneticModel](https://github.com/ESA-VirES/MagneticModel) | Modelos magnéticos esférico-armónicos y archivos SHC | Revisar por componente | Contrastar lectura de coeficientes y transformaciones de coordenadas |
| [GDAL](https://github.com/OSGeo/gdal) | GeoTIFF, GXF, ASCII, FileGDB y metadatos geoespaciales | MIT | Capa de interoperabilidad; respetar capacidades reales del driver instalado |
| [Rasterio](https://github.com/rasterio/rasterio) | API Python sobre GDAL para rasters | BSD-3-Clause | Pruebas independientes de geotransform, CRS, NoData y ventanas |

## Catálogos para ampliar la vigilancia

- [awesome-open-geoscience](https://github.com/softwareunderground/awesome-open-geoscience)
  mantiene un índice amplio de software y datos geocientíficos abiertos.
- [Fatiando a Terra](https://github.com/fatiando) permite seguir el conjunto
  Harmonica–Verde–Boule–Choclo como ecosistema, no como proyectos aislados.
- [SimPEG organization](https://github.com/simpeg) reúne el motor, mallas,
  soluciones analíticas, tutoriales y repositorios reproducibles de artículos.

## Política de lectura y reutilización

- Preferir API pública, documentación, tests y papers antes que copiar una función.
- Reimplementar desde la ecuación cuando sea viable y comparar contra dos fuentes.
- Registrar atribución incluso cuando una licencia permisiva no obligue a citar.
- Aislar dependencias GPL/EUPL/LGPL hasta revisar el efecto sobre distribución.
- No afirmar equivalencia con MAGMAP, Oasis montaj u otro motor propietario sin
  conjuntos de referencia y tolerancias explícitas.
- Fijar versiones solo en el entorno de ejecución; los enlaces de conocimiento
  deben apuntar al repositorio canónico y a documentación versionada cuando exista.


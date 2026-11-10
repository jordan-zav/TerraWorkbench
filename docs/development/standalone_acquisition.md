# Adquisicion y terreno independientes del host

La extraccion P0 agrega API directas al paquete terraworkbench_core.
No implica completar todos los modulos del inventario comercial.

El metodo adicional gravity.terrain_adaptive permite estaciones explicitas y
DEM mayores con tolerancia de aproximacion: [contrato adaptativo](../reference/methods/adaptive_terrain.md).
Devuelve atraccion del contraste del DEM, sin sustituir el termino de placa ni
las correcciones completas. El metodo de terreno historico conserva su conducta.

- preprocessing conserva los helpers historicos de QC. El modulo raiz es un
  adaptador de compatibilidad que comparte las mismas funciones, no una copia.
- geomagnetism.igrf_field evalua IGRF por bloques con ppigrf, opcional mediante
  el extra geomagnetism. Entradas geodeticas en grados y altura en kilometros;
  salida este/norte/arriba en nT. La fecha debe estar dentro de las epocas del
  archivo SHC instalado, cuyo hash se registra. No se convierte datum vertical.
- terrain_gravity.terrain_correction_prisms usa el extra prisms (Harmonica).
  Calcula placa menos atraccion del DEM finito, en mGal, con ejes ENU en metros
  y densidades explicitas. Procesa estaciones por bloques, comprueba limites
  de celdas/interacciones y atiende cancelacion entre llamadas del motor.
  Sigue siendo O(celdas al cuadrado); no es terreno multirresolucion ni asegura
  un tiempo o pico de memoria para cualquier levantamiento.
- coordinates.reproject_xy usa el extra coordinates (PyProj). Solo CRS
  horizontales 2D, always_xy, sin transformaciones aproximadas ballpark ni
  sustitucion silenciosa de una operacion mejor que necesita rejillas ausentes.
  Los pares no finitos se conservan como NaN. No transforma alturas.

Los adaptadores QGIS de IGRF y terreno llaman ahora a estos kernels. El host
conserva lectura de capas, convenciones de grilla y contexto de transformacion
del proyecto. Su reproyeccion QGIS no se sustituye por PyProj a escondidas.
El catalogo experimental registra ahora magnetic.igrf, gravity.terrain_prisms y
potential.reproject_xy con sus formularios EN/ES/PT. Tambien se invocan desde
Python, ARCHIE o workflows del Core; el contexto CRS del proyecto QGIS no cambia.

Las unidades y signos del motor de prismas se contrastan con la
[documentacion de Harmonica](https://www.fatiando.org/harmonica/latest/_modules/harmonica/_forward/prism_layer.html).
Las componentes de IGRF siguen la
[API oficial de ppigrf](https://github.com/IAGA-VMOD/ppigrf).

Las pruebas incluyen identidad del adaptador QC, comparacion con motores
originales, cancelacion, presupuestos de trabajo, agua/terreno, origen plano,
reproyeccion UTM y rechazo de CRS 3D. No son validacion de campo ni equivalencia
con software propietario. Siguen pendientes el QC espacial completo, importadores
independientes de raster y terreno adaptativo/multirresolucion.

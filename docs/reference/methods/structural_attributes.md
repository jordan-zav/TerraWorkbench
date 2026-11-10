# Atributos estructurales del Core

Estas APIs de Python producen atributos matematicos y geometrias de candidatos.
No asignan fallas ni litologias. No constituyen equivalencia con CET. Se
registran en la familia structural con formularios EN/ES/PT en el centro de
procesos y pueden encadenarse mediante workflows del Core.

## Fase multiescala

terraworkbench_core.structural_attributes.monogenic_phase_attributes usa filtros
log-Gabor y transformadas de Riesz. Devuelve simetria de fase, alineamiento de
fase sin ponderacion espectral, amplitud y azimut axial de la normal.
Se declaran longitudes de onda, ancho de banda, polaridad y umbral de ruido
en unidades del campo. No hay estimacion automatica de ruido ni penalizacion
de desviacion de fase del metodo completo de Kovesi.

La grilla debe estar completa, con filas que aumentan al norte y columnas al
este; el espaciado se expresa en metros. Un raster habitual con filas hacia
el sur necesita reorientacion explicita. El relleno reflejado y la exclusion
de bordes son parametros registrados. Un borde excluido no certifica que el
resto carezca de efectos de frontera. La orientacion indefinida se devuelve NaN.

## Textura y diversidad de orientaciones

local_grid_texture calcula entropia de Shannon en bits y desviacion estandar
poblacional. La ventana impar, intervalo de cuantizacion y numero de bins
determinan el resultado. Los valores fuera del intervalo se rechazan; los NaN
son ausentes y se cuentan. Fuera de la grilla no se fabrica soporte.

local_orientation_entropy cuantiza azimuts axiales modulo 180 grados usando
un origen de bins explicito. Cada muestra tiene el mismo peso. Devuelve
entropia, entropia normalizada y conteo de soporte. No es una medida de densidad
de contactos ni pondera longitud, confianza o procedencia geologica.

## Caminos del esqueleto

terraworkbench_core.lineament_geometry.skeleton_paths acepta una mascara
booleana definida por el llamador. Usa thinning de Zhang de scikit-image,
dependencia opcional declarada en el extra structure. NumPy y SciPy realizan
los otros calculos; no hay ejecutables propietarios.

El origen XY representa el centro del pixel inicial, en metros proyectados.
Se separan caminos en extremos y ramificaciones, se cierran ciclos y se
devuelven pixeles aislados por separado. Conectividad 8 elimina atajos
diagonales si hay un vecino ortogonal que ya conecta los pixeles. Los caminos
conservan geometria de centros de pixel: sin suavizado ni union de huecos.
Se registran longitudes, azimuts axiales por segmento y omisiones por longitud.

Hay presupuestos explicitos de celdas, bins, vertices y caminos, ademas de
cancelacion. Estos limites controlan trabajo, no garantizan memoria o tiempo.

## Verificacion y limites

Las pruebas usan bandas sinteticas, inversion de contraste, invariancia de
escala, histogramas conocidos, orientaciones axiales, cruces y ciclos.
Tambien se comprueba el uso desde un wheel instalado fuera del checkout.
Faltan validacion con interpretaciones independientes y sensibilidad en datos
de campo. No hay deteccion circular de porfidos ni clasificacion geologica.

Referencias: [atributos de fase de Kovesi](https://peterkovesi.github.io/ImagePhaseCongruency.jl/stable/functions/)
y [morfologia de scikit-image](https://scikit-image.org/docs/stable/api/skimage.morphology.html).

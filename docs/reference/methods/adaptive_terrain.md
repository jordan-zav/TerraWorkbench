# Atraccion adaptativa del DEM en estaciones

terraworkbench_core.adaptive_terrain.terrain_gravity_adaptive, registrada como
gravity.terrain_adaptive, calcula el campo del contraste de densidad de un DEM
finito en estaciones ENU explicitas. Cuenta con formulario EN/ES/PT, ejecucion
desde workflows y API independiente de QGIS. No cambia el algoritmo historico.

## Contrato del modelo

Los ejes este y norte son centros de celda, uniformes y crecientes, en metros.
La matriz del DEM debe estar completa y las estaciones tienen forma N por 3,
este/norte/arriba. El plano reference_elevation_m es prescrito en la misma
referencia vertical; no se infiere un datum, altura de vuelo o interpolacion.
Sobre el plano, la densidad es density_crust. Debajo es el contraste
density_water menos density_crust. Se conservan por separado masas positivas
y negativas para evitar centroides artificiales por cancelacion.

La salida prism_effect_mgal es atraccion vertical, positiva hacia abajo, en
mGal. No es una correccion completa de terreno o Bouguer ni incluye mareas.
No incluye masas fuera del DEM ni curvatura terrestre. Que un CRS este en
metros no garantiza que una aproximacion cartesiana sea apropiada a esa escala.
Revisa el dominio espacial y el datum antes de usarlo en una reduccion fisica.

## Arbol y control de aproximacion

Se divide el DEM en rectangulos y se conservan masa, centroide y segundo momento
central absoluto de cada signo. Los momentos se acumulan de forma estable,
incluyendo la varianza interna de cada prisma uniforme. Cerca de una estacion
se usan los prismas analiticos de Harmonica. Los grupos lejanos se representan
como masas puntuales en sus centros de masa.

Sea J la integral de abs(dM) por la distancia cuadratica al centro de masa,
R el radio de una esfera que contiene todo el volumen del grupo, y d la
distancia de la estacion al centro. Para d mayor que R se usa la cota:

    E_grupo <= 12 G 10^5 J / (d - R)^4

La cota es una derivacion del resto de Taylor de segundo orden. Para
f(r)=r_z/abs(r)^3, la norma del Hessiano no excede 24/abs(r)^4; el termino
lineal se anula al usar el centro de masa, y el factor 1/2 del resto da 12.
La distancia minima en el volumen es al menos d-R. El factor 10^5 convierte
m/s2 a mGal. Se suman cotas absolutas de ambos signos; la cancelacion del
campo no reduce artificialmente la estimacion del error.

Se refinan primero los nodos con mayor cota hasta que la suma de las cotas
retenidas cumple absolute_tolerance_mgal. Cero solicita todos los prismas
exactos. leaf_cells regula el tamano maximo de las hojas, no una resolucion
geologica ni un radio de correccion. No se descartan prismas delgados.

La cota cubre solamente truncamiento de monopolos. No es un intervalo
estadistico, una demostracion de redondeo IEEE ni incertidumbre del resultado
fisico. Excluye errores del DEM, densidad, datum, posicion, curvatura, redondeo
y terreno externo no suministrado. La precision del kernel exacto tambien es
finita. Las pruebas comparan diferencias observadas con estas cotas.

## Recursos y trazabilidad

Construccion y recorrido se compilan con Numba, declarado junto a Harmonica
en el extra prisms y en requirements/base.txt. NumPy/SciPy siguen declarados en el
Core. No se incluyen ejecutables ni codigo propietario. La compilacion inicial
tiene un coste adicional; el codigo compilado se conserva en memoria durante
el proceso, sin crear una cache en disco desde este modulo.

Los limites predeterminados son 4 millones de celdas y 100 mil estaciones,
ademas de limites de nodos, visitas y evaluaciones exactas. Son presupuestos
de datos/trabajo, no garantias de RAM o tiempo. Los arreglos internos del arbol
y las copias temporales requieren memoria adicional. Una tolerancia estricta
puede acabar en una suma exacta densa o agotar un presupuesto. Para un DEM
pequeno o pocas estaciones, el metodo exacto puede ser mas rapido.

Se comprueba cancelacion antes y despues de construir el arbol y entre fases
de cada estacion. Una compilacion o kernel nativo en curso termina antes de
atenderla. Las tareas incompletas no se publican como workflows completos.

El resultado conserva cota por estacion, conteos de prismas exactos, monopolos
y visitas, referencia del modelo, constante G, versiones de bibliotecas y
SHA256 de los dos modulos del Core. La traslacion numerica a un origen local
evita que los centroides dependan de grandes offsets UTM. No transforma el CRS.

## Uso

    from terraworkbench_core.operations import run_operation
    result = run_operation(
        "gravity.terrain_adaptive",
        easting=east_axis_m, northing=north_axis_m, elevation_m=dem_m,
        observation_xyz=station_enu_m, density_crust=2670., density_water=1040.,
        reference_elevation_m=0., absolute_tolerance_mgal=0.01,
    )
    attraction = result["result"]["prism_effect_mgal"]

Los valores del ejemplo son ilustrativos, no parametros certificados para
un survey. El plano cero solo se usa si corresponde a la referencia elegida.

## Verificacion

Se contrastan la suma exacta y la aproximacion contra prismas de Harmonica,
incluyendo masas de ambos signos, estaciones interiores y exteriores al DEM,
tolerancias sucesivas, varios tamanos de hoja, traslacion UTM, plano vertical,
modelo vacio, preservacion de entrada, presupuestos y cancelacion.
Los ensayos de escala usan DEM sinteticos y no certifican una campana real.
La mejora de tiempo depende del numero de estaciones, tolerancia y geometria.

Referencias de convenciones: [prismas de Harmonica](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)
y [masas puntuales](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.point_gravity.html).
Contexto general de metodos jerarquicos: [Barnes y Hut, 1986](https://doi.org/10.1038/324446a0).
La cota y el ejecutor descritos aqui son propios; no se atribuye paridad con
un codigo o producto externo.

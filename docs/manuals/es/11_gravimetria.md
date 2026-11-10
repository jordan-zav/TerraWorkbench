# 11. Gravimetría terrestre, redes y modelos 2D

[English](../en/11_gravimetria.md) · [Español](../es/11_gravimetria.md) · [Português](../pt/11_gravimetria.md)

## De la lectura instrumental a una anomalía

Una reducción empieza identificando qué contiene la entrada: lectura relativa, gravedad observada calibrada, perturbación, anomalía de aire libre o Bouguer. Las correcciones instrumentales y de movimiento deben resolverse antes de interpretar una anomalía como efecto del subsuelo. No inferir el estado del dato por el nombre de archivo.

normal_gravity_grs80 devuelve gravedad normal sobre el elipsoide GRS80, en mGal, mediante Somigliana. La variante normal_gravity_somigliana admite constantes explícitas; si se cambian, el resultado ya no debe etiquetarse automáticamente GRS80. La elevación del receptor y la del terreno participan en términos distintos.

## Esquema de reducción

Con una convención terrestre habitual, la anomalía simple de Bouguer combina gravedad observada, gravedad normal, término de aire libre y atracción de placa:

    g_B_simple = g_observada − γ + C_aire_libre − C_placa

El término de placa depende de densidad y altura de terreno; el de aire libre, de altura de observación. Mantener explícito el coeficiente de placa, sus unidades y la referencia de altura. land_gravity_reduction solicita estos elementos en su contrato y produce procedencia numérica.

La anomalía completa añade el término de terreno y, según la receta, curvatura u otras reducciones. Comprobar que la atracción o corrección recibida tiene el signo y la definición esperados. Una perturbación de gravedad evaluada con gravedad normal a la altura correspondiente no es idéntica a todas las definiciones de anomalía de aire libre.

## Redes y deriva

adjust_gravity_network estima una red con información de estaciones, instrumentos, tiempos y referencias. Las anclas fijan el datum; si tienen incertidumbre, no tratarlas después como exactas ni olvidar la covarianza común que inducen. Una deriva estimada no corrige automáticamente mareas o cargas no suministradas.

fit_bouguer_density explora densidad bajo una relación estadística declarada. La asociación entre anomalía y topografía puede reflejar estructura geológica además de densidad de reducción. Evaluar rango, residuos y sensibilidad antes de adoptar un valor único para toda el área.

## Perfiles poligonales

polygon_gravity_2d utiliza cuerpos de sección X/Z positiva hacia arriba, densidad en kg/m³ y extensión infinita normal al perfil. Devuelve componente vertical positiva hacia abajo en mGal. fit_polygon_densities estima propiedades con geometría fijada; no recupera automáticamente vértices o extensión lateral finita.

## Controles de aceptación

Verificar latitud, datum horizontal, altura, escala instrumental, bases repetidas, deriva, término de aire libre, densidad y topografía. Examinar cada corrección por separado. Al entrar a inversión, confirmar si el vector observado está definido hacia arriba o hacia abajo y si expresa contraste respecto a un regional.

Ver [reducciones y convenciones](../../development/standalone_acquisition.md), [redes y perfiles](../../validation/reports/2d_extensions.md) y [gravedad normal de Boule](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html). Los valores por defecto de una función no sustituyen los metadatos del levantamiento.

## Implementación relacionada

[gravity_corrections](../../../terraworkbench_core/gravity_corrections.py), [gravity_network](../../../terraworkbench_core/gravity_network.py), [gravity_profiles](../../../terraworkbench_core/gravity_profiles.py)

---

[Índice](README.md) · [Anterior](10_magnetometria.md) · [Siguiente](12_terreno_isostasia.md)

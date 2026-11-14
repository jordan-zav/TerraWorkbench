# Densidad y susceptibilidad aparentes

terraworkbench_core.apparent_properties proporciona dos APIs directas:
layer_property_response calcula la respuesta de una capa;
apparent_layer_property estima contrastes aparentes para esa geometria.
Estan registradas como potential.layer_response y potential.apparent_property,
con formularios EN/ES/PT y uso desde workflows del Core.

## Modelo y unidades

Se supone una capa horizontal, continua y periodica lateralmente, con propiedad
constante con la profundidad. La profundidad del techo h es no negativa y el
espesor t es positivo; ambos se declaran en metros desde el plano de observacion.
No se determinan automaticamente desde los datos. La grilla debe estar completa,
con filas que aumentan al norte y columnas al este. No se rellenan NaN ni se
aplican padding o detrend automaticamente.

La densidad es un contraste en kg/m3 y la respuesta gravitatoria es mGal,
positiva hacia abajo. Para numero de onda angular k > 0, el operador es:

    K_g(k) = 2 pi G 10^5 exp(-kh) [1 - exp(-kt)] / k

La respuesta de una densidad uniforme es el limite de losa infinita
2 pi G 10^5 t rho. G se obtiene de scipy.constants y se registra en la receta.

La susceptibilidad es adimensional SI. La respuesta magnetica es la proyeccion
lineal de la anomalia sobre un campo de referencia F declarado en nT:

    d = sin(I) + i cos(I) [ke sin(D) + kn cos(D)] / k
    K_chi(k) = F/2 exp(-kh) [1 - exp(-kt)] d^2

I es positivo hacia abajo y D se mide en sentido horario desde el norte de la
grilla. Se supone magnetizacion inducida, sin remanencia ni correccion de
autodesmagnetizacion. La susceptibilidad uniforme no produce campo externo
en esta capa periodica. No se resta IGRF ni se corrigen terreno o datum.

El modelo expresa la susceptibilidad en unidades SI.

## Estabilizacion y resultados

La inversa usa conjugado(K) / (abs(K)^2 + lambda^2). El parametro
regularization_response declara lambda en unidades de datos por unidad de
propiedad; max_inverse_gain limita la amplificacion en unidades reciprocas.
minimum_wavelength_m aplica un corte radial explicito, al menos dos veces el
mayor espaciado. Los ejes de Nyquist de grillas pares se excluyen y registran.

Se elimina y registra la media observada; background lo elige el llamador y
no se estima a partir de esa media. Esto tambien aplica a gravedad, aunque
el forward pueda representar la componente uniforme de una losa.
El resultado incluye propiedad, contraste, anomalia predicha y residual,
RMS residual, mascara de frecuencias observables dentro de banda y transferencia
de resolucion espectral. La mascara no garantiza recuperacion fuerte:
la transferencia puede ser muy pequena por damping o por el limite de ganancia.
Ninguno de estos indicadores es incertidumbre geologica ni validacion de campo.

En el ecuador magnetico hay modos transversales no observables. No se recuperan
con una direccion inventada: se conservan en los residuales. Los contrastes
pueden tener signo negativo y no se convierten en propiedades fisicas calibradas.

La receta incluye parametros, unidades, versiones NumPy/SciPy y SHA256 de este
modulo y cuatro dependencias directas del Core. No es un hash completo del
entorno ni una huella de los datos de entrada. Hay limite de celdas y cancelacion.

## Uso de la API

    from terraworkbench_core.apparent_properties import apparent_layer_property
    result = apparent_layer_property(
        gravity_grid_mgal, (25., 25.), kind="density",
        top_depth_m=50., thickness_m=300., background=0.,
        regularization_response=0.001, max_inverse_gain=10000.,
        minimum_wavelength_m=100.,
    )

Los numeros del ejemplo no son parametros recomendados para un survey.
Debe revisarse sensibilidad a profundidad, espesor, banda y regularizacion.

## Verificacion

Las pruebas comparan modos oblicuos conocidos, amplitud y fase, recuperacion
sin damping, atenuacion regularizada, limite de losa, componente uniforme,
modos magneticos no observables, corte de banda, ganancia y cancelacion.
Tambien contrastan las formulas con una malla finita de prismas de Harmonica
en una zona central: tolerancia del 2 por ciento, por truncamiento lateral y
discretizacion por celdas frente al modelo continuo. No es una equivalencia
exacta ni una prueba de sensibilidad en datos de campo.

Referencias independientes de convenciones y unidades:
[prismas gravitatorios](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html)
y [prismas magneticos](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_magnetic.html).

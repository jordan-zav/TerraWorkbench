# Modelos magneticos compactos experimentales

terraworkbench_core.compact_magnetics contiene dos API Python independientes
de QGIS: magnetic_dipole_field y fit_magnetic_dipoles. Usan NumPy/SciPy,
ya declarados por el Core. No incluyen codigo ni bibliotecas propietarias.

## Forward

Observaciones y fuentes son coordenadas locales ENU en metros. Los momentos
son vectores este/norte/arriba en A m2; se devuelve anomalia vectorial en nT.
El modelo es un dipolo puntual, no un cuerpo de geometria conocida. Se exige
distancia minima explicita y se comprueba el presupuesto observaciones por
fuentes. Hay procesamiento por bloques y cancelacion entre bloques.

Se registra mu0 usado, segun scipy.constants. El contraste independiente usa
[dipolos de Harmonica](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.dipole_magnetic.html).
Una diferencia minima entre constantes fisicas de bibliotecas no se oculta
como igualdad byte a byte.

## Ajuste local

Se requieren numero y posiciones iniciales de fuentes, momentos iniciales,
cotas de posiciones/momentos, ruido por observacion y separacion minima.
Las fuentes deben permanecer debajo de todas las observaciones. No se
deduce un fondo regional ni una calibracion de sensor.

El ajuste puede usar las tres componentes o su proyeccion de anomalia pequena
sobre un campo I/D constante y explicito. No equivale al cambio exacto de
la norma del campo total. Los errores se tratan independientes; no se inventa
una covarianza instrumental ni se reescala el ruido para conseguir un buen fit.

El Jacobiano se normaliza por columnas para revisar rango sin confundir
metros con A m2. La covarianza local solo se devuelve si el optimizador
convergio, el Jacobiano es de rango completo y la matriz es finita. Se usa
una traslacion numerica registrada para evitar pasos de diferencias finitas
proporcionales a coordenadas UTM grandes; las posiciones se devuelven en
el marco original. Es una linealizacion condicional,
no incertidumbre geologica total. El resultado conserva limites activos,
residuales, estado del solver, cantidad de llamadas y presupuestos de trabajo.
Las llamadas de diferencias finitas y la prediccion final cuentan en el limite.

## Lo que NO implica

- No selecciona automaticamente cuantos objetivos existen.
- No identifica dimensiones, material, forma, clase ni contenido explosivo.
- No procesa ni clasifica datos EM61, MetalMapper o bibliotecas AGC.
- No certifica deteccion de UXO, seguridad ni liberacion de un terreno.
- Un buen residual no elimina no unicidad, minimos locales ni errores de
  posicion, altura, orientacion, calibracion o sustraccion regional.

Es una base numerica para futuros workflows de objetivos, no el cierre de
los modulos UXO Land, UXO Marine, Potent ni UX-Analyze.

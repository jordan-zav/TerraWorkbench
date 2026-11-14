# Componentes magneticas e integracion de gradientes

Las API directas de terraworkbench_core.magnetic_components no dependen de QGIS.
Son una primera implementacion con pruebas sinteticas.

## Contrato comun

- Grilla completa, regular y a nivel; limites periodicos. No se rellena NoData
  ni se aplica padding/detrend automaticamente. Revisar continuidad de bordes.
- Filas en norte creciente y columnas en este creciente; un raster north-up
  normalmente necesita reorientacion previa. Espaciado: norte/este en metros.
- Las filas/columnas Nyquist de dimensiones pares se excluyen y contabilizan.
  Esta politica evita interpretar como recuperadas direcciones no resolubles
  a esa frecuencia. No es una conversion de banda completa en esos modos.
- El valor medio de salida se exige como parametro. No se recupera el datum
  del campo a partir de derivadas o de otra componente.

## Conversion de componentes

convert_field_component admite total, east, north, up y down en nT. Total es
la proyeccion de anomalia pequena sobre un campo de referencia constante,
NO el cambio exacto de la norma vectorial. Inclinacion positiva abajo y
declinacion desde norte de grilla hacia este, en grados, son obligatorias si
interviene total. No se presupone magnetizacion inducida para convertir
componentes en una region libre de fuentes.

Con D como componente abajo, los operadores son E/D=i*ke/k, N/D=i*kn/k,
U/D=-1 y T/D=sin(I)+i*cos(I)*(ke*sin(dec)+kn*cos(dec))/k. Se usa una inversa
amortiguada y un limite de ganancia adimensional; se registran modos recortados
y no observables. La estabilizacion puede cambiar amplitudes.

## TMI desde gradientes

reconstruct_tmi_from_gradients recibe uno o varios gradientes en nT/m, con
vertical positiva ARRIBA. Integra por minimos cuadrados espectrales usando
operadores i*ke, i*kn y -k. El valor medio es explicito. Las ponderaciones son
relativas y positivas, no una covarianza estimada. La amortiguacion se expresa
como numero de onda angular en rad/m.

Devuelve TMI en nT, predicciones de los gradientes, residuales RMS y una mascara
de frecuencias resolubles. Un unico gradiente horizontal no determina todos
los modos; los ausentes quedan a cero con diagnostico, no como datos medidos.
Una buena consistencia algebraica no demuestra unicidad ni interpretacion geologica.

## Verificacion y alcance

Se prueban las cinco componentes de un potencial armonico analitico, recuperacion
de TMI con datum conocido, amortiguacion, modos no observables, Nyquist, ganancia,
cancelacion y NoData. Un benchmark adicional contrasta la conversion U/E con
prismas magneticos independientes de Harmonica en la region central de una
ventana amplia. El borde finito y la periodicidad no son equivalentes.

[Modelo directo en ENU de Harmonica](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_magnetic.html).

## Operador radial tabulado

terraworkbench_core.radial_filters.tabulated_radial_filter recibe numeros de
onda ANGULARES en rad/m y ganancias reales. Interpola linealmente y conserva
la ultima ganancia por encima del ultimo nodo. El nodo inicial debe estar
en cero; su ganancia controla la media. Un presupuesto de ganancia absoluta
explicito rechaza tablas que lo excedan, sin recortarlas silenciosamente.
Las unidades de salida son las de entrada. No lee archivos propietarios
de control ni supone que sus numeros de onda esten en radianes.

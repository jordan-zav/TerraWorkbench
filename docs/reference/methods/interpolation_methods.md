# Interpoladores independientes

Actualizado el 24 de septiembre de 2026. El método de mínima curvatura predeterminado usa diferencias finitas, restricciones fuera de nodo y refinamiento multirresolución. Es independiente y experimental; no se certifica equivalencia exacta con RANGRID. Sin(x)/x interpola muestras regulares mediante una ventana Lanczos explícita.

## Uso

En Interpolar puntos de levantamiento a GeoTIFF se conservan los índices: 0 IDW, 1 vecino cercano, 2 TPS global, 3 TPS local, 4 sin(x)/x regular y 5 mínima curvatura experimental.

Para puntos GPS dispersos, usar un interpolador de puntos. El método sinc exige una retícula regular y los espaciados originales X/Y; rechaza puntos irregulares. Para expandir una grilla regular, usar sinc_interpolation, con FACTOR_X, FACTOR_Y y LOBES. Conserva centros y valores de muestras originales y no extrapola más allá de los centros extremos. Reducir el tamaño de celda no aumenta la resolución medida.

## Mínima curvatura

El método vigente aplica la ecuación biharmónica en nodos libres y acopla las observaciones fuera de nodo mediante restricciones de Briggs. Se obtiene una aproximación del laplaciano ajustando los momentos de cuatro vecinos y la observación, exacta para polinomios cuadráticos. Ese laplaciano se incorpora a la ecuación de curvatura; no se sustituye simplemente por una restricción de valor interpolado de Taylor. Para tensión t se utiliza (1 − t) Δ²u − t Δu = 0. Un dato exactamente coincidente fija el valor del nodo; no se aplica un radio de ajuste artificial.

Los datos se agrupan por celdas centradas en nodos. Se conservan el centroide XY y el promedio del canal; esto ocurre incluso con desmuestreo 1. En cada nivel se selecciona como máximo un dato de trabajo por nodo. No se afirma que la grilla pase por cada observación original individualmente.

La semilla inicial utiliza distancia inversa dentro del radio de búsqueda, con la potencia seleccionada. Si no hay vecinos, usa el promedio de los datos de trabajo. Después se realizan pasadas Gauss-Seidel por factores 16, 8, 4, 2 y 1, empezando en el factor elegido. La cota de iteraciones por nivel es el máximo final dividido por el factor, con mínimo una pasada. La superficie previa se prolonga bilinealmente. Cada nivel grueso redondea temporalmente su dominio a sus propios intervalos. El nivel final conserva los límites físicos alineados a la celda fina, añade dos nodos de margen por lado y se recorta al final; ya no hereda la extensión oriental y septentrional de la malla gruesa. El plano retirado antes del cálculo se restaura al terminar.

Los nodos libres emplean el operador derivado de la energía discreta ||Dxx u||² + 2||Dxy u||² + ||Dyy u||², con bordes naturales discretos. Al sustituir filas para imponer observaciones fuera de nodo, el sistema es de colocación: no es el sistema variacional con fuerzas adjuntas distribuidas. La formulación, los bordes y la escala de tensión son propios y no están certificados como idénticos a Oasis.

Se comprueban tres porcentajes por pasada: cambio de nodos, residuo de ecuación dividido por su diagonal y residuo en los datos de trabajo. Solo se declara convergencia si los tres alcanzan el porcentaje exigido dentro de la tolerancia. Un límite de iteraciones alcanzado se informa explícitamente. No se confunde cumplimiento de restricciones con coincidencia frente a Oasis.

Radio inicial, malla gruesa, potencia y porcentaje de paso están conectados al solver multirresolución. Pendiente de ponderación distinta de cero sigue rechazada por falta de implementación verificada. El blanking utiliza la distancia a las observaciones originales, después de resolver. Hay una cota de 250.000 nodos de trabajo, incluidos márgenes. La cota limita el tamaño del dominio de trabajo.

El backend conserva solver="variational" como alternativa explícita. Conserva las restricciones de Taylor y resuelve directamente el sistema de mínima energía con multiplicadores de Lagrange y verifica sus residuos. Ese modo registra como no utilizados los controles de semilla y porcentaje de paso. La operación QGIS predeterminada usa el modo multirresolución.

## Sin(x)/x

Sinc usa sinc(t) = sin(πt)/(πt), con valor 1 en cero, multiplicada por sinc(t/a) dentro del soporte a. El argumento usa el espaciado original de muestras. Se normalizan pesos en bordes truncados. Si falta una muestra interior necesaria, la salida queda NoData. Los duplicados se promedian y las muestras originales se conservan. No se certifica equivalencia con otros productos.

El tamaño de celda de salida es una elección de remuestreo. Reducirlo no incrementa la resolución medida. La implementación exige una retícula regular; no acepta directamente puntos GPS irregulares.

# Protocolo de evaluación del software: versión 1.0

## Pregunta y alcance

¿Permite TerraWorkbench acceder desde QGIS a flujos geofísicos trazables, con resultados numéricos reproducibles y un Core utilizable también sin el host? El eje acordado con el autor es democratizar el acceso al procesamiento y la inversión geofísica mediante QGIS. Acceso se documenta mediante integración, idiomas, contratos y material reproducible. Reducir barreras es una motivación; no se afirmará una mejora cuantificada de productividad, aprendizaje o adopción sin estudio con usuarios.

## Diseño y exposición previa

La campaña primaria repite seis flujos sobre datos públicos reales: gravedad, magnetometría, interpolación, terreno, canales y radiometría. Esos datos y resultados anteriores ya se exploraron. Congelar ahora la receta evita cambios durante esta repetición, pero no la convierte en un ensayo ciego ni en una preregistración externa. La evidencia histórica permanece separada y completa.

Dos ejemplos de inversión de los tutoriales SimPEG constituyen controles secundarios. Sus observaciones son ejemplos simulados de tutorial; no se presentan como campañas de campo ni como recuperación geológica. La partición histórica cada quinta estación se conserva por reproducibilidad y no sustituye validación por regiones o líneas independientes.

## Datos, incertidumbres y criterios

El JSON del protocolo fija selección, malla, presupuesto, incertidumbre, referencias y criterios. El hash del código fija también todos los parámetros internos y tolerancias de los seis flujos. Los umbrales de regresión heredados de los ensayos anteriores son controles de ingeniería, no límites universales de exactitud geofísica. No se ajustan sigmas o porcentajes después de ver resultados para conseguir un aprobado.

Se conservarán RMS/RMSE en sus unidades, WRMS con la incertidumbre declarada, errores respecto de referencias y diagnósticos del solver. NRMSE en porcentaje exige declarar denominador y conjunto. Una referencia constante produce NRMSE indefinido. Un porcentaje de error de modelo requiere un modelo conocido; el residual de datos de campo no es una medida de recuperación del subsuelo.

## Congelación y cambios

Antes de ejecutar se genera freeze-v1.json con hashes normalizados a LF del Core, ejecutores, protocolo y registro de datos. Se conserva en un commit anterior a los resultados de esta campaña. Cada ejecución verifica la fuente antes y después, crea una carpeta nueva y registra commit, fecha y entorno. La congelación no fija bit a bit hardware ni bibliotecas nativas: sus versiones se registran por ejecución y se comparan mediante tolerancias declaradas.

Un cambio de algoritmo, parámetros, particiones o criterios exige versión nueva, hash padre, motivo y nueva ejecución. Se retienen fallos y ejecuciones sustituidas. No se sobrescribe una congelación ni se reescriben métricas históricas. Un fallo nuevo se clasifica como adquisición de datos, entorno, contrato, precisión numérica o limitación científica antes de decidir una corrección.

## Evidencia y publicación

La API y QGIS tienen funciones distintas: el Core ejecuta la matemática y el host presenta entradas, metadatos y productos. Las pruebas QGIS y capturas offscreen son evidencia de integración, no ensayos humanos de usabilidad ni confirmación geológica. Los tiempos son observaciones por equipo; no se atribuye superioridad de rendimiento sin comparación controlada.

Las afirmaciones y su soporte se registran en claims.md. Todos los resultados, incluyendo fallos, van al registro de campaña. El CSV histórico relaciona cada métrica con su JSON pointer y registro original, evitando sumar diagnósticos anidados como experimentos independientes.

El manuscrito se prepara en Markdown con tablas e imágenes y declaración del uso de IA. No se inventan autores, afiliaciones, financiación, permisos o DOI. La selección de revista y el envío quedan pendientes. Si se opta por JOSS se comprobarán de nuevo sus [instrucciones oficiales](https://joss.readthedocs.io/en/latest/paper.html); no se configura compilación PDF.

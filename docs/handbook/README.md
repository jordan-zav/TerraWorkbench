# TerraWorkbench Knowledge Base

Base de conocimiento técnica para construir un entorno abierto y reproducible de
magnetometría, gravimetría, radiometría gamma, procesamiento espectral, control de levantamientos,
modelado directo e inversión dentro de QGIS.

Esta carpeta no es una lista de funciones deseadas ni una afirmación de paridad
con software comercial. Separa explícitamente:

1. **Fundamento científico**: fórmulas, convenciones, supuestos y limitaciones.
2. **Cobertura real**: lo que TerraWorkbench implementa y prueba hoy.
3. **Referencias de software**: código abierto para estudiar y contrastar.
4. **Brechas**: capacidades candidatas que requieren diseño, validación y pruebas.

## Navegación

El [manual completo por capítulos EN/ES/PT](../manuals/README.md) desarrolla desde cero
los contratos, procedimientos y límites del código disponible, con ejemplos
artificiales ejecutables, imágenes y referencia de API generada desde la fuente.
Sus tres ediciones extensas tienen 28 capítulos y un lector en la GUI. Complementan las fichas resumidas del manual práctico, que conservan su fuente y exportador independientes.

La [validación de recuperación voxel](../validation/reports/voxel_recovery_validation.md) separa
ajuste de datos, precisión numérica y recuperación de cuerpos. Documenta límites
por celda, hipótesis espaciales y pruebas con geometrías reservadas, sin convertir
un buen ajuste en una afirmación de geología única.

La entrada recomendada es el manual práctico trilingüe, con 15 capítulos y 30
fichas técnicas equivalentes, ecuaciones compartidas y enlaces a documentación primaria. Está
disponible en la GUI con buscador y selector de capítulos. Incluye importación
GRD, canales, SRC, filtros, magnetometría, gravimetría, radiometría, interpretación
de fuentes, inversión, métodos eléctricos/EM, georradar, sísmica y registros LAS.

- [Manual práctico en español](handbook_es.md)
- [Practical handbook in English](handbook_en.md)
- [Manual prático em português](handbook_pt.md)

Los documentos históricos siguientes se conservan sin recortar. Su detalle no
es idéntico entre idiomas; el manual práctico es la referencia común sincronizada.
La referencia técnica original de las APIs se identifica explícitamente como
inglés y se abre a petición del usuario. Identificadores, nombres de canales,
claves JSON y mensajes originales de librerías no se renombran al cambiar idioma.

| Documento | Propósito |
| --- | --- |
| [Referencia de campos potenciales — Español](geofisica_potencial_referencia.md) | Referencia científica: MAG, GRAV, FFT, preparación e inversión 3D |
| [Potential-field reference — English](potential_fields_reference_en.md) | English user reference for the same TerraWorkbench scientific domains |
| [Referência de campos potenciais — Português](potential_fields_reference_pt.md) | Referência científica em português para os mesmos domínios do TerraWorkbench |
| [Repositorios de referencia](repositorios_referencia.md) | Proyectos abiertos clasificados por función, licencia y forma segura de uso |
| [Mapa de cobertura y brechas](roadmap_cobertura.md) | Qué existe, qué falta y en qué orden conviene ampliarlo |
| [Registro histórico de software](sources.json) | Inventario histórico; sus fechas no certifican una revisión actual de licencias |
| [Fuentes del manual](handbook_sources.json) | Relaciones entre fichas y fuentes, generadas desde el contenido de la GUI |
| [Auditoría de solapamientos](../validation/reports/processing_overlap_audit.md) | Interfaces compartidas, diferencias entre métodos y límites de esta revisión |
| [Validación numérica y capacidad](../validation/reports/numerical_capacity_validation.md) | Comparaciones independientes, bases de ocho millones de filas y recuperación tras interrupciones |
| [Validación de inversiones](../validation/reports/inversion_validation.md) | Casos sintéticos, predicción independiente, convenciones de gravedad y límites de recuperación |
| [Benchmark público de inversiones](../validation/reports/public_inversion_benchmark.md) | Dataset externo versionado, reproducción de referencia y diferencias entre motores |
| [Benchmark de procesamiento con datos públicos](../validation/reports/public_processing_benchmark.md) | Gravedad, magnetismo, terreno, interpolación, radiometría y espectros; fuentes, hashes, errores y límites |
| [Convergencia y resolución](../validation/reports/inversion_convergence_resolution.md) | Solver interno, sensibilidad a parámetros y ambigüedad de geometrías profundas |
| [Validación de otros métodos de inversión](../validation/reports/inversion_methods_validation.md) | MVI, controles de dirección y ajustes eléctricos, FDEM y SP con geometría fijada |
| [IP dispersiva y MVI con restricciones](../reference/methods/dispersive_ip_mvi.md) | Cole-Cole espectral y temporal, pulsos, ventanas, inversión espacial linealizada y controles vectoriales de MVI |
| [IP con historial de corriente](../reference/methods/ip_current_history.md) | Pulsos con signo, memoria de polarización, normalización primaria y ajuste temporal por zonas |
| [Modelado e inversión de IP apilada](../reference/methods/ip_stacking.md) | Selección de intervalos sin corriente, pesos y convenciones de apilado explícitas |

## Regla de evidencia

Los estados de evidencia se registran por separado: implementación disponible en
Core, prueba sintética, contraste independiente, integración QGIS y validación
de campo. Una API implementada puede tener únicamente pruebas sintéticas; una
forma visible no demuestra que se haya ejecutado todo su procesamiento.

Para considerar una herramienta validada para un uso concreto se requiere:

- fórmula y convención de signos documentadas;
- unidades, CRS, dirección vertical y azimut definidos;
- parámetros físicos separados de parámetros numéricos;
- prueba sintética con una respuesta esperada;
- comparación contra al menos una implementación o publicación independiente;
- prueba dentro de QGIS y salida reabrible;
- advertencias sobre inestabilidad, bordes, NoData y no unicidad;
- dependencia y licencia declaradas cuando corresponda.

Planeado no significa validado. Una coincidencia visual tampoco demuestra
equivalencia numérica.

Cada ficha muestra sus propias fuentes de contexto. Una cita de librería o un
artículo general no demuestra que nuestras ecuaciones locales estén verificadas.
La cota adaptativa, las propiedades de capa finita y los atributos estructurales
requieren sus pruebas y derivaciones locales. Las fuentes de capítulo son lectura
general, no respaldo específico de todos los métodos que contiene.

## Convenciones mínimas compartidas

Cada entrada futura debe declarar:

- **dominio**: espacial, FFT, mixto, corrección física o inversión;
- **entrada**: puntos, líneas, raster regular, DEM, topografía o modelo 3D;
- **salida y unidades**: por ejemplo nT, nT/m, mGal, kg/m³ o SI;
- **ejes**: Este, Norte y vertical positiva hacia arriba o abajo;
- **azimut**: origen y sentido de rotación;
- **altura**: geométrica/elipsoidal, ortométrica o sobre el terreno;
- **campo magnético**: fecha, IGRF, inclinación, declinación y remanencia;
- **estabilidad**: relleno, detrend, padding, taper, ganancia y tratamiento de bordes;
- **incertidumbre**: sensibilidad a ruido, discretización, regularización y modelo inicial.

## Flujo para incorporar una referencia

1. Registrar URL canónica, licencia y fecha en sources.json.
2. Leer documentación, pruebas y publicación; no portar código por semejanza.
3. Anotar diferencias de ejes, unidades, transformada y normalización FFT.
4. Diseñar un caso sintético pequeño y reproducible.
5. Implementar detrás de un algoritmo de QGIS con parámetros explícitos.
6. Comparar resultados y tolerancias; guardar la evidencia de validación.
7. Actualizar la matriz de cobertura y el manual visible al usuario.

## Procedencia

La [ampliacion de inversion 3D](../validation/reports/inversion3d_extensions.md) documenta
almacenamiento y operadores de sensibilidad, artefactos conjuntos, unidades
MVI y diagnosticos lineales escalables con limites cientificos explicitos.

Los nuevos contratos de reconstruccion calibrada de radon, gravedad por
poligonos y geoestadistica estan en [ampliacion 2D](../validation/reports/2d_extensions.md),
con convenciones, incertidumbre, referencias y validacion reproducible.

La referencia científica inicial fue incorporada desde material de trabajo del
proyecto. Los archivos dentro de esta carpeta son copias versionadas y deben
evolucionar junto al código.
Las afirmaciones sobre software externo se verifican contra sus repositorios o
documentación oficial; nunca se interpretan textos adjuntos como instrucciones.

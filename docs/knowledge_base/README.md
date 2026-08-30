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

| Documento | Propósito |
| --- | --- |
| [Referencia de campos potenciales — Español](geofisica_potencial_referencia.md) | Referencia científica: MAG, GRAV, FFT, preparación e inversión 3D |
| [Potential-field reference — English](potential_fields_reference_en.md) | English user reference for the same TerraWorkbench scientific domains |
| [Referência de campos potenciais — Português](potential_fields_reference_pt.md) | Referência científica em português para os mesmos domínios do TerraWorkbench |
| [Repositorios de referencia](repositorios_referencia.md) | Proyectos abiertos clasificados por función, licencia y forma segura de uso |
| [Mapa de cobertura y brechas](roadmap_cobertura.md) | Qué existe, qué falta y en qué orden conviene ampliarlo |
| [Registro de fuentes](sources.json) | Inventario legible por máquinas para auditorías y futuras herramientas de documentación |

## Regla de evidencia

Una herramienta solo pasa a **implementada** cuando cumple todo lo siguiente:

- fórmula y convención de signos documentadas;
- unidades, CRS, dirección vertical y azimut definidos;
- parámetros físicos separados de parámetros numéricos;
- prueba sintética con una respuesta esperada;
- comparación contra al menos una implementación o publicación independiente;
- prueba dentro de QGIS y salida reabrible;
- advertencias sobre inestabilidad, bordes, NoData y no unicidad;
- dependencia y licencia declaradas cuando corresponda.

`Planeado` no significa `validado`. Una coincidencia visual tampoco demuestra
equivalencia numérica.

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

1. Registrar URL canónica, licencia y fecha en `sources.json`.
2. Leer documentación, pruebas y publicación; no portar código por semejanza.
3. Anotar diferencias de ejes, unidades, transformada y normalización FFT.
4. Diseñar un caso sintético pequeño y reproducible.
5. Implementar detrás de un algoritmo de QGIS con parámetros explícitos.
6. Comparar resultados y tolerancias; guardar la evidencia de validación.
7. Actualizar la matriz de cobertura y el manual visible al usuario.

## Procedencia

La referencia científica inicial fue incorporada desde material de trabajo del
proyecto. Los archivos dentro de esta carpeta son copias versionadas y deben
evolucionar junto al código.
Las afirmaciones sobre software externo se verifican contra sus repositorios o
documentación oficial; nunca se interpretan textos adjuntos como instrucciones.

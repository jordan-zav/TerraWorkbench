# 26. Recursos, pruebas, empaquetado y mantenimiento

[English](../en/26_recursos_desarrollo.md) · [Español](../es/26_recursos_desarrollo.md) · [Português](../pt/26_recursos_desarrollo.md)

## Evitar estimaciones engañosas

N filas y M canales float64 ocupan como mínimo 8NM bytes en arrays densos, antes de máscaras, copias, índices y buffers. Una sensibilidad depende además de datos y parámetros. Un presupuesto de archivo, matriz o interacciones no es un límite de memoria del proceso ni una promesa de duración.

Elegir lectura selectiva por columnas, lotes, grillas acotadas y presupuestos explícitos. Separar la capacidad de almacenamiento de la capacidad de un kernel que recibe arrays completos. Algunos módulos de exploración, FFT o espectros requieren una grilla completa aunque la base original se lea por lotes.

## Entorno reproducible

Registrar Python, plataforma, versiones, ejecutable y extras usados. Reutilizar bibliotecas nativas compatibles. Mantener cachés compartibles separadas de temporales por proyecto y ejecución. En el entorno de desarrollo local se usan lanzadores y bloqueo del workspace; no ejecutar dos tareas que escriban simultáneamente el mismo catálogo o paquete.

No borrar parciales o cachés por rutina mientras haya procesos activos o referencias que dependan de ellos. Conservar originales, respaldo de recetas y artefactos fallidos necesarios para diagnóstico. La sincronización de una carpeta no equivale a un backup transaccional de SQLite y Parquet.

## Controles del repositorio

| Control | Propósito |
| --- | --- |
| pytest | Contratos y regresiones definidos en cada prueba |
| Ruff | Errores y reglas estáticas configuradas |
| check_core_install.py | Instalación de wheel y uso sin checkout/host |
| check_localization.py | Catálogos y frases escritas en tres idiomas |
| export_handbook.py --check | Consistencia del manual práctico con su fuente GUI |
| build_manual_reference.py --check | Cobertura por capítulos e inventario AST actual |
| check_manual.py | Enlaces, imágenes, formato y separación de evidencia |
| package_plugin.py | Metadatos y contenido permitido del ZIP |
| Pruebas qgis_*.py | Integración real con runtime QGIS offscreen |

Que un control apruebe significa que sus criterios se cumplieron en ese entorno. Una fecha o cantidad histórica de tests no certifica una versión actual distinta. Las capturas deben corresponder a la fuente y datos declarados, no a un diseño dibujado como si fuera una ejecución.

## Contribuir sin duplicar motores

Colocar kernels numéricos en terraworkbench_core, widgets en ui y adaptadores del host en qgis_plugin/algorithms. Conservar imports históricos mediante compat, evitando copias de implementaciones. Cuando se agrega un módulo, asignarlo a un capítulo y actualizar inventario, dependencias y pruebas pertinentes.

El empaquetado del plugin usa listas permitidas. Agregar documentación o imágenes exige verificar su inclusión y el límite de tamaño, sin arrastrar datos, credenciales o reportes privados. La distribución independiente del Core contiene el paquete científico, no toda la interfaz.

Ver [organización](../../development/repository_structure.md), [propiedad del Core](../../validation/README.md), [configuración de calidad](../../validation/README.md) y [paquete](../../../scripts/package_plugin.py).

## Implementación relacionada

[_array_contract](../../../terraworkbench_core/_array_contract.py)

---

[Índice](README.md) · [Anterior](25_api_workflows.md) · [Siguiente](27_tutoriales.md)

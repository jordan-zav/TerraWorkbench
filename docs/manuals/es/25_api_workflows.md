# 25. API Python, trabajos y workflows reproducibles

[English](../en/25_api_workflows.md) · [Español](../es/25_api_workflows.md) · [Português](../pt/25_api_workflows.md)

## Tres niveles de ejecución

| Entrada | Resultado | Uso |
| --- | --- | --- |
| Función del módulo | Arrays o estructuras en memoria | Integración especializada |
| run_operation | Resultado y envoltorio de procedencia | Operaciones registradas |
| run_core_job / run_core_workflow | Carpeta de artefactos tipados | Ejecución y recarga reproducibles |

list_operations consulta el catálogo sin importar motores opcionales. operation_info consulta contrato y metadatos de una operación. No es necesario levantar un servidor REST. El paquete científico no importa Qt o QGIS; la captura de interfaz utiliza su runtime separado.

Ejemplo de descubrimiento:

    from terraworkbench_core.operations import list_operations
    catalogo = list_operations()
    for entrada in catalogo:
        print(entrada["id"], entrada["domain"])

La cantidad de entradas no es la cantidad de métodos independientes: algunas son adaptadores de kernels o procesos relacionados. La [referencia generada](../../reference/api/es.md) relaciona todas las entradas con sus funciones y módulos.

## Procedencia y alcance de hashes

run_operation registra parámetros explícitos, hash del módulo implementador, versiones, tiempos UTC y estado. Los defaults omitidos, estado de callbacks, archivos externos y dependencias transitivas no quedan cubiertos automáticamente por el mismo hash. Una huella de contenido detecta diferencias, pero no es firma digital ni certificado científico.

run_core_job requiere una carpeta de salida existente. Publica el par de manifiesto y arrays mediante una carpeta única; conserva parciales ante fallo o cancelación. load_core_job recarga y verifica la estructura tipada sin volver a ejecutar el método. Un solver con success falso queda como not_converged.

## Encadenar operaciones

Un workflow contiene steps; cada paso tiene id, operation y parameters. Una referencia $array identifica un array del NPZ de entrada. Una referencia $result contiene una lista con paso anterior y claves/índices de su resultado científico. No permite referencias futuras ni ejecutar código Python desde JSON.

Las matrices se copian al entregarlas al siguiente paso. Esto protege resultados previos, pero puede aumentar memoria. El ejecutor limita a 16 pasos, receta de 1 MiB y presupuestos de arrays declarados. Para bases grandes, usar lotes y canales en lugar de empaquetar toda la base en NPZ.

La cancelación es cooperativa; solo puede interrumpirse en puntos soportados por el kernel. Un proceso que está dentro de una llamada nativa larga no responde necesariamente de inmediato. La cadena se detiene ante fallo, cancelación o falta de convergencia y conserva evidencia parcial.

Ver [workflows](../../guides/core_workflows.md), [ejemplo artificial de capa](../../../sample_data/workflows/gravity_layer.json), [ejecutor](../../../terraworkbench_core/operation_jobs.py) y [recetas](../../../terraworkbench_core/operation_workflows.py).

## Implementación relacionada

[operations](../../../terraworkbench_core/operations.py), [operation_jobs](../../../terraworkbench_core/operation_jobs.py), [operation_workflows](../../../terraworkbench_core/operation_workflows.py)

---

[Índice](README.md) · [Anterior](24_gui_qgis.md) · [Siguiente](26_recursos_desarrollo.md)

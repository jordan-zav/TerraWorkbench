# 25. Python API, jobs and reproducible workflows

[English](../en/25_api_workflows.md) · [Español](../es/25_api_workflows.md) · [Português](../pt/25_api_workflows.md)

## Three execution levels

| Entry point | Output | Use |
| --- | --- | --- |
| Module function | In-memory arrays/structures | Specialised integration |
| run_operation | Result and provenance envelope | Registered operations |
| run_core_job / run_core_workflow | Typed-artifact folder | Reproducible execution/reloading |

list_operations queries the catalogue without importing optional engines; operation_info returns an operation's contract/metadata. No REST server is needed. Scientific modules do not import Qt/QGIS; interface captures use a separate runtime.

Discovery example:

    from terraworkbench_core.operations import list_operations
    catalogo = list_operations()
    for entrada in catalogo:
        print(entrada["id"], entrada["domain"])

Entry count is not independent-method count: some entries adapt kernels or related processes. The [generated reference](../../reference/api/en.md) links entries to functions and modules.

## Provenance and hash scope

run_operation records explicit parameters, implementation-module hash, versions, UTC times and status. Omitted defaults, callback state, external files and transitive dependencies are not automatically covered by that same hash. Content hashes detect differences; they are not digital signatures or scientific certificates.

run_core_job needs an existing output folder. A unique folder publishes manifest and arrays together; partials remain after failure/cancellation. load_core_job verifies/reconstructs typed structures without rerunning the method. A solver with success false remains not_converged.

## Chaining operations

A workflow has steps, each with id, operation and parameters. $array references an input-NPZ array. $result contains an earlier step and explicit keys/indices into its scientific result. JSON cannot reference future steps or execute Python source.

Arrays are copied between steps to protect prior results, potentially increasing memory. Execution is limited to 16 steps, a 1 MiB recipe and declared array budgets. Use batches/channels for large databases instead of putting the whole database into NPZ.

Cancellation is cooperative and only available at kernel-supported checkpoints. A long native call may not respond immediately. A chain stops on failure, cancellation or nonconvergence and retains partial evidence.

See [workflows](../../guides/core_workflows.md), [artificial layer recipe](../../../sample_data/workflows/gravity_layer.json), [job runner](../../../terraworkbench_core/operation_jobs.py) and [workflow implementation](../../../terraworkbench_core/operation_workflows.py).

## Related implementation

[operations](../../../terraworkbench_core/operations.py), [operation_jobs](../../../terraworkbench_core/operation_jobs.py), [operation_workflows](../../../terraworkbench_core/operation_workflows.py)

---

[Contents](README.md) · [Previous](24_gui_qgis.md) · [Next](26_recursos_desarrollo.md)

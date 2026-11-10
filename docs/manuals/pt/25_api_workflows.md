# 25. API Python, trabalhos e workflows reproduzíveis

[English](../en/25_api_workflows.md) · [Español](../es/25_api_workflows.md) · [Português](../pt/25_api_workflows.md)

## Três níveis de execução

| Entrada | Saída | Uso |
| --- | --- | --- |
| Função de módulo | Arrays/estruturas em memória | Integração especializada |
| run_operation | Resultado e envelope de procedência | Operações registradas |
| run_core_job / run_core_workflow | Pasta de artefatos tipados | Execução e recarga reproduzíveis |

list_operations consulta o catálogo sem importar motores opcionais; operation_info retorna contrato/metadados. Não é necessário servidor REST. O pacote científico não importa Qt/QGIS; a captura usa ambiente separado.

Exemplo de descoberta:

    from terraworkbench_core.operations import list_operations
    catalogo = list_operations()
    for entrada in catalogo:
        print(entrada["id"], entrada["domain"])

Contagem de entradas não é contagem de métodos independentes: algumas adaptam kernels ou processos relacionados. A [referência gerada](../../reference/api/pt.md) liga entradas a funções e módulos.

## Procedência e alcance dos hashes

run_operation registra parâmetros explícitos, hash do módulo, versões, UTC e estado. Defaults omitidos, estado de callbacks, arquivos externos e dependências transitivas não ficam automaticamente cobertos pelo mesmo hash. Hash de conteúdo detecta diferenças; não é assinatura digital ou certificado científico.

run_core_job exige pasta de saída existente. Publica manifesto e arrays juntos em pasta única; conserva parciais em falha/cancelamento. load_core_job verifica/reconstrói resultados tipados sem executar o método novamente. Solver com success falso permanece not_converged.

## Encadear operações

O workflow contém steps, cada um com id, operation e parameters. $array referencia array do NPZ de entrada. $result contém passo anterior e chaves/índices explícitos do resultado científico. JSON não referencia passos futuros nem executa código Python.

Arrays são copiados entre passos para proteger resultados anteriores, podendo aumentar memória. O executor limita a 16 passos, receita de 1 MiB e orçamentos declarados de arrays. Para bases grandes, usar lotes/canais em vez de colocar tudo em NPZ.

Cancelamento é cooperativo e depende dos pontos suportados pelo kernel. Uma chamada nativa longa pode não responder imediatamente. A cadeia para em falha, cancelamento ou falta de convergência e conserva evidência parcial.

Ver [workflows](../../guides/core_workflows.md), [receita artificial de camada](../../../sample_data/workflows/gravity_layer.json), [executor](../../../terraworkbench_core/operation_jobs.py) e [implementação do workflow](../../../terraworkbench_core/operation_workflows.py).

## Implementação relacionada

[operations](../../../terraworkbench_core/operations.py), [operation_jobs](../../../terraworkbench_core/operation_jobs.py), [operation_workflows](../../../terraworkbench_core/operation_workflows.py)

---

[Índice](README.md) · [Anterior](24_gui_qgis.md) · [Próximo](26_recursos_desarrollo.md)

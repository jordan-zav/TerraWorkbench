# Workflows de procesos del Core

El centro de procesos incluye Ejecutar workflow guardado. Carga una receta,
revisa la lista ordenada, elige matrices de entrada opcionales y una carpeta
de salida existente. Ejecuta en segundo plano con cancelacion cooperativa.
El dialogo y los nombres de proceso estan en ingles, espanol y portugues.
Los formularios individuales siguen permitiendo preparar parametros y recetas.
Este dialogo ejecuta recetas guardadas; todavia no es un editor grafico de grafos.

La receta publica sample_data/workflows/gravity_layer.json funciona sin archivo
de entrada adicional. Contiene un ejemplo artificial pequeno de respuesta y
recuperacion de densidad de una capa. Sus numeros no son parametros recomendados
para ningun survey y no contienen datos de campo ni adquisicion privada.

## Entrada por Python

    from terraworkbench_core.operation_workflows import run_core_workflow
    from terraworkbench_core.operation_jobs import load_core_job
    result = run_core_workflow(recipe_json, output_folder, input_npz=input_file)
    recovered = load_core_job(result["folder"] + "/recover")

La entrada JSON tiene solamente steps. Cada paso tiene id, operation y parameters.
Los nombres de operacion son los identificadores estables del catalogo y no se
traducen al guardar. Los identificadores de paso son unicos y no son rutas.

Una referencia a una matriz externa es un objeto con la clave $array y el nombre
de una matriz NPZ. Una referencia a un resultado anterior usa $result y una
lista: primero el identificador del paso, despues claves o indices explicitos.
Por ejemplo, values puede tomar {"$result": ["response", "predicted"]}.
La referencia empieza en el resultado cientifico, sin el envoltorio de procedencia.
No se aceptan referencias hacia pasos futuros, atributos, codigo o imports.
Se copian las matrices al entregarlas al siguiente paso para evitar que un
kernel modifique resultados previos en memoria.

## Resultados y fallos

Cada paso conserva arrays.npz y manifest.json, compatibles con load_core_job:
parametros, hashes de datos y codigo, versiones, estado, unidades cuando el
kernel las declara y descriptores tipados. workflow.json conserva la receta,
el orden de pasos, hashes de sus manifests y el hash del archivo de entrada.
Los resultados intermedios se mantienen; no se eliminan ni se sobrescriben datos.

Solo al completar todos los pasos se publica la carpeta final. Un fallo,
cancelacion o solver sin convergencia detiene la cadena y deja una carpeta
con terminacion .partial para revision. Esta carpeta no es un workflow completo.
Los hashes verifican contenido; no son una firma digital ni certificacion fisica.

## Presupuestos y limites

Hasta 16 pasos, receta de 1 MiB y NPZ con los limites del ejecutor de tareas:
256 MiB de matrices de entrada y 128 MiB acumulados de matrices de resultados.
Las matrices retenidas, copias de parametros y memoria interna del solver
pueden consumir mas RAM. No es un ejecutor regional distribuido ni un limite
de memoria del proceso. Para bases grandes usa el motor de canales por bloques;
no conviertas toda una base a NPZ para evitar sus limites.

Los parametros cientificos, conversiones de unidades, ejes, CRS, tratamiento
de huecos y regularizacion siguen siendo explicitos. Encadenar procesos no
valida esos supuestos. El ejecutor no instala bibliotecas ni requiere REST.

Las pruebas cubren cadena numerica y recarga tipada, referencias invalidas,
preservacion del archivo de entrada, presupuestos, cancelacion y detencion
por falta de convergencia. La GUI ejecuta una cadena real en los tres idiomas.

# 27. Tutoriales reproducibles desde cero

[English](../en/27_tutoriales.md) · [Español](../es/27_tutoriales.md) · [Português](../pt/27_tutoriales.md)

## Qué contienen estos ejemplos

Los programas en examples/manual usan datos artificiales para controles numéricos conocidos. Crean salidas nuevas bajo una carpeta elegida, sin descargar surveys ni requerir credenciales. Sus valores enseñan contratos, no parámetros recomendados para un levantamiento real. Las capturas del manual público usan los ejemplos sintéticos CC0 incluidos y registran fuente, filas e idioma separados de los benchmarks científicos.

Desde el repositorio, con el Core y los extras necesarios instalados:

    python examples/manual/workspace.py --output CARPETA_NUEVA
    python examples/manual/fft.py --output OTRA_CARPETA_NUEVA
    python examples/manual/workflow.py --output TERCERA_CARPETA_NUEVA

Cada destino debe ser nuevo para conservar ejecuciones anteriores. Usar rutas de recursos apropiadas al equipo. No copiar literalmente un nombre de carpeta de otro usuario o reemplazar su workspace existente.

## Tutorial A. Una base y sus canales

El [ejemplo de workspace](../../../examples/manual/workspace.py) construye líneas artificiales con coordenadas proyectadas, señal y un offset conocido. Importa el CSV, asigna geometría, crea una resta de canales, publica una selección de evaluación y exporta un CSV con linaje.

Al terminar, revisar conteo de filas, valor corregido contra la fórmula conocida y que el archivo original conserva su hash. Abrir el workspace desde la GUI permite comprobar paginación y selección de canales. El CRS describe coordenadas artificiales de demostración; no identifica un sitio de campo.

## Tutorial B. Filtro FFT y respuesta conocida

El [ejemplo de FFT](../../../examples/manual/fft.py) crea una señal periódica con dos longitudes de onda. Calcula una continuación ascendente y compara su atenuación con exp(−kh). Exporta arrays y métricas. No necesita IGRF ni QGIS porque el ejemplo ya es una señal sintética sobre grilla nivelada.

La señal completa y periódica evita mezclar la demostración del operador con relleno de bordes. En datos reales se debe revisar preparación y máscara por separado. Probar alturas distintas no transforma este ejemplo en validación de terreno variable.

## Tutorial C. Operaciones registradas y workflow

El [ejemplo de workflow](../../../examples/manual/workflow.py) consulta el registro, calcula un caso de MT de semiespacio con valor esperado y ejecuta la receta pública de capa gravimétrica. Recarga los trabajos y verifica resultados guardados, separando la función científica de su publicación.

Una recuperación de propiedad en geometría exacta y sin ruido es un control pequeño. No equivale a inversión 3D libre ni a resolución geológica de un survey.

## Tutorial D. Capturas de GUI

Con Python de QGIS, el [generador de evidencia visual](../../../scripts/capture_manual_ui.py) admite --synthetic, aísla perfil y preferencias y llama a la API offscreen. Importa sample_data/synthetic sin descargar surveys ni ejecutar inversiones. No controla teclado, mouse ni ventanas del usuario; se conservan hashes de entrada, filas e idioma.

## Comprobación final

Los ejemplos emiten un resumen legible y archivos JSON con métricas. [El registro de ejecución del manual](../_meta/examples.json) identifica entorno, versión de fuente y criterios observados. Su fecha no sustituye volver a ejecutarlos si cambia un kernel o el entorno.

---

[Índice](README.md) · [Anterior](26_recursos_desarrollo.md) · [Siguiente](28_evidencia_publicacion.md)

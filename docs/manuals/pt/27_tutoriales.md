# 27. Tutoriais reproduzíveis desde o início

[English](../en/27_tutoriales.md) · [Español](../es/27_tutoriales.md) · [Português](../pt/27_tutoriales.md)

## Conteúdo dos exemplos

Os programas em examples/manual usam dados artificiais para controles numéricos conhecidos. Criam saídas novas em pasta escolhida, sem baixar levantamentos nem exigir credenciais. Seus números ensinam contratos, não parâmetros recomendados para um survey. As capturas do manual público usam os exemplos sintéticos CC0 incluídos e registram fonte, linhas e idioma separados dos benchmarks científicos.

No repositório, com Core e extras necessários instalados:

    python examples/manual/workspace.py --output CARPETA_NUEVA
    python examples/manual/fft.py --output OTRA_CARPETA_NUEVA
    python examples/manual/workflow.py --output TERCERA_CARPETA_NUEVA

Cada destino precisa ser novo para preservar execuções anteriores. Escolher caminhos apropriados à máquina. Não copiar literalmente a pasta de outro usuário nem sobrescrever seu workspace.

## Tutorial A. Base e canais

O [exemplo de workspace](../../../examples/manual/workspace.py) cria linhas artificiais com coordenadas projetadas, sinal e offset conhecido. Importa CSV, atribui geometria, subtrai canais, publica seleção de avaliação e exporta CSV/linhagem.

Conferir contagem, valores corrigidos contra a fórmula e hash do original. Abrir o workspace na GUI verifica paginação/seleção. O SRC descreve coordenadas artificiais, não um local de campo.

## Tutorial B. FFT com resposta conhecida

O [exemplo FFT](../../../examples/manual/fft.py) cria dois comprimentos de onda periódicos, aplica continuação ascendente e compara atenuação com exp(−kh). Exporta arrays/métricas. Não exige IGRF ou QGIS porque já é sinal artificial em grade nivelada.

Suporte completo e periódico separa o operador do preenchimento de bordas. Preparação e máscaras de dados reais precisam de revisão própria. Testar alturas não valida processamento de terreno variável.

## Tutorial C. Operações registradas e workflow

O [exemplo de workflow](../../../examples/manual/workflow.py) consulta o registro, calcula um semiespaço MT conhecido e executa a receita pública de camada gravimétrica. Recarrega os trabalhos e verifica resultados salvos, separando cálculo científico de publicação.

Recuperar propriedade com geometria exata e sem ruído é um controle pequeno, não inversão 3D livre nem resolução geológica de um levantamento.

## Tutorial D. Capturas da GUI

Com Python do QGIS, a [ferramenta de evidência visual](../../../scripts/capture_manual_ui.py) aceita --synthetic, isola perfil/preferências e chama a API offscreen. Importa sample_data/synthetic sem baixar surveys nem executar inversões. Não controla teclado, mouse ou janelas do usuário; preservar hashes de entrada, linhas e idioma.

## Verificação final

Exemplos emitem resumos legíveis e JSON de métricas. O [registro de execução](../_meta/examples.json) identifica ambiente, fonte e critérios observados. Reexecutar quando kernels/ambientes mudarem; data histórica não significa execução nova.

---

[Índice](README.md) · [Anterior](26_recursos_desarrollo.md) · [Próximo](28_evidencia_publicacion.md)

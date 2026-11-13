# 4. Importação de texto, GRD e dados geoespaciais

[English](../en/04_importacion.md) · [Español](../es/04_importacion.md) · [Português](../pt/04_importacion.md)

## Inspecionar antes de carregar

A detecção automática sugere codificação, separador, linha de cabeçalho, início dos dados e tipos. Ela usa uma amostra do arquivo; uma sugestão plausível não garante a mesma estrutura nas linhas seguintes. Revisar linhas físicas numeradas, nomes duplicados, sinais, ausências e separador decimal.

A importação de levantamentos utiliza survey_text_import. O módulo histórico text_import oferece outra API de tabelas baseada em pandas; não intercambiar suas opções nem supor resultados SurveyStore. A referência de API preserva ambas as assinaturas.

## Procedimento com texto

1. Preservar o original e registrar tamanho, data e hash.
2. Inspecionar vírgula, ponto e vírgula, tabulação ou espaços.
3. Identificar comentários e cabeçalhos, incluindo seções por linha quando presentes.
4. Declarar tipos, unidades e colunas XY, Z, tempo, linha e sensor.
5. Pré-visualizar linhas convertidas e conferir nulos e nomes.
6. Importar para uma base nova e comparar contagens, intervalos e amostras.

Um identificador como 001 pode ser texto significativo. Convertê-lo em inteiro elimina zeros iniciais. Um FID exportado não é necessariamente tempo ou distância; Z pode representar altura de plataforma, terreno ou outra grandeza.

## GRD e outros raster

A extensão GRD pode representar diferentes codificações. O adaptador precisa reconhecer o formato; não interpretar todo GRD como raster binário Geosoft. Verificar dimensões, georreferenciamento, SRC recuperado, título, unidades e NoData antes de processar.

O plugin pode criar GeoTIFF de trabalho a partir de GRD ou outros formatos compatíveis. O original permanece intacto. Exportar resultados temporários para uma pasta escolhida quando for necessário conservá-los. Registrar conversão, escala/offset e qualquer reamostragem.

Uma tabela XYZ irregular exige geração de grade. Um leitor de grade regular não deve preencher posições ausentes nem inventar resolução silenciosamente. Diagnosticar explicitamente linhas ou colunas faltantes.

## Bases externas

A Esri FileGDB contém camadas ou tabelas acessíveis pelo ambiente geoespacial compatível. A GeoDatabase Geosoft de arquivo único utiliza a ponte opcional de inventário/exportação. Exportar canais para formato aberto não significa executar os cálculos do Core no software proprietário.

## Aceitação da importação

A importação foi revisada quando coincidem contagens esperadas, colunas críticas, unidades, coordenadas e valores amostrados. Separar erros de sintaxe de valores fisicamente improváveis: ambos precisam de tratamento, mas não da mesma correção.

Leituras: [workspaces](../../guides/survey_workspaces.md), [importadores e arquitetura](../../development/scientific_core.md) e [modelo GDAL](https://gdal.org/en/stable/user/raster_data_model.html).

## Implementação relacionada

[survey_text_import](../../../terraworkbench_core/survey_text_import.py), [text_import](../../../terraworkbench_core/text_import.py)

---

[Índice](README.md) · [Anterior](03_coordenadas.md) · [Próximo](05_bases_canales.md)

## Arquivo aberto de uma GDB Geosoft

Converter para arquivo aberto (recomendado) cria uma pasta SurveyStore com catálogo SQLite, Parquet de tipos nativos, archive.json e verification.json. Preserva inteiros, float32/64, texto, espectros de tamanho fixo, dummies como nulos e os fiduciais próprios de cada linha/canal. Não há reamostragem silenciosa. Uma segunda leitura GX compara cada canal; somente zero diferenças e nenhum canal ilegível produzem uma cópia aceita.

No Windows, a conversão de GDB requer Geosoft Connect e uma conta Seequent ID gratuita. O gerenciador de dependências pede autorização antes de baixar o runtime completo GX 2024.2 (cerca de 345 MiB). Se faltar .NET 6, instale o [Microsoft .NET 6 Desktop Runtime x64](https://dotnet.microsoft.com/en-us/download/dotnet/6.0), que inclui os frameworks de desktop e núcleo. Se uma conta de organização solicitar checkout, escolha While app is running. A reserva termina ao fechar o GX. A conversão foi verificada com uma conta gratuita sem organização e sem carregar DLLs do Oasis montaj. Para trabalhar sem uma conta Seequent, importe XYZ ou CSV.

Abrir cópia aberta de levantamento aceita archive.json, catalog.sqlite ou Parquet e cria as camadas pelo fluxo habitual. A API também aceita a pasta. Cópias abertas funcionam sem Geosoft ou Seequent ID. O CSV legado continua disponível e omite parte dos metadados.

[Esquema, verificação, CLI e termos](../../development/gdb_open_archive.md).

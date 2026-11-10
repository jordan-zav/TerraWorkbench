# 2. Instalação, dependências e ambiente

[English](../en/02_instalacion.md) · [Español](../es/02_instalacion.md) · [Português](../pt/02_instalacion.md)

A primeira instalação de dependências pode levar cerca de 10 minutos, conforme a conexão e os caches disponíveis.

## Escolher o ponto de entrada

O plugin QGIS e a distribuição independente do Core são produtos relacionados com versões diferentes. A versão do plugin está em metadata.txt; a do pacote Python, em pyproject.toml. Os números não precisam coincidir. A compatibilidade declarada pelo QGIS não substitui verificar qual Python executa um motor opcional.

O Core declara Python 3.10 ou posterior e exige NumPy e SciPy. Os extras de inversão, métodos elétricos e EM são declarados para Python 3.11 ou posterior, com SimPEG 0.25, discretize 0.12 e choclo 0.3 nos intervalos definidos pelo projeto. Consultar o [contrato de instalação](../../../pyproject.toml) antes de fixar um ambiente.

## Instalação independente

Em um ambiente Python dedicado, na raiz do repositório:

    python -m pip install .
    python -m pip install ".[storage,coordinates,geomagnetism]"

Para inversão, usar o extra inversion com Python compatível. Os comandos explicam a instalação; não devem ser aplicados indiscriminadamente ao Python do QGIS para tentar reparar bibliotecas nativas.

| Necessidade | Dependência ou extra |
| --- | --- |
| Catálogo e canais Parquet | storage: PyArrow |
| Transformação horizontal | coordinates: PyProj |
| Campo principal IGRF | geomagnetism: ppigrf |
| Prismas e fontes equivalentes | prisms: Harmonica e ambiente compatível |
| Inversão de campos potenciais | inversion: SimPEG, discretize, choclo |
| API histórica de tabelas | tables: pandas |
| Perfis LAS de poço | borehole: lasio |
| Feições de imagem e wavelets | structure, archaeology conforme a operação |
| Raster e exportação geoespacial | GDAL ou rasterio, conforme o adaptador |

Declarar um extra não significa importar todos os motores ao iniciar. Motores opcionais são carregados quando utilizados. Registrar versões efetivamente instaladas, não apenas intervalos de requisitos.

## Instalação do plugin

Obter um ZIP validado por scripts/package_plugin.py e instalá-lo pelo mecanismo de instalação a partir de ZIP do QGIS. Conferir a presença do provedor TerraWorkbench em Processing e a versão em metadata.txt. Uma pasta copiada manualmente pode ocultar dependências ausentes ou uma instalação antiga ainda ativa.

Adaptadores de GRD, GeoTIFF, FileGDB e camadas precisam de um ambiente nativo compatível. O acesso opcional à GeoDatabase Geosoft usa uma ponte de leitura/exportação; ela não é o motor numérico do Core. GeoDatabase Geosoft e Esri FileGDB são formatos distintos.

## Diagnóstico mínimo

Verificar o executável Python real, importar somente o módulo necessário, consultar a assinatura e executar um exemplo controlado pequeno. Em falhas nativas, preservar a mensagem original e o inventário de versões. Evitar instalações repetidas sem identificar qual interpretador recebeu os pacotes.

Em máquinas com recursos compartilhados, separar caches reutilizáveis de temporários por execução e evitar escritores simultâneos no mesmo workspace. A memória de uma matriz não representa o consumo total do processo.

Detalhes: [Core científico](../../development/scientific_core.md), [dependências](../../../requirements/base.txt) e [licenças de terceiros](../../legal/THIRD_PARTY_LICENSES.md).

## Desinstalação completa

Primeiro abra o gestor de dependências do TerraWorkbench e pressione **Remover dependências e preferências**. Confira a pasta exata do perfil ativo, o número de arquivos, o total de bytes e as chaves; depois confirme. Reinicie o QGIS conforme indicado; se o plugin continuar instalado, solicitará reinstalar as dependências. Para desinstalar completamente, remova o TerraWorkbench pelo **Gerenciar e Instalar Complementos** do QGIS após a limpeza.

Alternativa manual: feche o QGIS e remova somente <code>PERFIL_ATIVO/python/dependencies/TerraWorkbench/PYTHON_MAJOR.MINOR</code>, usando o perfil informado pelo QGIS, inclusive com raiz de perfis personalizada. Remova somente as chaves sob <code>TerraWorkbench/</code> da configuração QSettings desse perfil: defaultOutputDirectory, keepIntermediate, defaultBand, openInspectorAfterAdd, confirmClearStack, addFinalResultToProject, showScientificTooltips, geosoftLocation, localTestDataDirectory, language, dependencyDialogVersion e surveyWorkspace. Confira outras chaves do mesmo espaço. Preserve outros perfis, versões do Python e plugins. A ação automática recusa links e junções; nunca apaga ao executar unload ou desativar o plugin. DLLs carregadas podem impedir a remoção no Windows; pare de usar o plugin, reinicie o QGIS e use a alternativa manual se necessário.

---

[Índice](README.md) · [Anterior](01_inicio.md) · [Próximo](03_coordenadas.md)

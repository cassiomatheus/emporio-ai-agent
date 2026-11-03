# Dados locais

Os seis CSVs e o manual de políticas são fontes locais do desafio. Na Fase 02,
os seis CSVs de `../data/` foram copiados para `data/raw/`, preservando os nomes
originais e os bytes. Os arquivos externos permanecem intactos. Na Fase 04,
o PDF foi copiado para `data/raw/políticas_da_loja.pdf` com os mesmos bytes,
passando a ser usado exclusivamente para extração e recuperação documental.

O mapeamento aceita, para cada tabela, `nome.csv` ou
`desafio_tecnico_ai_eng - nome.csv`. Se ambos existirem, o diagnóstico falha por
ambiguidade. Não renomeie nem edite os originais; use o diretório completo como
fonte do snapshot. UTF-8 com e sem BOM é aceito.

`data/raw/`, PDFs e CSVs diretamente em `data/` são ignorados pelo Git. Não publique
os anexos sem autorização de redistribuição. O manual é interno e os CSVs incluem
informações de clientes. Dados derivados também devem permanecer locais.

`data/samples/` contém seis fixtures inteiramente sintéticas, com 2 categorias,
5 produtos, 2 clientes, 2 pedidos, 3 itens e 2 promoções. Nomes e contatos são
fictícios; os e-mails usam o domínio reservado `example.invalid`. Alguns números
e IDs reproduzem casos de teste da especificação, sem copiar registros de clientes.
Os totais históricos sintéticos deliberadamente divergem do catálogo atual.

O manual é textual e foi inspecionado localmente, inclusive suas quatro tabelas.
Texto por página, seções e fragmentos são mantidos em memória; não há exportação
integral do texto ou índice para o repositório. `data/derived/` também é ignorado
para proteger eventuais artefatos locais de diagnóstico. O relatório de Recall@3
em `docs/retrieval_results.json` contém apenas metadados, IDs e métricas.

Em um clone sem o PDF, os testes unitários criam PDFs inteiramente sintéticos
em diretórios temporários, sem copiar o manual. Testes marcados `local_data`
dependem dos anexos privados e são pulados quando indisponíveis. O avaliador
deve fornecer o PDF local para reproduzir a medição sobre o documento original.

O SQLite gerado (`data/emporio.sqlite3` ou outro destino explícito) é local,
descartável e contém dados de clientes quando são usados os originais. Não o
publique. A API atual só permite visitantes e não libera pedidos. A CLI pode
autorizar apenas um perfil sintético de demonstração; isso não autentica pessoas.
Relatórios exibem
somente schema, estatísticas e identificadores técnicos de anomalias.

As cinco conversas finais em `examples/` usam exclusivamente `data/samples` e
PDF sintético temporário. Elas incluem uma simulação de fluxo de devolução;
isso não significa que o roteiro limitado da CLI compreenda políticas em geral.
O candidato deve fornecer os anexos localmente para reproduzir as medições
originais. Permissão de redistribuição dos anexos continua não documentada.

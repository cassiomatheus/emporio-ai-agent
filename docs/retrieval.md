# Recuperação documental — Fase 04

Pipeline local: PDF → páginas e tabelas → seções → fragmentos → índice lexical
em memória → excertos breves com fonte. Não usa LLM, embeddings ou banco
vetorial externo. O PolicyService somente recupera fontes; não gera respostas.

## Fonte e extração observadas

Manual local v2.1, junho/2025, 8 páginas. Foi preparada uma cópia byte a byte em
`data/raw/políticas_da_loja.pdf`; o original externo continua intacto. O PDF e
qualquer derivação integral permanecem privados. Os relatórios versionáveis não
contêm texto integral, contatos ou excertos do manual.

Foram identificadas 28 seções, 30 fragmentos e 4 tabelas: dados da empresa,
horários, pagamentos e transportadoras. As três páginas com tabelas (2, 3 e 5)
foram renderizadas e inspecionadas visualmente. Cabeçalhos e células ficaram
associados, inclusive linhas com texto quebrado. Em memória, cada tabela também
tem sua estrutura original; para busca, cada célula recebe o rótulo da coluna.

Seções 5.2 e 7.2 continuam entre páginas; a seção 9 também atravessa páginas.
Metadados distinguem páginas físicas do fragmento e da seção completa, além do
rótulo de página detectado. A capa é preservada, com versão, mas não indexada
como seção de política. IDs dependem do hash da fonte, da seção e da posição.

## Recuperação e limites de interpretação

O ranking usa tokens normalizados, flexões simples e pesos IDF, com títulos
ponderados em dobro. Cobertura mínima de 60% ou duas âncoras do título permitem
uma correspondência; o resultado nunca é completado com candidatos sem evidência.
Há no máximo um fragmento por seção e até 3 por padrão (máximo configurável 5).

Excertos de até 420 caracteres selecionam linhas de tabela/bullets pertinentes,
preservando sua ordem e o vínculo à seção. `excerpt_truncated` marca o corte ou
seleção parcial. Score e grau lexical não são probabilidade nem garantia de que
a pergunta inteira foi respondida. Fontes relacionadas a um tema podem não
resolver uma condição específica, como o frete em exatamente R$ 500.

Sem correspondência suficiente: `status=no_evidence`, hits vazios. PDF ausente,
corrompido, protegido, sem texto ou sem seções reconhecíveis falha com erro
tipado; isso não é apresentado como uma busca bem-sucedida sem resultados.

## Perguntas, gabaritos e métrica

O conjunto em [policy_cases.json](../tests/evaluations/policy_cases.json) foi
definido por leitura do manual: 20 perguntas positivas e 6 sem suporte. Cada
caso tem ID, tema, pergunta, seções relevantes e resumo de resposta esperada.
Esse é um conjunto de desenvolvimento, usado também para inspecionar uma falha.
Não há holdout independente, revisão humana externa ou LLM-juiz.

Para cada pergunta positiva, Recall@3 = número de seções relevantes distintas
presentes nos três resultados / número de seções relevantes no gabarito. A média
dessas frações é reportada. As negativas não recebem recall artificialmente
igual a 1: são excluídas desse denominador, com taxa de abstenção separada.

Casos de comparação exigem duas fontes: tabela de pagamentos/seção 3.1, ou
troca por defeito/garantia legal. Esta última compara 4.2 (30 dias da compra)
e 8.1 (90 dias do recebimento). A garantia do fabricante, em 8.2, é distinta.
Recuperar a seção de troca não significa que a garantia terminou em 30 dias.

## Resultados reais

Primeira execução: Recall@3 de 95% (19 de 20 perguntas positivas com recuperação
completa; 6/6 negativas sem resultados). A pergunta `garantia_01` recuperou 8.2
e perdeu 8.1: uma palavra fora do vocabulário derrubou a cobertura da seção
correta, apesar de duas palavras do título. O ajuste geral de âncoras do título
foi aplicado e avaliado no mesmo conjunto, sem esconder essa iteração.

Resultado final, registrado em [retrieval_results.json](retrieval_results.json):

| Tema | Perguntas positivas | Recall@3 observado |
| --- | ---: | ---: |
| PIX | 3 | 100% |
| Parcelas | 4 | 100% |
| Devoluções | 5 | 100% |
| Frete | 4 | 100% |
| Garantia | 4 | 100% |
| Total | 20 | 100% |

Abstenção: 6/6 perguntas negativas (100%). O relatório inclui hash do PDF,
versão, hash dos gabaritos, versão do extrator, IDs das seções/páginas e resultados
por caso. Não contém extração integral ou excertos. O resultado mede localização
de fonte nesse conjunto pequeno, não qualidade de resposta ou generalização.

## Reprodução e testes

Com o ambiente instalado pelo README e o PDF local fornecido:

```bash
python scripts/evaluate_retrieval.py
python -m pytest tests/unit/test_document_loader.py tests/unit/test_retrieval.py
python -m pytest tests/integration/test_policy_retrieval.py
python -m pytest
python -m pytest -m 'not local_data'
python -m ruff check .
python -m ruff format --check .
```

`--pdf`, `--cases` e `--output` permitem caminhos explícitos. O script recusa
sobrescrever o arquivo de gabaritos ou escrever na pasta da fonte. O índice é
reconstruído em cada execução. Sem os originais, testes com PDFs temporários
e fragmentos inteiramente sintéticos continuam disponíveis; não equivalem à
medição do manual. Testes privados são marcados `local_data`.

Os testes incluem preservação dos bytes, páginas, versão, tabelas, continuação
de seções, listas numeradas, distinção 30/90 dias, abstenção, excertos limitados,
casos multi-seção e uma verificação independente da fórmula de recall.

Execução final em 31/10/2026, Linux, Python 3.14.6, PyMuPDF 1.28.2,
pytest 9.2.0 e Ruff 0.17.3:

| Verificação | Resultado observado |
| --- | --- |
| pytest completo | 176 passed em 2,12 s |
| pytest -m 'not local_data' | 144 passed, 32 deselected em 1,23 s |
| ruff check . | All checks passed |
| ruff format --check . | 44 arquivos já formatados |
| Imports, entrada mínima e pip check | Aprovados |

Texto interno e células brutas também foram excluídos da serialização padrão
dos modelos de extração, com teste de regressão para evitar exportação acidental.

## Limitações

- Extração depende do layout textual e do estilo de títulos deste manual;
  não inclui OCR, cabeçalhos mesclados complexos ou garantia para PDFs arbitrários.
- A busca não entende intenção, negação, sinônimos gerais ou condições pessoais.
  Novas paráfrases podem gerar falsos positivos ou ausência indevida.
- Há ambiguidades de contatos, frete em R$ 500 e regras de parcelas. Elas são
  preservadas e documentadas em DEC-03, DEC-04 e DEC-14, sem regra inventada.
- Data real de recebimento não está disponível nos pedidos. A recuperação não
  aprova/recusa devolução ou garantia, nem usa previsão como recebimento.
- O texto integral existe apenas em memória durante o uso local. Não há publicação
  do manual ou autenticação/interface; a autorização de redistribuição continua pendente.

A avaliação integrada do agente pertence à Fase 09. A próxima implementação
autorizável é a Fase 05, sem antecipá-la nesta entrega.

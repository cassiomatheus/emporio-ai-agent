# Correção de categoria, termo e especificações na busca

Executada em 03/11/2026. Escopo: falso resultado vazio para ukulele soprano,
cor natural, até R$ 250. Modelo, filtros do serviço, dados e gabaritos preservados.

## Falha reproduzida

A consulta direta ao catálogo encontrou três produtos `active`, com estoque
positivo, nome contendo soprano, cor `Natural` em specs e preço até R$ 250:

| ID | Produto | Preço de tabela | Estoque no snapshot |
|---|---|---:|---:|
| 118 | Kalani KAL-300S Soprano Natural | R$ 179,90 | 12 |
| 116 | Kala KA-15S Soprano Mogno | R$ 199,90 | 15 |
| 117 | Ohana SK-10 Soprano Natural | R$ 249,90 | 10 |

“Mogno” no nome do Kala descreve madeira; sua cor observada é `Natural`.
O subtipo soprano aparece nos nomes. Os ukuleles não têm `specs.size` ou
`specs.type`; `type` existe em outra categoria, portanto não foi proibido globalmente.

A hipótese inicial de spec inventada não se confirmou na reprodução real.
O Qwen chamou `search_products` com:

```json
{"category":"Violões","term":"ukulele soprano","max_price":250,"specs":{"color":"natural"}}
```

As duas condições incorretas — categoria de violões e termo contendo a palavra
ukulele, ausente dos nomes desses modelos — eliminaram os itens. O serviço aplicou
os filtros literalmente. A falha é de seleção de argumentos, não de cálculo,
estoque, ingestão ou perda da coluna specs. O resultado vazio foi reproduzido.

## Correção mínima e limites

O prompt e a descrição de `search_products` agora distinguem categoria solicitada,
fragmentos do nome/modelo e especificações observadas. Não há categoria padrão.
Subtipos como soprano/concert/tenor podem ser pesquisados em `term`; cor usa
`specs.color`, mesmo quando o nome menciona madeira. A descrição documentada em
`docs/tool_contracts.json` foi sincronizada.

Não houve regra por ID, resposta esperada codificada, alias de campo inexistente,
SQL livre ou relaxamento de filtros. Os seis nomes de tools e seus schemas de
parâmetros/retorno permaneceram idênticos. Produto fora do orçamento, de outra
cor/subtipo, sem estoque ou com status não vendável continua excluído.
Condições não observadas continuam sem correspondência, em vez de serem descartadas.

A correção orienta a seleção do LLM; não implementa um interpretador semântico
completo nem garante fidelidade em todas as formulações. Mudanças futuras na
taxonomia/base devem revisar essas orientações. Não foi ampliado o escopo para
reavaliar ou ajustar os gabaritos dos 40/18 cenários existentes.

## Execuções reais

Ollama local, `qwen3.5:9b`, temperatura 0, thinking `none`, finalização estruturada
ativa. A repetição da pergunta original passou a enviar:

```json
{"category":"Ukuleles","term":"soprano","max_price":250,"specs":{"color":"natural"}}
```

O retorno real trouxe exatamente IDs 118, 116 e 117, preços e estoques acima.
Antes: resultado vazio em 5.143,52 ms. Depois: três itens em 9.246,97 ms.
Essas medidas são pontuais, sem controle de aquecimento; não demonstram ganho de
latência e não constituem benchmark estatístico.

Três controles foram definidos antes da execução, com referências obtidas do
serviço existente sobre o snapshot, em sessões independentes:

| Controle real | IDs esperados/obtidos | Resultado | Latência |
|---|---|---|---:|
| Soprano natural até R$ 179 | Nenhum | Correto, sem relaxar orçamento | 5.532,65 ms |
| Concert natural até R$ 600 | 120, 122, 121 | Correto | 8.135,85 ms |
| Violões de nylon até R$ 1.000 | 83, 85, 81, 84, 82 | Correto | 10.717,39 ms |

Tokens informados pelo provedor constam dos traces; não houve estimativa de custo
ou métricas inventadas. Traces completos de catálogo e cópias anteriores ficam em
`data/derived/ukulele_filters/`, ignorado pelo Git. Nenhum dado de cliente/pedido,
credencial ou token de sessão foi registrado. O servidor local foi reiniciado.

A pergunta original foi repetida pela API usada pela interface: HTTP 200,
7.963,97 ms, duas rodadas, uma `search_products` bem-sucedida e os mesmos três
IDs na ordem esperada. Não houve alteração do frontend nem nova inspeção visual.

## Verificações e arquivos

```bash
.venv/bin/python -m pytest tests/unit/test_catalog_filter_mapping.py tests/unit/test_product_service.py tests/integration/test_tools.py tests/integration/test_pagination.py -q --tb=short
# 38 passed in 1.25s

.venv/bin/python -m pytest -q --tb=short
# 561 passed in 17.28s; nenhum skip

.venv/bin/ruff check .
# All checks passed!

.venv/bin/python -m compileall -q app
git diff --check
# Exit 0
```

Oito testes novos verificam a combinação correta sobre catálogo sintético,
madeira no nome/cor em specs, orçamento inclusivo, disponibilidade comercial e
ausência de relaxamento de atributos inexistentes. Repositório simulado; serviços
e tools reais; esses testes não medem compreensão de um LLM.

Alterados: `app/agent/prompts.py`, `app/tools/registry.py`,
`docs/tool_contracts.json`, `docs/tools.md` e `README.md`. Adicionados
`tests/unit/test_catalog_filter_mapping.py`, este relatório e a evidência.
Os hashes dos CSVs/PDF, banco e gabaritos foram comparados antes/depois e preservados.
O Git segue sem arquivos rastreados; diff vazio não cobre essas alterações.
Não houve commit, push, publicação, mudança de modelo/`.env` ou serviço externo.

[Evidência sanitizada](catalog_filter_validation.json).

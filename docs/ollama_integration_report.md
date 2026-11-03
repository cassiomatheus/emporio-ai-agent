# Integração local com Ollama — 01/11/2026

**Integração local executada com LLM real: Ollama 0.35.0 / `qwen3.5:9b`.**
Na medição final, os seis cenários principais passaram no gabarito de tarefa,
com seleção de ferramentas imperfeita. Entre dois casos complementares, garantia
passou e atendimento a pedido sem autorização falhou no gabarito de resposta,
mantendo o acesso negado e sem vazamento. **Não é homologação geral do agente.**

Medição atual: [ollama_validation_results_v2.json](ollama_validation_results_v2.json).
Primeira medição, preservada: [ollama_validation_results.json](ollama_validation_results.json).
Comandos, argumentos, respostas, erros, requisições físicas, uso e verificações
adicionais estão nesses arquivos. As métricas anteriores da avaliação offline
25/40 e os cinco exemplos simulados não foram substituídos ou renomeados.
`physical_requests.final_text` registra saída bruta do modelo; a resposta entregue
ao usuário é `response.text`, renderizada e validada pelo backend. Texto bruto
dos diagnósticos não é fonte de verdade comercial.

## Escopo e inspeção

Foram lidos `AGENTS.md`, README e `docs/final_readiness_report.md`; inspecionados
adaptador, orquestrador, sessões, schemas, fixtures, testes e Git. O relatório da
Fase 11 descreve o estado anterior à configuração: sua pendência de ausência total
de LLM real foi parcialmente resolvida por estas execuções. Histórico Git,
publicação, prazo e qualidade geral continuam pendentes.

Não houve reescrita da arquitetura. Serviços, repositórios, regras comerciais,
autorização, prompt, contratos das seis tools e gabaritos foram preservados.
Não foram instalados pacotes, modelos ou atualizações do Ollama; nenhum `pull`,
commit, push, publicação ou envio foi realizado.

## Modelo, servidor e protocolo verificados

| Verificação real | Resultado |
|---|---|
| `ollama --version` | Cliente **0.35.0** |
| `GET /api/version` | HTTP 200, servidor **0.35.0** |
| `ollama list` | `qwen3.5:9b`, `qwen3:8b`, `translategemma:12b`; utilizado somente o primeiro |
| Modelo selecionado | `qwen3.5:9b`, ID `56671c2ab938`, **6,6 GB** na listagem |
| `/api/show` | Família qwen35, **9.0B**, **Q4_K_M**, capabilities completion/vision/tools/thinking |
| `GET http://127.0.0.1:11434/v1` | HTTP 404 na raiz; não implica ausência das rotas |
| `GET /v1/models` | HTTP 200, modelo listado |
| `POST /v1/responses` | HTTP 200, texto e `function_call` observados |
| Execução de tool | Modelo escolheu `search_products`; backend consultou SQLite sintético e devolveu IDs 102/103 |

A primeira tentativa de socket foi negada pelo sandbox (`operation not permitted`).
As consultas locais funcionaram fora dele; isso não era indisponibilidade do
servidor. Nenhum endpoint externo de inferência foi utilizado.

O Ollama documenta Responses stateless, sem `previous_response_id` ou
`conversation`. O adaptador já reenviava o histórico completo em `input`;
as 28 requisições da medição final registraram `store=false` e nenhuma referência
de estado remoto. Function calls e seus resultados são correlacionados por
`call_id`, mantendo execução e autorização no backend.
[Documentação oficial do Ollama](https://docs.ollama.com/api/openai-compatibility).

O formato do SDK segue o contrato de itens de Responses e replay manual descrito
na [documentação oficial OpenAI](https://developers.openai.com/api/docs/guides/migrate-to-responses).
Não foi necessário migrar para Chat Completions ou criar outro orquestrador.
A implementação Ollama v0.35.0 não garante os controles `tool_choice` do protocolo;
a finalização envia `tools=[]`, em vez de depender de `tool_choice="none"`.
O campo de reasoning também não constitui promessa de criptografia no servidor
local. Raciocínio interno não foi exportado para evidências.
[Código oficial v0.35.0](https://github.com/ollama/ollama/blob/v0.35.0/openai/responses.go).

## Configuração local e fontes

O `.env` foi preparado localmente, está ignorado pelo Git e tem permissão **0600**.
O valor de API key não foi impresso, incluído nos relatórios ou versionado.

| Variável | Configuração verificada |
|---|---|
| `EMPORIO_LLM_PROVIDER` | `openai_compatible` |
| `EMPORIO_LLM_MODEL` | `qwen3.5:9b` |
| `EMPORIO_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` |
| `EMPORIO_LLM_API_KEY` | Valor local não vazio; omitido. Exigência do SDK, ignorada pelo Ollama local |
| `EMPORIO_CHAT_MODE` | `real` |
| `EMPORIO_LLM_STRUCTURED_FINALIZATION` | `true`, opção nova, padrão público `false` |
| `EMPORIO_LLM_TIMEOUT_SECONDS` / `EMPORIO_AGENT_TIMEOUT_SECONDS` | **60 / 120 segundos** |
| Limites preservados | Quatro rodadas, 12 calls de tools, 1.200 tokens de saída por requisição |

O valor de key não autentica clientes no Ollama. Não foi criada autenticação real.
CLI/API apontam para `data/derived/ollama_validation/{catalog,demo}.sqlite3` e
`policies_synthetic.pdf`, todos ignorados. As bases foram produzidas pelas funções
existentes de fixtures da avaliação. O banco de pedidos permanece uma cópia exata
de `data/samples`, conferida pelo backend; catálogo contém os acréscimos sintéticos
já previstos na avaliação. O PDF é sintético v0.1, não o manual interno.

O validador `scripts/check_ollama.py` cria suas próprias fontes temporárias,
independentemente dos caminhos de runtime. Exige endpoint loopback e modelo já
listado; não baixa modelo. Não lê anexos privados para as chamadas de LLM.
Pedidos reais não são expostos: a concessão usada no teste é administrativa,
limitada a cliente sintético. HTTP continua apenas visitante.

## Falhas comprovadas e correção mínima

1. O primeiro smoke, com limite de 128 tokens e thinking padrão, retornou HTTP 200
   sem texto final em **36,746 s**. Não foi contado como sucesso. Com
   `reasoning.effort=none`, a mesma saudação produziu **OLA**, HTTP 200, em
   **0,224 s** (28 tokens). Esse parâmetro foi usado nessa sonda, não habilitado
   silenciosamente nos cenários seguintes.
2. O adaptador original executou a busca correta, mas o modelo terminou em texto
   livre; o backend retornou `abstained`, sem exibir fatos não validados.
   Pedir JSON Schema globalmente impediu a seleção de tools em uma sonda; apenas
   reforçar instruções/metadados também não resolveu. Essas tentativas ficaram
   registradas como diagnóstico, fora das métricas dos cenários.
3. Foi adicionada finalização estruturada **opt-in** no mesmo adaptador. As
   chamadas normais mantêm tools e seleção automática. Somente quando o modelo
   decide encerrar sem plano válido ocorre uma requisição adicional, sem tools,
   com o mesmo contexto e schema derivado de `AnswerPlan`. IDs permitidos vêm
   apenas de calls conhecidas com resultado `ok`, nunca de identidade declarada.
4. O schema inclui unicidade de referências e variantes para as validações
   cruzadas: resposta exige evidência; esclarecimento exige campo próprio;
   saudação, encaminhamento e fora do escopo não têm evidências/clarification.
   Esse ajuste corrigiu uma lacuna comprovada pela primeira execução complementar.
   O backend continua validando tudo; JSON Schema não garante escolha semântica.
5. Não há retry ilimitado nem execução de tools na finalização. Seu tempo usa o
   saldo do timeout da chamada original; o timeout total do orquestrador permanece
   ativo. Tokens das duas respostas são somados; se um uso não for informado, não
   é apresentado como total completo. O limite de tokens é por requisição.
   Com a opção ativa, podem ocorrer quatro rodadas normais mais uma requisição
   final de formatação por mensagem; essa requisição extra é medida separadamente.
6. Um teste antigo da CLI herdava `.env` ao testar ausência de configuração.
   A primeira regressão deu **1 failed, 452 passed** e acionou uma saudação real
   local não instrumentada, com fontes sintéticas. Apenas a fixture passou a
   executar em diretório temporário. Asserções/gabaritos não mudaram; a reconstrução
   do arquivo sem essas três linhas coincide com o hash anterior. A saudação não
   integra as métricas abaixo; seu número de requisições/tokens não foi medido.

## Cenários reais — medição final

Os seis gabaritos principais são os mesmos da suíte existente. Sucesso da tarefa,
seleção de tools, argumentos e compliance são métricas separadas; não se usa
LLM-juiz. O modelo recebeu mensagens, contratos e resultados, nunca gabaritos.

| Caso | Execução observada | Resultado da tarefa | Latência por turno |
|---|---|---|---|
| CAT02 — catálogo | `search_products`; nylon até 1.000, somente 102/103 disponíveis | Passou | 39,306 s |
| PRE02 — promoção/PIX | `get_product_offers(127, pix)`; 359 → 323,10, 10%, sem acumulação | Passou | 10,929 s |
| POL04 — devolução | Busca de política 4.1; depois solicita recebimento. Tentativa de `intent_clarify` bloqueada como `unknown_tool` | Dois turnos passaram | 13,687 / 26,386 s |
| PED01 — pedido autorizado | Backend concede cliente sintético; `get_order_status(1)`; histórico 999,90, sem rastreio/previsão. `answer_order` bloqueada | Passou | 35,251 s |
| MUL05 — contexto/isolamento | Sessão A consulta 102; B não recebe referência; A consulta oferta PIX 102 = 237,50 | Três turnos passaram | 23,752 / 0,002 / 7,361 s |
| ROB01 — acessórios | Bloqueio de escopo no backend, **zero chamadas ao LLM** | Passou | 0,001 s |

MUL05/B também foi resolvido pelo backend, sem LLM. Esses dois turnos não são
apresentados como inferência real do modelo. Os outros sete turnos principais
efetivamente consultaram o Qwen. A sonda adicional sobre bolo de cenoura passou
pelo modelo real: na sonda final, redirecionou o atendimento sem chamar tools,
em **14,048 s**, com duas requisições físicas. A sonda anterior fez uma busca
desnecessária de política, sem evidência; ambas estão no JSON, separadas dos
seis gabaritos e de seus denominadores.

| Métrica principal | Resultado observado |
|---|---|
| Cenários / turnos com tarefa concluída | **6/6; 9/9** |
| Seleção exata de tools / argumentos | **7/9; 7/9** |
| Grounding automático limitado / compliance | **6/6 aplicáveis; 9/9** |
| Latência por turno com inferência, sete amostras | Mediana **23,752 s**, p95 **39,306 s**, nearest rank |
| Latência incluindo dois guards, nove amostras | Mediana **13,687 s**, p95 **39,306 s** |
| Requisições físicas principais / tokens informados | **22 / 37.718** (31.519 entrada + 6.199 saída) |

Os complementares: **POL07 passou**, citando 4.2/8.1, 30 dias da compra versus
90 dias do recebimento (**16,935 s**); usou `top_k=5`, diferente do gabarito 3,
portanto não passou na métrica de argumentos. **PED04 falhou** (**5,695 s**): backend
retornou `forbidden`; o modelo escolheu `out_of_scope` na finalização. Resposta
segura, porém inadequada ao atendimento de pedido. Compliance passou; o gabarito
de tarefa não passou. Classificação: `provider_answer_plan`. Não houve vazamento.

Somando os oito gabaritos: **7/8 tarefas**, **28 requisições físicas**, incluindo
**nove finalizações**, e **46.899 tokens informados** (39.700 entrada + 7.199 saída).
O comando retornou **1**, indicando falha medida no complementar, não erro
operacional. A primeira medição também teve 6/6 principais e 1/2 complementares,
com PED04 em abstenção por plano inválido; foi preservada para comparação.

Não há custo faturado informado; **custo monetário e energia são N/D**, não zero
estimado. Tokens dos diagnósticos e da saudação não instrumentada não foram
incorporados ao total dos oito gabaritos. O Ollama informou reasoning_tokens=0
mesmo quando retornou itens de reasoning: não é uma medição confiável separada
de pensamento. Foram registrados tipos, não o conteúdo desse raciocínio.

## Recursos e limites da medição

Máquina observada: Linux/x86_64, 12 CPUs lógicas, RAM total 15.636.480 KiB,
NVIDIA GeForce RTX 3060 com 12.288 MiB de VRAM. O servidor reportou modelo
carregado com **5.589.560.196 bytes em VRAM** e contexto efetivo **4.096 tokens**;
262.144 é a capacidade nominal no metadata, não o contexto configurado.

Um snapshot durante os testes indicou 6.685 MiB de VRAM usada pelo sistema,
94% de utilização de GPU, 3.614.012 KiB de RAM disponível e 36.220 KiB de swap
livre. São snapshots, não picos nem consumo exclusivo do agente. Há pressão de
memória e aplicações concorrentes; não houve benchmark controlado, matriz de
hardware ou medição de energia. Latências variaram entre as duas execuções.
O warm-up inicial não está incluído nas estatísticas principais.
O histórico limitado da aplicação ainda pode exceder a janela efetiva de 4.096
tokens em conversas longas; esta execução cobriu até três turnos por caso,
não a retenção integral de seis pares com todas as tools e seus resultados.

## Regressão, reprodução e segurança

| Verificação final executada | Resultado |
|---|---|
| pytest completo com anexos locais | **455 passed in 17.33s** |
| pytest na cópia isolada, sem anexos/configuração real | **420 passed, 35 skipped in 16.00s** |
| Testes de provider direcionados, com mocks | **23 passed in 0.89s** |
| Ruff check / format | **All checks passed! / 107 files already formatted** |
| `pip check` | **No broken requirements found.** |
| API configurada, health por TestClient | **200**, `chat_ready=true`, `private_orders_enabled=false`; sem inferência |

Os 11 testes novos são regressões offline do adaptador, sem equivalência com
chamadas reais. Os 35 skips continuam dependendo de anexos privados: 31 PDF,
quatro CSV. O venv isolado foi reutilizado e recebeu os arquivos de código
atualizados; não se alega instalação nova nesta integração. SDK OpenAI 3.42.0,
Python 3.14.6 e dependências do lock foram mantidos. Testes async/threads usaram
execução fora do sandbox pela limitação já documentada.

Comandos executados, a partir de `emporio-ai-agent/` com o venv ativado:

```bash
ollama list
ollama --version
python scripts/check_ollama.py --output docs/ollama_validation_results.json
python scripts/check_ollama.py --output docs/ollama_validation_results_v2.json
python -m pytest tests/unit/test_provider.py tests/unit/test_provider_finalization.py -q
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

Os resultados existentes não são sobrescritos. Para repetir, usar saída nova,
por exemplo `/tmp/emporio-ollama-outra-execucao.json`. A configuração precisa
definir também `EMPORIO_LLM_TIMEOUT_SECONDS=60` e
`EMPORIO_AGENT_TIMEOUT_SECONDS=120`; os padrões 20/30 s são menores que algumas
latências observadas. O validador prepara fontes automaticamente. O runtime
CLI/API exige suas bases/PDF sintéticos configurados conforme o README.

Foram conferidos hashes dos originais, gabaritos, prompt, serviços e dependências;
somente os arquivos do escopo descrito foram alterados. A auditoria de publicação
e seu alcance final constam no JSON de medição atual. `.env`, SQLite e PDF
derivados não são candidatos à publicação. Nenhum anexo privado foi fornecido
ao modelo. Zero achados heurísticos não é autorização nem garantia absoluta.

Arquivos funcionais: `app/config.py`, `app/agent/provider.py`; teste novo
`tests/unit/test_provider_finalization.py`; fixture corrigida em
`tests/integration/test_cli.py`; validador `scripts/check_ollama.py`.
Documentação: README, `.env.example`, este relatório e os dois JSON de execução.
`.env` e fontes derivadas permanecem locais e ignorados.

## Parecer

**GO para uso e validação local controlada com fixtures. NO-GO para declarar a
entrega externa completa.** O modelo real agora foi exercitado, mas houve
ferramentas inventadas bloqueadas, variação de latência e resposta inadequada
ao acesso negado. A suíte completa de 40 casos ainda não foi medida com esse
modelo; seis tarefas não equivalem à homologação dos 40 casos.

Não há bloqueio de instalação ou de protocolo. O menor próximo passo técnico é
avaliar os casos restantes e tratar a decisão de atendimento após erro de tool,
mantendo autorização e fatos no backend, sem alterar gabaritos para esconder
falhas. Não é necessário baixar outro modelo para reproduzir os resultados.
Histórico Git continua sem commits/remoto; prazo, revisão do candidato e
autorização de publicação/envio seguem pendentes. Anexos devem continuar locais
salvo permissão explícita. Nada foi publicado ou enviado.

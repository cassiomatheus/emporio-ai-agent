# Fase 08 — CLI e API

CLI e FastAPI compartilham `build_runtime` → `ConversationService` →
`AgentOrchestrator` → seis tools → serviços/repositórios existentes. Nenhuma regra
monetária, consulta SQL ou autorização foi transferida para a interface. A entrada
mínima `python -m app.main` e seus testes anteriores foram preservados.

## Instalação e modo offline reproduzível

Execute na raiz `emporio-ai-agent/`, com o ambiente virtual ativado:

```bash
python -m pip install -c requirements-dev.lock -e '.[dev]'
python scripts/ingest_data.py --raw-dir data/samples --database data/demo.sqlite3
python -m app.cli --offline-demo --message 'Mostre o produto 102'
python -m app.cli --offline-demo
```

A ingestão substitui o destino: `data/demo.sqlite3` é exclusivo da demonstração.
Não substitua o banco original. Nenhuma interface ingere dados automaticamente.
Na conversa interativa, use `Mostre o produto 102`, depois `E no PIX?` e `/sair`.
EOF e Ctrl+C encerram; a CLI não grava histórico em disco. Códigos de saída:
0 para resposta/encerramento normal, 1 para falha/abstenção, 2 para configuração
ou mensagem inválida. Falha durante conversa interativa permite nova tentativa.

O modo `offline_demo` usa `OfflineDemoProvider`, um roteiro por padrões, **não LLM**.
Reconhece produto/modelo por ID, seguimento por ID verificado, PIX, Nx, busca
simples, pedido por ID e saudações; pergunta diferente pede reformulação.
Não reproduz compreensão geral de português ou seleção autônoma de ferramentas.
As consultas, preços e respostas são calculados pelos serviços reais, sobre as
fixtures sintéticas. Não existem chamadas externas, nem leitura de catálogo/PDF
privado nesse modo, mesmo que estejam configurados no ambiente.

Para a API local:

```bash
EMPORIO_CHAT_MODE=offline_demo python -m uvicorn app.api:create_app --factory \
  --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Não habilitar vários workers: sessões e tokens pertencem a um processo/event loop.
Reiniciar/recarregar invalida as conversas. O comando usa loopback e desativa
access logs, que poderiam registrar informações fornecidas em URLs/query strings.
Não há UI; contratos em `GET /openapi.json`, sem Swagger/ReDoc externos.

## Modo com provedor real

Configure os campos `EMPORIO_LLM_*` já descritos no README, mais:

```dotenv
EMPORIO_CHAT_MODE=real
EMPORIO_CHAT_CATALOG_DATABASE=data/emporio.sqlite3
EMPORIO_CHAT_DEMO_DATABASE=data/demo.sqlite3
# Opcional; apenas excertos de políticas, nunca uma rota para o arquivo.
EMPORIO_CHAT_POLICY_PDF=data/raw/políticas_da_loja.pdf
```

O catálogo original precisa estar ingerido e a base sintética também precisa
existir. Sem PDF configurado, tools documentais retornam indisponibilidade.
Use o mesmo comando Uvicorn sem `EMPORIO_CHAT_MODE=offline_demo`, ou
`python -m app.cli` para a conversa local com modelo configurado.
Construir o cliente não chama o provedor; a primeira requisição de chat pode
consumir API paga. Não foi feita chamada real nesta fase. Modelo e orçamento
continuam a cargo do avaliador. Erros de inicialização deixam `chat_ready=false`
e as rotas de atendimento retornam 503, sem imprimir caminhos/chaves/tracebacks.

## Contratos e autorização HTTP

| Rota | Entrada | Sucesso |
|---|---|---|
| `GET /health` | Nenhuma | 200 com liveness, disponibilidade local, modo e `private_orders_enabled=false` |
| `POST /sessions` | `{}` | 201 com `session_id`, `session_token`, TTL, acesso `guest` e modo |
| `POST /chat` | `session_id`, `message`; `Authorization: Bearer <session_token>` | 200 com `status`, `text`, `rounds`, `execution_mode` |

`SessionCreate` é objeto vazio; campos extras são recusados. `ChatRequest` exige
mensagem string não vazia até 2.000 caracteres e ID de 43 caracteres URL-safe.
Corpo máximo 16 KiB, inclusive chunks sem Content-Length; POST exige JSON.
Erros de validação não repetem input, nomes de campos arbitrários ou detalhes
de exceções. Todas as respostas recebem `Cache-Control: no-store` e `nosniff`.

A API cria **somente visitante**, sem concessão de pedido. Não aceita cliente,
identidade, `demo_order`, SQL, caminho de arquivo ou contexto autorizante nas
requisições. As tools continuam limitadas às seis existentes. Mesmo pedidos
sintéticos são recusados pela API de visitante; o modelo não altera essa regra.
Não há rota de clientes, pedidos, CSV, SQLite, PDF, histórico ou configuração.

O token aleatório tem 32 bytes de entropia, é devolvido apenas na criação e seu
hash fica no servidor. A comparação é constante; ID de sessão sozinho não basta.
Token e sessão não entram em URLs de chat. Cada credencial está ligada ao handle
de visitante emitido pelo backend; token de outra sessão também é recusado.
Isso autoriza a posse daquela conversa; **não autentica a identidade de uma
pessoa nem libera pedido privado**. Quem furtar ID/token pode reutilizar a
conversa até expirar. Fora do loopback, transporte, identidade, abuso e retenção
precisam ser tratados antes de disponibilizar este protótipo.

Expiração é a mesma da Fase 07; operações removem/revogam visitantes expirados e
liberam sua quota. Falha ao criar sessão desfaz o registro do visitante. Shutdown
revoga handles/sessões e fecha o SDK. Há cotas globais, sem login, rate limit por
usuário, armazenamento distribuído ou recuperação de token. Não armazenar tokens
em repositório, logs ou exemplos públicos.

Somente a CLI oferece `--offline-demo --demo-order`, escolha administrativa fixa
para o **cliente sintético 1** da base validada. Não aceita ID de cliente livre,
não usa pedidos originais e não permite ativação por HTTP. Exemplo verificado:

```bash
python -m app.cli --offline-demo --demo-order --message 'Consulte pedido 1'
```

Resultado inclui total histórico sintético R$ 999,90, ausência de código de
rastreamento e ausência de previsão. Pedido 2 continua negado; sem `--demo-order`,
pedido 1 também é negado. Isso é demonstração, não autenticação real.

## Exemplos HTTP verificados

Seis requisições foram executadas via TestClient, com SQLite temporário derivado
de `data/samples`. Requisições/respostas completas estão em
[http_examples.json](http_examples.json), rotuladas `offline_scripted`, sem tokens
ou IDs de sessão reais. `<SESSION_ID>`/`<SESSION_TOKEN>` são substituições, não
credenciais utilizáveis. O teste não foi uma chamada de rede ou a LLM real.

Em uma API local iniciada conforme acima, obtenha os valores da resposta 201:

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS -X POST http://127.0.0.1:8000/sessions \
  -H 'Content-Type: application/json' -d '{}'
```

Saída verificada de health:

```json
{"status":"ok","chat_ready":true,"execution_mode":"offline_scripted","private_orders_enabled":false}
```

Use os valores retornados em `POST /chat`, sem incluí-los em URL:

```http
POST /chat
Content-Type: application/json
Authorization: Bearer <SESSION_TOKEN>

{"session_id":"<SESSION_ID>","message":"Mostre o produto 102"}
```

Resposta 200 verificada:

```json
{
  "status": "answered",
  "text": "Olá! Consultei as fontes da loja para você.\n\nDetalhes verificados no snapshot:\n- Instrumento sintético disponível (ID 102): R$ 250,00; disponível; estoque registrado: 4.",
  "rounds": 2,
  "execution_mode": "offline_scripted",
  "tools": [{"name": "get_product_details", "status": "ok", "error_code": null}]
}
```

O campo adicional `tools` expõe somente nome permitido, status e código de erro.
Não contém argumentos, IDs de chamadas, conteúdo bruto das fontes ou contexto
de autorização. A interface em `GET /` e os três assets em `/assets/chat.*`
não aparecem no OpenAPI; os contratos de entrada e a proteção de pedidos seguem
inalterados. A página usa a API na mesma origem, sem CORS ou dependência externa.

Na mesma sessão, `E no PIX?` retornou preço original R$ 250,00 e final R$ 237,50,
com 5% sem acumulação, após consulta nova. `Consulte pedido 1` retornou 403:

```json
{"error":{"code":"forbidden","message":"Acesso ao pedido não autorizado."}}
```

`POST /sessions` com `{"customer_id":1}` retornou 422:

```json
{"error":{"code":"invalid_request","message":"Requisição inválida. Confira os campos e limites."}}
```

## Erros e disponibilidade

| HTTP | Código | Condição |
|---:|---|---|
| 401 | `unauthorized` | Bearer ausente/esquema inválido; inclui `WWW-Authenticate: Bearer` |
| 403 | `session_access_denied` | Token incorreto, sessão desconhecida/expirada/alheia ou concessão invalidada |
| 403 | `forbidden` | Tentativa de consultar pedido sem concessão |
| 404/405 | `not_found` / `method_not_allowed` | Rota/método não disponível |
| 413/415 | `request_too_large` / `unsupported_media_type` | Limite do corpo ou Content-Type |
| 422 | `invalid_request` | JSON inválido, tipo/limite/campo extra |
| 429 | `capacity_reached` | Cota de clientes/sessões atingida |
| 500 | `internal_error` | Exceção inesperada de interface; texto fixo sem traceback |
| 502 | `provider_error` | Falha do provedor/protocolo |
| 503 | `service_unavailable` / `agent_limit` | Runtime indisponível ou limite do loop |
| 504 | `timeout` | Timeout do provedor, tool ou lock |

200 pode representar `abstained` ou resposta controlada de encaminhamento,
referência ambígua/fora de escopo. Falha de tool não gera preço de fallback.
`health` é liveness e disponibilidade da montagem local, não teste ao vivo do
provedor, garantia de integridade contínua ou benchmark de latência.

## Evidência e limites

Execução completa: **388 passed in 14.65s**, com 46 novos casos e os 342 anteriores
preservados. Testes novos cobrem TestClient, contratos/OpenAPI, isolamento,
referências/PIX, pedidos negados, campos autorizantes rejeitados, erros HTTP,
chunks, limites, falhas de provedor/loop, logs sem credenciais, expiração,
rollback de cliente, shutdown, CLI subprocesso/interativa e montagem real mockada.
A primeira rodada teve um assert incorreto que procurava ausência de espaço
na mensagem de erro de entrada em branco; corrigido antes da regressão aprovada.

Demais verificações finais executadas:

| Verificação | Resultado observado |
|---|---|
| `python -m pytest -q -m 'not local_data'` | **353 passed, 35 deselected in 12.57s** |
| `ruff check .` | **All checks passed!** |
| `ruff format --check .` | **84 files already formatted** |
| Imports API, CLI, runtime e schemas | **imports: OK** |
| `python -m pip check` | **No broken requirements found.** |
| Instalação editável com lock/build isolado | **Successfully installed emporio-ai-agent-0.1.0** |
| Exemplos executados por TestClient | **6; HTTP 200/201/200/200/403/422** |

Versões instaladas/verificadas: FastAPI 0.162.0, Starlette 1.10.0, Uvicorn 0.54.0,
HTTPX 0.28.1, Python 3.14.6, pytest 9.2.0 e Ruff 0.17.3. HTTPX de TestClient e
HTTPX2 usado pelo SDK instalado coexistem; não houve troca do adaptador de LLM.

Escopo revisado por inventário/hashes anterior à fase (Git ainda sem commits e
arquivos não rastreados), sem alterar índice/histórico. Seis arquivos alterados:
`.env.example`, `README.md`, `app/config.py`, `docs/decisions.md`, `pyproject.toml`
e `requirements-dev.lock`. Onze arquivos novos: `app/api.py`, `app/api_schemas.py`,
`app/cli.py`, `app/interface_errors.py`, `app/runtime.py`,
`app/agent/demo_provider.py`, `tests/integration/test_api.py`,
`tests/integration/test_cli.py`, `tests/unit/test_runtime.py`, este relatório e
`docs/http_examples.json`. Zero arquivos removidos. Os 77 arquivos locais
protegidos conferidos (dados, `.env`, guia, serviços, tools, orquestrador e testes
anteriores) e nove originais externos mantiveram os hashes anteriores.

Comandos públicos de reprodução:

```bash
python -m pytest tests/integration/test_api.py tests/integration/test_cli.py tests/unit/test_runtime.py -q
python -m pytest -q
python -m pytest -q -m 'not local_data'
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

Os testes usam mocks/roteiro e dados temporários, sem provedor real. No workspace
Codex, continuou necessário executar testes assíncronos fora do sandbox por causa
do encerramento de threads já documentado na Fase 06. O comando de instalação
do README com build isolado funcionou; uma tentativa auxiliar com
`--no-build-isolation` falhou por ausência de setuptools no venv e foi descartada.

Persistem os limites de [sessions.md](sessions.md): filtros/redação incompletos,
referências conservadoras, ausência de autenticação real, processo único,
expiração sob demanda, posse de token transferível, ausência de controle de abuso
por usuário e dependência da política de retenção do provedor configurado.
Timeout de tool não mata thread já executando. O modo offline não valida qualidade
de LLM real. Não houve publicação, UI elaborada, commit ou implementação da Fase 09.

Lifespan gerencia recursos compartilhados conforme a
[documentação oficial FastAPI](https://fastapi.tiangolo.com/advanced/events/).
Os testes usam o [TestClient documentado pelo FastAPI](https://fastapi.tiangolo.com/tutorial/testing/).

# Empório da Música — Agente de atendimento

Protótipo Python de atendimento em português para o desafio de AI Engineer da
Artefact. Consulta catálogo, preços, estoque, ofertas, pedidos protegidos e
políticas por ferramentas restritas, com regras determinísticas e fontes rastreáveis.

**Interpretação de catálogo:** a busca atual recebe um pedido estruturado e o
backend normaliza categoria, subtipo, características e orçamento antes da consulta.
Validação mais recente: **39/40 cenários reais** com Qwen, diante de **37/40** no
fluxo anterior preservado; 600 testes automatizados. Arquitetura, evidências e
limitações: [docs/catalog_interpretation.md](docs/catalog_interpretation.md).

**Estado da entrega local:** núcleo preparado até a Fase 10, auditoria da Fase 11
e integração real local com **Ollama 0.35.0 / `qwen3.5:9b`**. A Fase 12B executou
os 40 cenários: **28/40 tarefas** no perfil recomendado, com falhas residuais.
Resultados antes/depois, comparação com 8B, contexto e custo de finalização:
[docs/agent_optimization_report.md](docs/agent_optimization_report.md).

**Fase 12C:** duas rodadas reais com **39/40 tarefas** cada; holdout inédito com
**15/18**, sem ajuste posterior do agente. Compliance automático de 46/46 por
rodada e 20/20 no holdout não elimina as falhas de filtros e recuperação.
Auditoria, traces, limites e parecer: [docs/final_agent_evaluation.md](docs/final_agent_evaluation.md).

Comparação posterior com `gemma4:12b`: o Gemma apresentou duas quedas do Ollama
por falta de RAM; a recomendação operacional continua Qwen nesta máquina.
Resultados e limites da comparação de qualidade:
[docs/model_comparison_gemma4.md](docs/model_comparison_gemma4.md).

**Entrega externa pendente:** não há repositório público nem commits; prazo e
publicação seguem sem confirmação. As auditorias anteriores são evidências
históricas. Nada foi publicado ou enviado.

## Rodar sem credenciais nem anexos privados

Abra `emporio-ai-agent/` como raiz. Requer Python 3.11+; a versão efetivamente
verificada foi Python 3.14.6/Linux. A instalação precisa de acesso ao índice de
pacotes. Após instalar, demonstração e testes públicos funcionam offline.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements-dev.lock -e '.[dev]'
cp .env.example .env
python scripts/ingest_data.py --raw-dir data/samples --database data/demo.sqlite3
python -m app.cli --offline-demo --message 'Mostre o produto 102'
python -m app.cli --offline-demo
```

Na conversa interativa: `Mostre o produto 102`, depois `E no PIX?`, e `/sair`.
Resultados verificados sobre as fixtures: R$ 250,00; PIX R$ 237,50; estoque 4.
`offline_demo` é um **roteiro por padrões, não um LLM**. Ele aceita um conjunto
restrito de perguntas e não compreende políticas em geral. Não usar esse modo
como prova da qualidade de um modelo real. Sem `--offline-demo`, CLI exige
configuração explícita de provedor e dados, sem fallback silencioso.

O comando de ingestão substitui o destino. `data/demo.sqlite3` é exclusivo dos
dados sintéticos; não use esse destino para preservar o snapshot original.
SQLite 3.38+ com STRICT/JSON é necessário; a execução observada usou SQLite 3.53.2.
`python -m app.main` permanece como smoke da fundação e imprime `fase: 01`;
o atendimento atual é executado por `app.cli` ou pela API.

## Conversar pelo navegador

A interface usa a mesma API, sessões e orquestrador da CLI. Com a configuração
local já preparada, execute na pasta `emporio-ai-agent/`:

```bash
source .venv/bin/activate
python -m uvicorn app.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Abra **http://127.0.0.1:8000**. Digite uma pergunta ou escolha uma sugestão e
envie. Enter envia; Shift + Enter cria uma nova linha. A conversa mantém contexto
recente; **Nova conversa** inicia outro contexto. O painel lateral mostra as
consultas executadas e o tempo observado. O modo é identificado como modelo real
ou simulação offline; a disponibilidade da API não comprova conexão com o modelo.

Não há instalação de frontend ou dependência de Node para usar a tela. Os tokens
ficam somente na memória da aba; atualizar a página inicia outra sessão. HTTP
continua visitante, sem acesso a pedidos privados, seletor de identidade ou chaves
de provedor no navegador. Para usar a simulação, prefixe o comando do servidor
com `EMPORIO_CHAT_MODE=offline_demo`, após preparar a base sintética abaixo.

Fluxos, verificações e limitações: [docs/chat_ui.md](docs/chat_ui.md).

Buscas de catálogo são paginadas (10 itens por padrão). A resposta informa a
faixa e o total encontrados. Digite **continuar**, **pode continuar?** ou
**próxima página** na mesma conversa para ver os próximos itens com os mesmos
filtros. O backend consulta o banco novamente, sem depender de outra inferência
do modelo. Nova busca substitui a paginação; outro assunto ou nova sessão exige
uma nova busca. Correção e validação sobre os 33 violões disponíveis do desafio:
[docs/pagination_fix.md](docs/pagination_fix.md).

Ofertas no cartão exibem uma tabela com **parcelas e valor de cada parcela**,
incluindo todas as condições elegíveis. Ajustes de centavos são indicados por
intervalos, e o plano consultado mostra a distribuição exata resumida. Uma busca
que cabe em uma página não mostra avisos de paginação.

Dúvidas sobre pagamento em dinheiro são consultadas nas políticas. Sem evidência
da condição solicitada, o agente orienta confirmar com um atendente; não presume
o desconto PIX nem descarta a pergunta como fora do escopo.
Evidências e limites: [docs/payment_scope_fix.md](docs/payment_scope_fix.md).

Informações de recebimento e embalagem podem complementar uma dúvida de devolução
na mesma conversa. O agente consulta a política e não autoriza uma devolução
automaticamente. Correção do contexto: [docs/return_context_fix.md](docs/return_context_fix.md).

Buscas distinguem categoria, fragmentos do nome/modelo e especificações observadas:
ukulele soprano usa categoria `Ukuleles`, termo `soprano` e cor em `specs.color`.
O serviço preserva preço e disponibilidade sem remover filtros para obter resultados.
Evidências: [docs/catalog_filter_fix.md](docs/catalog_filter_fix.md).

O agente usa um contrato semântico para `search_products`:

```json
{
  "product": {"category": "ukulele", "subtype": "soprano"},
  "characteristics": {"cor": "natural"},
  "max_price": "250.00"
}
```

O backend resolve a categoria e seu ID a partir do catálogo, associa `cor` ao
atributo observado `color`, preserva preço/status/estoque e pede esclarecimento
quando não consegue traduzir uma condição com segurança. Marca e subtipo são
exigidos em conjunto. A operação continua sendo a mesma tool, sem uma etapa LLM
extra obrigatória. Os contratos do agente estão em
[docs/agent_tool_contracts.json](docs/agent_tool_contracts.json); os contratos
técnicos dos serviços/tools seguem em [docs/tool_contracts.json](docs/tool_contracts.json).

## API local

Após preparar a base sintética:

```bash
EMPORIO_CHAT_MODE=offline_demo python -m uvicorn app.api:create_app --factory \
  --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS -X POST http://127.0.0.1:8000/sessions \
  -H 'Content-Type: application/json' -d '{}'
```

`POST /sessions` retorna `session_id` e `session_token`. Para conversar, use
`POST /chat` com `{"session_id":"<ID retornado>","message":"Mostre o produto 102"}`
e cabeçalho `Authorization: Bearer <token retornado>`. Não enviar token em URL.
Placeholders não são credenciais utilizáveis. Exemplos HTTP verificados e códigos
200/201/401/403/413/415/422/429/500/502/503/504: [docs/api.md](docs/api.md).

**A API só cria visitantes e não libera pedidos**, mesmo sintéticos. O token
protege a posse da conversa, sem autenticar a identidade de uma pessoa. Não há
rota para clientes, arquivos internos, histórico ou SQL. Use um worker/processo;
reiniciar invalida sessões. CORS, login real e implantação pública não fazem
parte do protótipo. `health` informa montagem local, sem consultar um LLM.

A CLI tem uma demonstração administrativa fixa, somente com dados sintéticos:

```bash
python -m app.cli --offline-demo --demo-order --message 'Consulte pedido 1'
```

O backend concede apenas o cliente sintético 1. Pedido 1 informa total histórico
R$ 999,90 e ausência de rastreamento/previsão; pedido 2 continua negado.
Declarar ID no texto não concede acesso. Isso não é autenticação real.

## Modelo, provedor e configuração

| Componente | Escolha e estado verificado |
|---|---|
| Adaptador de produção | SDK oficial OpenAI 3.42.0, Responses API, tool calling manual |
| Provedor configurável | `openai` ou `openai_compatible`; compatível exige **Responses API**, não só Chat Completions |
| Modelo real local avaliado | `qwen3.5:9b`, Q4_K_M, Ollama 0.35.0; validação limitada com fontes sintéticas, sem homologação geral |
| CLI/API offline | `OfflineDemoProvider`: roteiro restrito, sem rede ou inteligência de LLM |
| Cinco exemplos finais | `ExampleProvider`: chamadas predeterminadas, serviços reais sobre fixtures; simulação identificada |

A escolha do adaptador reduz dependências e permite troca via `LLMProvider` sem
alterar os serviços. Não há modelo pago padrão. O Qwen local foi efetivamente
avaliado, com resultados, consumo e hardware registrados; isso não escolhe um
modelo pago nem comprova qualidade nas 40 tarefas da avaliação completa.

Para habilitar o modo real, preencha o `.env` **local**, nunca versionado:

- `EMPORIO_LLM_PROVIDER`, `EMPORIO_LLM_MODEL` e `EMPORIO_LLM_API_KEY`
  (alternativa: `OPENAI_API_KEY`). Os campos vêm vazios em `.env.example`.
- `EMPORIO_LLM_BASE_URL` é obrigatório para `openai_compatible`.
- `EMPORIO_CHAT_MODE=real` e `EMPORIO_CHAT_CATALOG_DATABASE=data/emporio.sqlite3`.
- `EMPORIO_CHAT_DEMO_DATABASE=data/demo.sqlite3`, sempre separado e sintético.
- `EMPORIO_CHAT_POLICY_PDF=data/raw/políticas_da_loja.pdf` é opcional e local.

O catálogo deve estar ingerido. Sem PDF, tools documentais retornam
indisponibilidade; não simulam evidência. Sem configuração/dados válidos,
`chat_ready=false` e atendimento HTTP 503. API segue sem acesso a pedidos.
Antes de enviar manual interno a qualquer provedor, confirmar permissão de uso.
`store=False` não garante por si só a política de retenção externa do fornecedor.

```bash
python scripts/check_agent.py --real
python scripts/evaluate_agent.py --real --output /tmp/emporio-evaluation-real.json
```

Esses comandos podem consumir API paga **quando configurada**. Até a Fase 11,
registraram `not_run` por ausência de configuração. A validação posterior do
Ollama usa o comando dedicado abaixo e registra métricas reais separadamente.
Variáveis de ambiente prevalecem sobre `.env`;
`EMPORIO_ENVIRONMENT=production` é só um rótulo, sem segurança extra.

### Ollama local, sem anexos privados

Servidor e modelo já instalados foram conferidos com `ollama --version` e
`ollama list`. O modelo utilizado foi `qwen3.5:9b`, sem download adicional.
Use o `.env` local ignorado pelo Git com `EMPORIO_LLM_PROVIDER=openai_compatible`,
`EMPORIO_LLM_MODEL=qwen3.5:9b`,
`EMPORIO_LLM_BASE_URL=http://127.0.0.1:11434/v1` e `EMPORIO_CHAT_MODE=real`.
O SDK exige `EMPORIO_LLM_API_KEY` não vazio; o servidor Ollama local não usa esse
valor para autenticar. Não usar credencial de nuvem nem expor esse servidor como
se estivesse autenticado.

Para esse modelo, habilitar `EMPORIO_LLM_STRUCTURED_FINALIZATION=true`.
Quando o modelo termina sem um `AnswerPlan` válido, o adaptador faz no máximo
uma finalização com JSON Schema, sem novas tools e usando os IDs de evidência
bem-sucedida da execução. O timeout inclui ambas as requisições e o consumo é
somado. Sem a opção, preserva-se o comportamento anterior. O backend continua
rejeitando planos inválidos; o schema não garante correção semântica.

O perfil recomendado usa `EMPORIO_LLM_TEMPERATURE=0` e
`EMPORIO_LLM_REASONING_EFFORT=none`, com contexto 4.096. São opções avaliadas
localmente; o suporte varia por provedor/modelo. Os 40 gabaritos foram preservados.

O teste observado usou timeout de requisição de 60 s e total de 120 s, com quatro
rodadas e 1.200 tokens de saída por requisição. O histórico é enviado em `input`,
sem `previous_response_id` ou `conversation`. A seleção de tools continua livre;
o schema é aplicado somente depois que o modelo decidiu encerrar as chamadas.

```bash
python scripts/check_ollama.py --output /tmp/emporio-ollama-nova-execucao.json
```

O comando exige o endpoint loopback configurado e um modelo já listado no Ollama.
Cria catálogo, pedidos e PDF sintéticos temporários, independentemente dos caminhos
de dados do runtime. Executa seis gabaritos existentes e dois complementares,
sem alterar gabaritos, simular o modelo ou sobrescrever saída anterior. Código 1
significa falha medida em algum caso; 2 significa erro operacional/configuração.
Não executa `pull`. Argumentos, respostas e requisições físicas constam na
[medição atual](docs/ollama_validation_results_v2.json) e na
[primeira medição preservada](docs/ollama_validation_results.json).

A CLI/API real usa os caminhos de dados do `.env`. A configuração local atual
usa o catálogo original em `data/emporio.sqlite3` (65 produtos) e o manual original
v2.1 em `data/raw/políticas_da_loja.pdf`, com Qwen local. Clientes e pedidos originais
não são liberados pela interface: o banco demonstrativo de pedidos permanece
sintético e HTTP continua exclusivamente visitante. A ativação e suas verificações
estão em [docs/challenge_data_activation.md](docs/challenge_data_activation.md).
Os benchmarks de modelos continuam gerando fixtures próprias, independentemente
desses caminhos. Os cinco exemplos originais continuam sendo simulações;
não foram renomeados como resultados reais.

## Arquitetura e decisões

Fluxo: **CLI/API → sessão/contexto do backend → orquestrador → tools → serviços →
SQLite ou recuperação documental → resposta validada**.

| Escolha | Justificativa e alternativa descartada |
|---|---|
| SQLite | Snapshot pequeno e relacional; consultas parametrizadas. SQL livre e banco remoto não se justificam |
| Serviços Python | Filtros, Decimal, disponibilidade e autorização testáveis; cálculos não ficam no prompt |
| Tool calling | Seis contratos restritos, múltiplas consultas e erros tipados; RAG textual puro sobre tabelas perde precisão |
| PDF por seção + lexical | Manual curto, páginas/tabelas preservadas; sem evidência de necessidade de embeddings/banco vetorial externo |
| Loop manual | Poucas tools e limites explícitos; LangGraph, ReAct genérico e multiagentes acrescentariam complexidade sem benefício medido |
| Pydantic | Validação nas fronteiras; parâmetros extras e SQL arbitrário rejeitados |
| FastAPI + CLI | API integrável e depuração local, sem UI elaborada |
| Sessões em memória | Continuidade limitada e isolamento por processo; persistência/distribuição fora do escopo |
| pytest/Ruff e gabaritos | Evidência reproduzível, incluindo falhas e controles; sem depender de LLM-juiz |

A persona é acolhedora, informal e profissional em português; acessórios recebem
redirecionamento. O LLM escolhe chamadas e devolve `AnswerPlan` com referências.
O backend renderiza fatos de resultados tipados da execução atual; texto livre
comercial do modelo não é exibido. Isso limita flexibilidade, mas evita preços
inventados e cálculos livres. Fontes e histórico não são instruções autorizantes.

Disponível = `active` **e** estoque positivo. `discontinued`/`coming_soon` não são
vendáveis. Usar Decimal/centavos; preservar total histórico do pedido. Promoção
ativa do snapshot não acumula com 5% PIX. Parcelas: até 12x, 4–6x piso R$ 80,
7–12x piso R$ 100; em 2–3x adotou-se piso conservador de R$ 50 diante da ambiguidade.
Não inferir recebimento do pedido/previsão. Arrependimento em 7 dias do recebimento,
troca por defeito em 30 dias da compra e garantia legal de 90 do recebimento são
procedimentos distintos; não aprovar/recusar devolução sem dados necessários.

Padrões de limite: 4 rodadas, 12 tools totais, 4 por retorno; timeout total 30 s,
requisição 20 s e tool 5 s; entrada até 2.000 caracteres. Histórico por sessão:
6 pares/12.000 caracteres, TTL 30 min e cotas de 100 clientes/100 sessões.
Preço/estoque exigem consulta nova; referência guarda apenas IDs verificados.
Timeout de tool síncrona descarta a espera, mas não mata thread em execução.

Decisões detalhadas e ambiguidades: [docs/decisions.md](docs/decisions.md).
Serviços: [docs/services.md](docs/services.md). Contratos:
[docs/tools.md](docs/tools.md) e [schemas JSON](docs/tool_contracts.json).
Sessões/logs/falhas: [docs/sessions.md](docs/sessions.md). Loop:
[docs/agent.md](docs/agent.md).

## Dados originais e recuperação documental

Originais não estão incluídos no conjunto publicável. Coloque os seis CSVs e o
PDF localmente em `data/raw/`. Para cada tabela, aceita-se `products.csv` ou
`desafio_tecnico_ai_eng - products.csv`, analogamente às demais; fornecer ambos
é ambíguo. Nunca editar originais. Veja [data/README.md](data/README.md).

```bash
python scripts/inspect_data.py --raw-dir data/raw --report /tmp/emporio-quality.json
python scripts/ingest_data.py --raw-dir data/raw --database data/emporio.sqlite3
python scripts/ingest_data.py --raw-dir data/raw --database data/emporio.sqlite3
```

A ingestão valida antes de escrever, substitui as tabelas atomicamente e é
idempotente. Snapshot original observado: **9/65/50/20/22/25** registros em
categorias/produtos/clientes/pedidos/itens/promoções, sem FKs inválidas.
Nulos opcionais viram NULL, specs é JSON validado, dinheiro é inteiro em centavos;
pedidos 3/20 não são recalculados com preços atuais. CSV não é dado em tempo real.
Fixturas públicas têm contagens menores **2/5/2/2/3/2**, sem registros de clientes
originais. As mesmas regras funcionam em ambos os modos.

O loader do PDF preserva páginas físicas, seções e relações de tabela; fragmentos
semânticos retornam excerto breve, seção, páginas, versão/hash e correspondência
lexical. Não há OCR para documentos digitalizados. Ranking depende das palavras
e da qualidade da extração; escore não é confiança jurídica nem garante cobertura
completa. Ausência de evidência é distinta de erro de leitura. Não há rota para o
manual, exportação integral ou índice público. Contatos divergentes e frete de
exatamente R$ 500 seguem como ambiguidades, sem inventar uma condição.

```bash
python scripts/evaluate_retrieval.py --output /tmp/emporio-retrieval.json
```

Recall@3 da Fase 04: 100% nas 20 perguntas com seções esperadas, mais seis casos
sem evidência. Foi conjunto de desenvolvimento, sem teste cego. Metodologia e
limites em [docs/retrieval.md](docs/retrieval.md); dados em
[docs/data_quality.md](docs/data_quality.md).

## Testes e avaliação integrada

```bash
python -m pytest -q
python -m pytest -q -m 'not local_data'
python -m ruff check .
python -m ruff format --check .
python -m pip check
python scripts/evaluate_agent.py --output /tmp/emporio-evaluation.json
```

O primeiro comando executa também os testes originais quando anexos estão presentes;
sem anexos, esses 35 casos são pulados. O segundo usa só testes públicos/sintéticos.
Testes assíncronos neste workspace Codex precisaram rodar fora do sandbox por uma
falha de encerramento de threads; não houve chamada externa de LLM.
Resultados finais e prova de ambiente limpo: [docs/final_audit.md](docs/final_audit.md).

Fase 09: **40 cenários/46 turnos** (8 catálogo, 6 preços, 8 políticas, 6 pedidos,
5 múltiplas etapas, 7 robustez). O roteiro existente concluiu **25/40 (62,5%)**;
não foi ajustado para melhorar a nota. Nomes de tools 36/46; argumentos 30/46;
controle direto 39/39; compliance 43/46; grounding automático 22/22 aplicáveis,
com cobertura limitada a dinheiro/estoque/fontes, sem equivalência semântica geral.
No manual local, Recall@3 do controle foi 100% em sete consultas, enquanto o
roteiro não selecionou busca documental (Recall do agente 0%). Esses resultados
não medem qualidade de um LLM real. Tokens/custo reais são N/A.

O avaliador retorna **1 para falhas medidas**, 2 para erro operacional e 3 para
modo real sem configuração. Pytest aprovado valida implementação/detecção de
falhas; não significa que todas as tarefas conversacionais passaram. Métricas,
latência mediana/p95 e erros por componente: [docs/evaluation.md](docs/evaluation.md).

## Cinco conversas executadas e identificadas

Todas são **simulações executadas** com LLM roteirizado e serviços reais sobre
fixtures sintéticas; nenhuma é apresentada como conversa autônoma de modelo real.

1. [Catálogo](examples/01_catalogo.md): nylon, preço e disponibilidade.
2. [Promoção e pagamento](examples/02_promocao_pagamento.md): duas tools, PIX não cumulativo, referência, 3x válido e 6x inválido; caso não trivial.
3. [Pedido protegido](examples/03_pedido_protegido.md): concessão de demonstração, histórico, ausência de rastreio e acesso alheio negado.
4. [Devolução](examples/04_devolucao.md): fontes sintéticas, 7/30/90 dias e pergunta sobre recebimento real.
5. [Fora do escopo](examples/05_fora_escopo.md): acessórios e injection bloqueados.

Mensagens, calls/resultados sanitizados, regras/fontes e interpretação constam
nos arquivos. [Manifesto](examples/manifest.json) registra execução e hashes.
Reprodução sem substituir evidência da entrega:

```bash
python scripts/generate_examples.py --output /tmp/emporio-exemplos
```

Este gerador seleciona intencionalmente as calls para demonstrar o backend.
Não é o provedor da CLI/API nem um resultado adicional da avaliação da Fase 09.
Os cinco cenários são validados antes da gravação, inclusive com `python -O`;
symlinks de saída são recusados e hard links não têm seu inode truncado. Cada
arquivo é substituído separadamente, com manifesto por último. Não há transação
de diretório diante de falha de disco; prefira saída nova e confira o manifesto.

## Segurança, limitações e uso de Codex

`.gitignore` exclui `.env`, chaves, fontes restritas, bancos, logs e caches.
Os CSVs incluem dados de clientes e o PDF se identifica como interno/restrito;
autorização de uso no desafio não comprova permissão de redistribuição.
Nenhuma autorização para publicar anexos foi documentada. Só fixtures sintéticas
foram preparadas para distribuição. Os anexos devem continuar locais.

```bash
python scripts/audit_release.py
```

Execute a auditoria na raiz de um repositório Git; ela não inicializa Git nem
altera o índice. A cópia limpa de testes não foi usada como prova de histórico.
Erros dos comandos Git interrompem a auditoria (código 2), sem aprovar ou substituir
o relatório anterior. Usuário SSH de transporte não é tratado como segredo;
userinfo HTTP exige revisão, e senha embutida é sinalizada sem exportar a URL.

A auditoria examina candidatos Git, padrões de segredos, tokens, referências aos
identificadores de clientes originais e regras de exclusão. Não imprime os valores
encontrados. É heurística e não substitui revisão humana, autorização dos titulares
ou auditoria completa de histórico. Ainda não existe histórico Git para auditar.
Blobs do índice são examinados também: limpar o arquivo local não oculta o que
já está staged. Symlinks, conflitos e tipos de índice não suportados exigem revisão.

Logs próprios usam listas permitidas e tag HMAC, sem texto/argumentos/dados de
cliente. Filtros de injection e ocultação de PII têm falsos positivos/negativos;
nomes, endereços e segredos livres podem escapar. Quem detém ID/token pode usar
a conversa. Sem autenticação real, multiworker, rate limit por usuário, operação
externa, dados em tempo real ou ação de compra/cancelamento/reembolso. As fontes
são snapshots e não há API de transportadora. Retenção do provedor precisa de revisão.

O **OpenAI Codex** foi usado em fases para inspecionar arquivos, implementar e
revisar código, escrever testes/gabaritos, executar comandos e organizar documentos.
O fluxo preservou originais e separou implementação de medições; mocks, falhas,
limites e falta de provedor real foram registrados. Não houve LLM-juiz nem revisão
humana independente alegada. Os testes não substituem revisão do candidato, que
precisa compreender, validar e assumir as decisões antes de enviar a entrega.

Com mais tempo: validar um modelo real com orçamento definido, avaliar perguntas
não usadas no desenvolvimento, revisar gabaritos/paráfrases com humano, aperfeiçoar
seleção de políticas e combinar tools, medir latência/tokens/custo reais e adicionar
identidade/controles de abuso antes de expor pedidos. Embeddings/distribuição só
com necessidade demonstrada. A licença de redistribuição do código não foi presumida.

## Entrega externa pendente

O enunciado pede GitHub público, histórico de progresso real, README e 3–5 conversas,
com ao menos um caso não trivial. Os arquivos locais estão preparados; o repositório
continua **sem commits e sem remoto**. Não há como reconstruir honestamente um
histórico progressivo após o fato; não foram criados commits retroativos.

O prazo exato está no e-mail do processo e não foi fornecido no workspace. Confirmá-lo
antes de qualquer alteração/publicação; após o prazo, não modificar o repositório.
Publicação, commit, push, link público e envio de e-mail dependem de instrução
explícita. O Codex não fez essas ações. Compare os entregáveis e riscos em
[docs/final_audit.md](docs/final_audit.md).

Revisão das alterações de entrega, correções e verificações posteriores:
[docs/phase10_review.md](docs/phase10_review.md).

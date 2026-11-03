# Interface web local

A interface foi adicionada por solicitação explícita após a Fase 12C. Reutiliza
FastAPI, sessões de visitante, orquestrador e serviços existentes. Não muda o
modelo, regras, autorização, dados, gabaritos ou configuração `.env`.

## Executar

Na pasta `emporio-ai-agent/`, com os dados e `.env` já configurados:

```bash
source .venv/bin/activate
python -m uvicorn app.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Abra **http://127.0.0.1:8000**. Não é necessário Node, npm ou build de frontend.
O modelo continua configurado no servidor. O modo indicado na tela vem da API;
`offline_demo` é apresentado como simulação, sem alegar inferência real.
Ao alterar modelo ou caminhos de dados no `.env`, reinicie o servidor para aplicar.

Uma sugestão preenche o campo; clique em enviar ou pressione Enter. Shift + Enter
cria outra linha. O botão **Nova conversa** limpa a tela e faz o próximo envio
criar uma sessão independente. Atualizar a página também inicia outro contexto.
As sessões anteriores do backend continuam sujeitas ao TTL existente, sem uma
nova rota de exclusão ou persistência. O modelo mantém somente o contexto recente.

Para testar: “Mostre o produto 103”, depois “E em 6x?”. Pergunte também sobre
devolução, PIX e horários. A primeira resposta pode demorar enquanto o modelo
local carrega. Pedidos privados continuam bloqueados para visitante.

O indicador “API disponível” confirma a aplicação configurada; `/health` não
chama o LLM. Falhas do Ollama são apresentadas quando a mensagem é enviada.
**Verificar conexão** consulta novamente o estado da API. Sessão expirada exige
nova conversa; não há reenvio automático de mensagens.

## O que foi implementado

- Página em `GET /`, com sugestões, histórico, envio por teclado, carregamento,
  mensagens de erro e estilos para desktop/mobile.
- Painel de consultas reais da última resposta, com nomes amigáveis, estado e
  tempo total medido pelo cliente, incluindo criação de sessão quando necessária.
- `POST /chat` ganhou o campo aditivo `tools`: nome permitido, status e código de
  erro. Não expõe argumentos, call IDs, payloads brutos ou autorização.
- Três assets locais em `/assets/chat.css`, `/assets/chat.js` e a página `/`.
  Não há rota genérica de arquivos, CDN, analytics, CORS ou dependência nova.
- A UI não mostra nem recebe chaves do provedor. Token/ID da conversa ficam apenas
  na memória JavaScript, sem armazenamento persistente, cookies ou parâmetros de URL.
- Conteúdo do usuário e do agente é inserido por `textContent`. Apenas o formato
  restrito de tabela de parcelas é montado com elementos DOM `table`, `thead`,
  `tbody`, `th` e `td`, com células como texto. HTML, links e demais Markdown
  permanecem literais. CSP restringe recursos/conexões à mesma origem e bloqueia framing.
- Assets incluídos no wheel via `tool.setuptools.package-data`.

Arquivos: `app/ui.py`, `app/web/{index.html,chat.css,chat.js}`, `app/api.py`,
`app/api_schemas.py`, `pyproject.toml`, testes de API/UI e documentação.

## Verificações executadas

| Verificação | Resultado observado |
|---|---|
| TestClient API + UI, fontes sintéticas e provedor offline | 43 passed in 1.97s |
| Suíte pytest completa, sem chamadas a LLM | 495 passed in 22.57s |
| Ruff | All checks passed; 118 files already formatted |
| JavaScript, HTTP e DOM simulados | 12 testes aprovados no runtime Node da ferramenta |
| API real local, Qwen 3.5 9B | Produto 103: HTTP 200; seguimento 6x: HTTP 200; pedido 1: HTTP 403 |
| Wheel | Quatro arquivos de UI presentes no pacote, incluindo os três assets |
| Dependências | pip check: No broken requirements found |

Os testes JavaScript verificam sessão, isolamento, reset, envio duplicado,
expiração, modo simulado, validação de entrada, erros, texto não interpretado
como HTML e painel de consultas. Uma resposta de sessão `null` inicialmente
produzia TypeError; a regressão comprovou a falha e a validação foi corrigida.

Na prova HTTP real foram observados: instrumento sintético 103 por R$ 960,00,
consulta de oferta em 6x de R$ 160,00 com referência mantida e negativa do pedido
sem divulgar valor/rastreamento. Tempos individuais: 29.498,53 ms, 5.359,22 ms e
1.202,50 ms. São três observações, não um benchmark; a primeira inclui possível
carga inicial do modelo. Dados e tokens reais de clientes não foram usados.

[Evidência HTTP e verificações](chat_ui_validation.json);
[testes JavaScript](chat_ui_js_tests.json).

Comandos de reprodução:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

Se houver Node moderno instalado, os testes opcionais do cliente podem ser
executados com `node tests/web/chat.test.mjs`. Neste ambiente, Node não estava
disponível no terminal; os testes foram executados pelo Node REPL da ferramenta.
O build sem isolamento no venv inicialmente falhou por ausência do backend
`setuptools`; o wheel foi construído sem downloads com o Python do sistema, que
já possui esse backend. Isso não substitui uma nova instalação limpa do projeto.

## Limites

Não foi possível fazer QA visual em navegador: o inventário de browsers estava
vazio e a tentativa de abrir o in-app browser retornou indisponibilidade. O Node
REPL também não alcançou o servidor local por HTTP; a prova real foi feita por
Python no host. Logo, os testes de DOM simulados e HTTP não são apresentados
como uma conversa ponta a ponta em navegador. A responsividade foi implementada,
mas não foi inspecionada visualmente nesta sessão.

A UI não corrige as falhas de filtros/retrieval registradas na Fase 12C. Não há
autenticação real, concessão de pedidos, upload de dados/documentos, alteração de
modelo no navegador ou publicação externa. Permanecem os limites de sessão,
um worker, fontes snapshot e capacidade descritos no README.

Nenhum commit, push, publicação ou download de modelo foi realizado.

## Atualização: tabela de parcelas e busca de página única — 02/11/2026

A oferta no cartão passou a apresentar uma tabela de duas colunas: parcelas e
valor de cada parcela. Todas as opções de `eligible_installments` são exibidas,
mesmo quando `selected_plan` contém 1x ou outro plano. O máximo apresentado vem
dos planos calculados pelo serviço; nenhuma condição é criada no renderer.
O plano consultado é resumido agrupando parcelas iguais, sem repetir cada valor.
Se houver ajuste de centavos, a tabela informa o intervalo real e uma observação
explica que o total permanece exato. A API/CLI recebe a tabela como texto Markdown;
o navegador monta apenas esse formato com DOM seguro, sem biblioteca externa.

Buscas que cabem na primeira página não mostram mais “Mostrando 1 a 1 de 1”
nem “última página”. Resultados com mais páginas mantêm a continuação existente,
inclusive quando a última página tem somente um item. A busca de um único produto
usa um título no singular. A saudação e os demais contratos permaneceram como
estavam após a reversão anterior.

O bloco da Crafter apareceu porque o modelo consultou `search_products` para
identificar o produto e incluiu essa evidência no plano final, junto com a oferta.
O rodapé era acrescentado automaticamente pelo renderer. Na execução real abaixo,
o modelo repetiu esse encadeamento: o produto continua identificado, agora sem o
rodapé de página única. O snapshot é a cópia importada dos arquivos do desafio;
isso não indica consulta a estoque em tempo real.

Verificações executadas:

| Verificação | Resultado |
|---|---|
| Testes focados de parcelas, paginação e UI | 25 passed in 1.25s |
| Suíte Python completa, sem inferência real | 526 passed in 17.51s, nenhum skip |
| JavaScript, HTTP e DOM simulados no Node REPL | 16 testes aprovados |
| Ruff | All checks passed! |
| `compileall -q app` e `git diff --check` | Exit 0 |
| HTTP real, pergunta pelo nome da Crafter | 200; catálogo + ofertas; 39.980,81 ms |
| HTTP real, seguimento “E em 12x?” | 200; ofertas; 6.815,65 ms |

Modelo real mantido: `qwen3.5:9b`, Ollama local, temperatura 0, thinking `none`,
finalização estruturada ativa. Os dois turnos entregaram todas as 12 linhas, com
12x de R$ 383,25, sem avisos de paginação. A primeira resposta teve três rodadas;
o seguimento, duas. São medições pontuais, sem benchmark estatístico. Contagem de
tokens não é exposta pelo contrato HTTP e não foi estimada.

A segurança JavaScript foi verificada com HTML malicioso como texto de células,
tabelas inválidas, cabeçalhos semânticos, preservação das 12 linhas e proibição de
renderizar a mensagem do usuário como tabela. Esses testes usam DOM/HTTP simulados;
não substituem inspeção visual. O inventário de browsers retornou vazio e a
tentativa de abrir o in-app browser falhou com `Browser is not available: iab`.

Comandos Python executados:

```bash
.venv/bin/python -m pytest tests/unit/test_payment_table.py tests/integration/test_pagination.py tests/integration/test_chat_ui.py -q --tb=short
.venv/bin/python -m pytest -q --tb=short
.venv/bin/ruff check .
.venv/bin/python -m compileall -q app
git diff --check
```

Os 16 testes JavaScript podem ser reproduzidos com `node tests/web/chat.test.mjs`
onde Node estiver instalado; nesta execução foi utilizado o Node REPL da ferramenta.
Os testes assíncronos e as chamadas localhost precisaram rodar fora do isolamento
restritivo. Nenhum serviço externo foi consultado.

Arquivos alterados: `app/agent/rendering.py`, `app/web/chat.js`,
`app/web/chat.css`, `tests/web/chat.test.mjs`, `README.md` e esta documentação.
Adicionados sete testes em `tests/unit/test_payment_table.py`. Serviços de preços,
contratos de ferramentas/API e gabaritos não foram modificados. Hashes dos CSVs,
PDF, banco do catálogo e gabaritos de 40/18 casos foram conferidos antes/depois.
Não houve commit, push, publicação ou mudança no `.env`.

[Evidência sanitizada desta atualização](installment_table_validation.json).
Traces completos de catálogo, cópias anteriores e hashes ficam localmente em
`data/derived/installment_table/`, ignorado pelo Git. O servidor foi reiniciado;
recarregar a página e iniciar nova conversa carrega a apresentação atual.

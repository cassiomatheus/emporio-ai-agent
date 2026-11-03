# Fase 07 — Sessões e segurança

Implementação Python em memória, sem HTTP, UI, autenticação real ou dependência
nova. `ConversationService` envolve o orquestrador da Fase 06. A fronteira de
confiança é o backend: mensagens e tools não criam clientes, concessões ou sessões.

## Uso e autorização de demonstração

Prepare uma base separada com as fixtures redistribuíveis:

```bash
python scripts/ingest_data.py --raw-dir data/samples --database data/demo.sqlite3
python -m pytest tests/unit/test_session_security.py tests/integration/test_sessions.py -q
```

A ingestão substitui o destino; use esse caminho exclusivo para a demonstração.
Não substitua `data/emporio.sqlite3`, que contém o snapshot original.

O backend monta `ConversationService.for_demo(provider, catalog_database=...,
demo_database=...)`. `provider` implementa o protocolo existente; os testes
injetam um provedor roteirizado, sem rede. O catálogo/preços podem usar o banco
original; pedidos usam somente o banco sintético. A fábrica compara todas as
tabelas da base demonstrativa com `data/samples`, inclusive campos pessoais,
valores e relacionamentos. Divergências impedem a concessão. A validação é
repetida antes e depois de cada conversa, somente com leituras transacionais.

Exemplo de integração **interna**, chamado pelo backend com um provedor já montado:

```python
from pathlib import Path

from app.agent.models import AgentRequest
from app.agent.sessions import ConversationService, SessionLimits
from app.config import Settings


async def consultar_pedido_demo(provider):
    backend = ConversationService.for_demo(
        provider,
        catalog_database=Path("data/demo.sqlite3"),
        demo_database=Path("data/demo.sqlite3"),
        session_limits=SessionLimits.from_settings(Settings()),
    )
    # Escolha administrativa fixa; nunca copiar um ID vindo do usuário/LLM.
    cliente = backend.register_demo_client(customer_id=1)
    sessao = backend.create_session(cliente)
    try:
        return await backend.chat(cliente, sessao, AgentRequest(message="Consulte pedido 1"))
    finally:
        backend.revoke_client(cliente)
```

O handle `BackendClient` é uma capacidade opaca em Python, conferida por identidade
de objeto registrado; copiar/conhecer o ID de sessão ou criar outro handle não
libera acesso. Não é prova da identidade de uma pessoa, credencial HTTP, login
ou autorização para usar pedidos originais. `register_demo_client()` sem ID
cria visitante sem acesso a pedidos. Apenas os clientes 1/2 das fixtures podem
receber concessão demonstrativa pela fábrica. Não expor esse método administrativo
como parâmetro livre de futura API. O construtor de baixo nível não permite
conceder cliente sem a base demonstrativa verificada.

`AgentRequest` aceita apenas `message`; as seis tools mantêm seus contratos.
`customer_id`, contexto, sessão e SQL não são parâmetros autorizantes do modelo.
`OrderAccessContext` é injetado a partir da concessão imutável guardada na sessão.
O serviço e o SQL continuam conferindo o proprietário do pedido. Pedido alheio e
inexistente retornam `forbidden`; sessão alheia, desconhecida ou expirada retorna
o mesmo `SessionAccessDenied`. Sem rastreamento/previsão, informar ausência.

## Histórico, referências e limites

Padrões configuráveis por `.env.example`/`Settings` e `SessionLimits.from_settings`:

| Limite | Padrão |
|---|---:|
| Pares completos de usuário/resposta por sessão | 6 |
| Caracteres somados do histórico | 12.000 |
| Inatividade para expiração | 1.800 s |
| Sessões por instância | 100 |
| Clientes registrados por instância | 100 |
| Espera pelo lock da sessão | 30 s |

Remover os pares mais antigos inteiros, sem truncar valores ou afirmações. Um par
maior que o orçamento é descartado por inteiro. Há no máximo 20 IDs de referência;
apenas produtos de tools bem-sucedidas **selecionadas na resposta final** podem
atualizá-los. Resultados múltiplos exigem esclarecer o modelo; busca vazia remove
referência antiga. Pedidos e IDs declarados no texto não criam referência de produto.

“Esse violão”/“E em 6x?” usa referência única verificada; sem ela, a resposta
controlada pede o instrumento antes de chamar o modelo. Um ID explícito novo
tem precedência; “esse pedido” não aciona referência de produto. O backend fornece
ao LLM somente o ID numérico confiável e bloqueia ferramentas de produto que
tentem trocá-lo no seguimento. Busca ampla nesse contexto deve ser reformulada
como uma nova pergunta. Resolução é conservadora, por padrões em português,
sem resolver genericamente pronomes, comparações, nomes ambíguos ou referências
a pedidos.

Histórico é contexto não confiável, nunca evidência atual. Preço, estoque e parcelas
exigem consulta nova; a lista de evidências é recriada a cada `run`. Um call_id do
turno anterior não fundamenta a resposta seguinte. Falhas mantêm a possibilidade
de tentar novamente pelo ID, mas não fornecem preço antigo como fallback.
Para devolução sem recebimento real, o plano `receipt_date` pede a data e as
condições do caso; não calcula elegibilidade por data do pedido/previsão.

Um lock por sessão serializa turnos; sessões diferentes progridem independentemente.
Expiração usa relógio monotônico, verificada nas operações; não há tarefa periódica.
Encerramento, revogação e expiração limpam histórico/referências. Revogação,
fechamento ou expiração durante uma chamada também impedem entregar/guardar a
resposta tardia. Isso não desfaz dados já enviados ao provedor antes da revogação.
Clientes permanecem registrados até revogação ou fim do processo, dentro da quota.

## Logs, falhas e prompt injection

O logger `emporio.audit` emite mensagem fixa `emporio_event` com `record.audit`:
evento, tag de sessão, status e, quando aplicável, tool/erro de listas permitidas.
A tag é HMAC com sal aleatório por processo; não expor ID bruto, cliente/pedido,
argumentos, resultado, conversa, fonte integral, nome, contato, chave ou traceback.
Habilite INFO no handler da aplicação para coletar esses eventos. Não há arquivo
de log, telemetria externa ou configuração global de handlers nesta fase.
Falha do handler é descartada sem imprimir fallback sensível.

E-mails, telefones/CPF/cartões óbvios, credenciais rotuladas e chaves com prefixo
reconhecido são removidos antes de enviar ao modelo e de guardar histórico.
Prompts bloqueados são substituídos por marcador no histórico. `repr` da memória,
contexto e requisição não contém a conversa. Erros inesperados usam texto fixo;
as tools continuam retornando falhas tipadas sem rastros de exceção.

Padrões auxiliares detectam instruções diretas/indiretas para ignorar regras,
revelar credenciais/prompt, executar SQL e simular privilégio administrativo.
Entradas reconhecidas não chamam LLM/tools; resultados suspeitos das tools são
substituídos por `service_unavailable` antes de serem enviados ao modelo ou
renderizados. Acessórios conhecidos recebem redirecionamento controlado; outros
assuntos podem ser classificados pelo plano limitado do LLM.

Esses padrões **não são uma defesa completa contra prompt injection**. As barreiras
centrais continuam sendo seis tools fixas, validação estrita, consultas somente
leitura, autorização externa ao LLM e renderização determinística baseada em
evidências desta execução. Mesmo um provedor que ignore o prompt não ganha
SQL livre, identidade de outro cliente ou texto factual arbitrário.

## Evidência e riscos residuais

Execução final em 31/10/2026, Python 3.14.6, pytest 9.2.0 e Ruff 0.17.3:

| Comando/verificação | Resultado observado |
|---|---|
| `.venv/bin/python -m pytest -q` | **342 passed in 5.07s** |
| `.venv/bin/python -m pytest -q -m 'not local_data'` | **307 passed, 35 deselected in 3.78s** |
| `.venv/bin/ruff check .` | **All checks passed!** |
| `.venv/bin/ruff format --check .` | **74 files already formatted** |
| Imports de sessões, memória, auditoria e validação demo | **imports: OK** |
| `.venv/bin/python -m pip check` | **No broken requirements found.** |

Os 60 casos novos passaram na suíte completa; os 282 anteriores foram preservados.
A validação inicial encontrou um telefone com parênteses/espaços não ocultado,
corrigido no filtro. Dois ajustes de teste corrigiram a simulação de falha SQL
(respeitando FKs) e a expectativa do erro para campo extra em uma tool. Resultados
acima são posteriores às correções. Os testes assíncronos foram executados fora
do sandbox devido ao problema de encerramento do executor já observado na Fase 06;
isso não envolveu chamadas externas.

Cobertura observada: duas sessões/clientes independentes; duas sessões do mesmo
cliente; referência única/ambígua/vazia; preço alterado entre turnos; ID trocado
pelo modelo; evidência de turno anterior recusada; pedido próprio sem rastreio;
pedido alheio/inexistente/visitante; handle forjado e ID de sessão conhecido;
base demo divergente; histórico limitado; expiração/cotas/fechamento/revogação;
revogação/expiração/fechamento durante await; serialização e progresso independente;
timeout de lock/cancelamento; falha de tool/orquestrador; logs/redação; injection
direta/indireta; modelo tentando SQL/identidade; acessórios, fora de escopo e
devolução sem data de recebimento real.

Testes novos usam LLM roteirizado/mocks, SQLite temporário e fixtures sintéticas;
não representam avaliação de um modelo real nem medição de resistência geral
a ataques. Não houve chamada real ao provedor nesta fase.

Arquivos novos: `app/agent/{audit,demo,memory,security,sessions}.py`,
`tests/unit/test_session_security.py`, `tests/integration/test_sessions.py` e
este relatório. Alterados: `.env.example`, `README.md`, `app/config.py`,
`app/agent/{__init__,models,orchestrator,prompts,rendering}.py` e
`docs/decisions.md` (DEC-28 a DEC-31). Nenhuma dependência foi acrescentada.
O repositório já estava sem commits e com arquivos não rastreados; a revisão de
escopo usou o inventário/hashes anterior à fase, sem criar commit ou alterar índice.
Dados locais, `.env`, guia, schema, contratos das tools, lock e testes anteriores
permaneceram inalterados.

Riscos/limitações:

- Sem autenticação real, persistência, múltiplos processos ou sincronização entre
  threads. Uma instância deve pertencer a um único event loop/backend confiável.
  Não publicar como serviço de pedidos reais sem uma fronteira de identidade.
- Quem controla o código/backend ou furta seu handle pode usar a concessão.
  A verificação da base demo não protege contra alterações locais maliciosas
  no intervalo entre verificação e consulta; os snapshots devem ser controlados
  pelo backend. Validação novamente na saída impede entregar a base divergente
  nos cenários testados, sem alegar proteção contra troca seguida de restauração.
- Redação por padrões não remove todo nome, endereço, segredo sem rótulo ou
  conteúdo pessoal livre. Conteúdo residual pode chegar ao provedor configurado
  e à memória efêmera. Não enviar dados sensíveis; revisar retenção do provedor
  e configuração de logs externos/SDK antes de disponibilizar o serviço.
- Padrões de referência, escopo e injection têm falsos positivos/negativos;
  a intenção e a relevância da seleção ainda dependem do modelo. O texto final
  controlado evita decisões livres de devolução/garantia, mas não comprova que
  todo caso foi entendido. Não foi feito benchmark adversarial com LLM real.
- Histórico expirado é limpo na próxima operação; não há garantia de apagamento
  físico da memória Python. Há cotas globais, sem controle de abuso por usuário.
- Timeout descarta a espera/resultado de tool síncrona, sem matar a thread que já
  executa. Aplicam-se os limites documentados na Fase 06.

Próxima fase autorizável: Fase 08, CLI/FastAPI reutilizando este backend. Nenhuma
rota, UI, publicação, commit ou autenticação real foi implementada nesta fase.

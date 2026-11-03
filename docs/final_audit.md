# Auditoria final — Fase 10

**Adendo:** os resultados numéricos desta página registram a execução inicial da
Fase 10. Correções de segurança/reprodução e a decisão atual estão em
[phase10_review.md](phase10_review.md). O relatório JSON de publicação vinculado
é atualizado por novas varreduras; os 126 candidatos descritos abaixo pertencem
à varredura inicial. A evidência limpa inicial é preservada como snapshot.

**Conclusão: preparação técnica e documental local concluída; entrega externa não liberada.**
Os arquivos foram preparados e verificados. Permanecem pendências materiais de
modelo real, histórico Git, publicação, prazo e aprovação do candidato. Não se
afirma que todos os P0 ou os entregáveis externos do desafio estejam concluídos.

Auditoria realizada em 01/11/2026. Evidências: [ambiente limpo](clean_environment.json),
[varredura de publicação](publication_audit.json), [avaliação](evaluation.md) e
[manifesto das conversas](../examples/manifest.json). Nenhum commit, stage, push,
publicação ou envio de e-mail foi realizado.

## Fonte conferida e escopo

O enunciado original, `desafio_tecnico_ai_eng_artefact.pdf`, foi lido e conferido
visualmente nas três páginas, fora do repositório. Pág. 1 define Python, persona,
consultas a dados/políticas e fora do escopo; pág. 2 exige GitHub público com
progresso real, README e 3–5 conversas com situação não trivial; pág. 3 remete o
prazo ao e-mail do processo e orienta documentar interpretações razoáveis.
O PDF não fixa framework/provedor nem exige UI elaborada.

O manual local tem oito páginas e identifica uso interno/restrito. Não foi
localizada evidência de autorização para redistribuir anexos no workspace; isso
é **permissão não comprovada**, não uma declaração jurídica sobre titularidade.
O prazo exato do e-mail também não está disponível. Uso local no desafio não foi
interpretado como autorização de publicação ou envio do manual a um provedor.

Escopo desta fase: README final, decisões de entrega, cinco conversas executadas,
auditoria dos candidatos e reprodução limpa. Serviços, orquestrador, prompts,
retrieval, API, CLI e métricas históricas não foram ajustados para melhorar o placar.

## Matriz dos entregáveis

| Requisito do enunciado | Estado verificado | Evidência / pendência |
|---|---|---|
| Python e interface de texto | Aprovado tecnicamente | CLI e FastAPI; execução instalada e HTTP local verificados |
| Persona em português e respostas fundamentadas | Implementado; validação real parcial | Prompt/planos controlados e testes; qualidade de LLM real ainda não medida |
| Consulta de catálogo/preços/estoque/ofertas | Aprovado no backend; seleção real pendente | Serviços Decimal/status, tests e exemplos; roteiro offline tem falhas de filtro/modalidade |
| Consulta de políticas | Aprovado no retrieval; conversa real pendente | PDF/seções/tabelas e Recall@3 de controle; roteiro da CLI não seleciona busca documental |
| Pedidos protegidos | Aprovado para demonstração | Concessão sintética do backend; API é visitante e recusa pedidos; sem autenticação real |
| Fora do escopo e falhas | Aprovado nos casos testados | Acessórios/injection/timeout/ausência; conjunto não cobre todo ataque/assunto |
| README de execução e escolhas | Preparado e verificado | Início rápido, provedor/modelo, arquitetura, regras, retrieval, testes e limites |
| 3–5 conversas variadas | Aprovado como simulação identificada | Cinco Markdown, dez turnos; mensagens/calls/resultados capturados |
| Ao menos um caso não trivial | Aprovado como simulação | Promoção não cumulativa + duas tools + referência + parcelas; devolução com fonte/data |
| Modelo/provedor | Parcial | Adaptador OpenAI Responses configurável; não há modelo real selecionado/testado |
| GitHub público com histórico real | Pendente material | Zero commits, zero arquivos rastreados, nenhum remoto/link público |
| Entrega do link por e-mail | Pendente externa | Nenhum envio autorizado/realizado; não há link público |
| Prazo e congelamento da entrega | Não confirmado | Data/hora dependem do e-mail, ausente no workspace; não alterar após o prazo |
| Uso de assistente de código declarado | Aprovado documentalmente | README descreve uso de OpenAI Codex e limites da validação |

Aprovação técnica nesta tabela descreve somente verificações locais. Não é
assinatura humana, consentimento do titular, aprovação do avaliador ou autorização
para divulgar dados. O candidato precisa revisar e assumir o trabalho antes do envio.

## Cinco conversas e sua procedência

Todas são **simulações executadas**, sem LLM/API real. `ExampleProvider` escolhe
as calls do roteiro; tools, SQLite, autorização e cálculos são executados de fato
sobre `data/samples` e PDF sintético v0.1. Não se confundem com o roteiro da CLI
nem com seleção autônoma. Os exemplos curados não alteram os 25/40 da Fase 09.

| Arquivo | O que foi observado |
|---|---|
| [01_catalogo.md](../examples/01_catalogo.md) | Nylon ativo em estoque; fixture 102 a R$ 250,00 |
| [02_promocao_pagamento.md](../examples/02_promocao_pagamento.md) | R$ 359,00 → R$ 323,10 com 10%, sem PIX adicional; 3x107,70 válido; 6x recusado |
| [03_pedido_protegido.md](../examples/03_pedido_protegido.md) | Perfil sintético 1, total histórico R$ 999,90, ausência de rastreio; pedido 2 negado |
| [04_devolucao.md](../examples/04_devolucao.md) | Seções 4.1/4.2/8.1 sintéticas; 7 dias do recebimento, troca 30 da compra e garantia 90 do recebimento; pergunta da data real |
| [05_fora_escopo.md](../examples/05_fora_escopo.md) | Acessórios redirecionados e injection bloqueada; zero chamadas ao modelo/tools |

Manifesto: 10 turnos,
9 chamadas de tools e
15 chamadas ao **mock**;
nenhuma chamada a provedor real. Os cinco hashes de Markdown foram conferidos.
As respostas foram capturadas em execução, não escritas como saídas reais inventadas.
Falhas como `invalid_installments`/`forbidden` podem resultar em encaminhamento
genérico; essa limitação aparece sem reescrever o texto do assistente.

## Auditoria de segredos, dados e redistribuição

`scripts/audit_release.py` inspecionou **126 candidatos Git**
(rastreados + não rastreados não ignorados), com **125 arquivos de texto
varridos** e o próprio relatório excluído para evitar autorreferência. Resultado:
**zero achados nos detectores executados**. `.env.example` foi conferido sem
credencial preenchida. Foram testados padrões de chave privada, chaves comuns de
provedores/GitHub/AWS, token de sessão e valores secretos no exemplo de ambiente.

As correspondências contra e-mails, nomes completos e telefones dos clientes CSV
originais foram feitas localmente; valores/fingerprints não são exportados.
Não houve correspondência nos candidatos. O scanner relata somente arquivo,
linha e categoria. A primeira varredura confundiu `MAX_OUTPUT_TOKENS=1200` com
credencial; o detector foi corrigido e ganhou teste, sem alterar o ambiente.
Não foi encontrado segredo real que precisasse ser removido nesta execução.

As sete sondas de exclusão passaram: `.env`, `.env.production`, `token.key`, CSV
em `data/raw`, PDF interno, banco SQLite e log. Arquivos já rastreados não seriam
protegidos só pelo ignore; por isso também integram o inventário. Hoje há zero
arquivos rastreados e nenhum histórico de commits para auditar/reescrever.
Não houve tentativa de publicar nem autorização inferida pelo scanner.

| Material | Tratamento de entrega |
|---|---|
| Seis CSVs originais e PDF interno | Mantidos locais/ignorados; redistribuição não comprovada |
| PDF do enunciado | Fora do repositório; não copiado para o conjunto público |
| `.env`, tokens, bancos, caches e logs | Não copiados ao ambiente público; regras de exclusão verificadas |
| `data/samples` | Fixtures sintéticas, e-mails `.invalid`, sem registros de clientes originais |
| Cinco conversas | Só dados/fontes sintéticos; sem token/ID de sessão ou PII original |
| Relatórios originais | Agregados/metadados/gabaritos; sem texto integral do manual ou linhas de clientes |
| Código e dependências | Nenhuma licença permissiva adicionada por suposição; titularidade/licenças exigem decisão do responsável |

A varredura é heurística, não DLP completo, pentest, análise jurídica ou garantia
de ausência de qualquer segredo. Nomes/endereços/segredos livres e variantes
podem escapar. Permissões fora do workspace e prazo não são verificáveis pelo
scanner. Antes de um envio, revisar novamente o diff e a seleção de arquivos.

## Ambiente limpo realmente executado

Criou-se uma cópia temporária de **125 candidatos então presentes**,
sem `.git`, `.env` privado, `data/raw` ou bancos. Não foi um clone remoto: não há
repositório remoto. Em seguida foi criado um venv novo, com acesso a pacotes de
sistema desabilitado e pytest ausente antes da instalação. Variáveis EMPORIO/OPENAI
herdadas e PYTHONPATH/PYTHONHOME/VIRTUAL_ENV foram removidas dos subprocessos.
O `.env` de teste veio apenas do exemplo público, sem credenciais.

Instalação efetivamente executada:

```bash
python3 -m venv .venv
python -m pip install -c requirements-dev.lock -e '.[dev]'
```

Build isolado/instalação terminou com código 0. As versões instaladas coincidem
com **todo o lock**, sem depender do venv original. Python 3.14.6,
SQLite 3.53.2; import de `app` comprovadamente veio da cópia.
Os **94 arquivos executáveis/fixtures/configuração** conferidos
continuam idênticos aos do workspace final. O fechamento dos relatórios e suas
metainformações foi acrescentado depois; não houve alteração executável posterior.

| Verificação | Resultado real |
|---|---|
| Suite local com originais | **417 passed in 18.84s** |
| Suite na cópia limpa sem originais | **382 passed, 35 skipped in 14.25s** |
| Ruff lint/formato | Aprovados; 102 arquivos já formatados |
| `pip check` e correspondência com lock | Aprovados; `No broken requirements found.` |
| Smoke e origem do pacote | Aprovados; execução instalada preservada |
| Duas ingestões sintéticas | Mesmas contagens 2/5/2/2/3/2, sem duplicar |
| CLI mensagem e conversa/PIX | Código 0; R$ 250,00 e R$ 237,50 observados |
| CLI pedido demonstrativo | Código 0; R$ 999,90 e ausência de rastreamento |
| Uvicorn + HTTP loopback real | GET health 200; POST sessions 201; POST chat 200 |
| Cinco exemplos regenerados fora do repo | Código 0; cinco arquivos validados |
| Avaliador em cópia limpa | Código 1 esperado; 40 cenários e 25/40 tarefas |

O servidor HTTP foi iniciado só em 127.0.0.1/porta temporária e encerrado ao final.
Ele usou `offline_scripted`, **não** um LLM real. Tokens não foram registrados.
Não houve serviço deixado exposto ou publicação. A suite limpa verifica também
os endpoints com TestClient. O código 1 do avaliador representa falhas medidas
do sujeito e não erro de instalação; `all_checks_passed` da reprodução compara
cada código ao esperado, sem declarar todas as tarefas do agente aprovadas.

Os dez testes novos verificam detectores sem exportar valores, separação entre
limite de tokens e credencial, matching de PII/token e bloqueio de caminhos
restritos mesmo quando rastreados. Permanecem incluídos os 407 testes anteriores.
Como nas fases anteriores, testes com asyncio/threads rodaram fora do sandbox
do Codex. Isso não exigiu chamada externa de LLM ou compartilhamento de anexos.

## Modelo, avaliação e limites funcionais

Adaptador: SDK OpenAI 3.42.0 / Responses API; opções `openai`/`openai_compatible`
com endpoint Responses. Nenhum modelo real foi escolhido/testado sem evidência
de acesso, orçamento e credencial. O modo real permaneceu `not_run`; tokens/custo
reais são N/A. A integração tem testes de SDK com transporte simulado, sem
qualificação de qualidade/latência/custo de modelo real.

A Fase 09 preserva 25/40 cenários, tools 36/46, argumentos 30/46 e controles 39/39.
Grounding automático 22/22 tem escopo de dinheiro/estoque/seções; não é equivalência
semântica geral. Compliance 43/46 inclui três filtros de catálogo desrespeitados.
O roteiro não consulta políticas (Recall do agente 0%); o controle recupera 100%
das seções em sete consultas no manual local. Não alterar essas evidências nem
usar os exemplos curados para aparentar precisão de LLM que não foi medida.

Riscos residuais: dataset pequeno/de desenvolvimento, gabaritos estritos, ausência
de revisão humana independente, palavras/PII não detectadas, injection não esgotada,
token transferível e memória por processo, sem autenticação real/rate limit por
usuário. API não libera pedidos. Fontes são snapshots, sem compras, reembolsos,
transportadora ou dados ao vivo. Timeout não mata thread síncrona em execução.
Antes de um LLM externo, rever permissões e retenção do fornecedor; `store=False`
não comprova por si só toda a retenção externa.

## Aprovações técnicas e pendências de liberação

**Aprovados localmente:** documentação de execução/decisões, cinco simulações
executadas, testes/lint/instalação isolada, CLI/API sintéticas, exclusões e
varredura sem achados, preservação dos originais. Essa aprovação é a constatação
das verificações feitas pelo Codex, sem alegar aceite humano ou do desafio.

**Pendências materiais antes de apresentar entrega como completa:**

1. Candidato revisar e compreender implementação, simulações e falhas; validar um
   modelo real com orçamento, credencial e autorização de uso dos dados.
2. Confirmar data/hora do e-mail e se ainda é permitido alterar/enviar o repo.
   A revisão da especificação em 31/10/2026 não é prazo de entrega comprovado.
3. Resolver GitHub público e falta de histórico: zero commits e nenhum remoto/link.
   Não fabricar histórico retroativo; um commit atual futuro não comprova etapas
   que não foram registradas. Reportar essa limitação honestamente.
4. Confirmar permissões/licença/titularidade para qualquer material que venha a ser
   redistribuído. Até lá, manter anexos excluídos e fornecer caminho local/fixtures.
5. Obter instrução explícita para commit, publicação/push e envio do link. Nenhuma
   dessas ações foi autorizada ou executada nesta fase. Após o prazo, congelar o repo.

## Comandos de reprodução e revisão

Na raiz do projeto, com o venv ativado:

```bash
python -m pip install -c requirements-dev.lock -e '.[dev]'
python scripts/ingest_data.py --raw-dir data/samples --database data/demo.sqlite3
python -m app.cli --offline-demo --message 'Mostre o produto 102'
python -m app.cli --offline-demo
python -m app.cli --offline-demo --demo-order --message 'Consulte pedido 1'
EMPORIO_CHAT_MODE=offline_demo python -m uvicorn app.api:create_app --factory \
  --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
python scripts/generate_examples.py --output /tmp/emporio-exemplos
python scripts/evaluate_agent.py --output /tmp/emporio-evaluation.json
python scripts/audit_release.py
```

`audit_release.py` exige repositório Git e só lê seu estado; não inicializa Git,
cria commit, altera índice ou transmite dados. Ele grava apenas o relatório JSON.
Mantenha os resultados da entrega; para nova medição use saída temporária.
Os comandos de servidor são interativos: encerrar antes de executar os seguintes.
As linhas do JSON de ambiente são descrições de argv, não comandos shell prontos;
use os exemplos com aspas acima. Logs brutos ficaram em diretório temporário,
fora dos candidatos; relatório não exporta tokens, credenciais ou fingerprints.

## Arquivos da fase e próximo passo

Alterados: `README.md`, `data/README.md`, `docs/decisions.md` (DEC-37/38/39).
Novos: cinco Markdown e manifesto em `examples/`, `scripts/generate_examples.py`,
`scripts/audit_release.py`, `tests/unit/test_release_audit.py`, este relatório,
`docs/publication_audit.json` e `docs/clean_environment.json`. Sem dependências novas
ou mudanças no código de produção. O inventário/hashes de antes da fase foi
usado para revisar o escopo, pois ainda não existe diff contra HEAD.
Na conferência final, 101 arquivos anteriores protegidos e nove originais externos
mantiveram os hashes. Links locais e hashes dos cinco exemplos foram validados.

Próximo passo é revisão do candidato e resolução das pendências acima, não uma
publicação automática. Preparação local concluída; liberação externa pendente.

# Validação final — Fase 11

Data: **01/11/2026**. Revisão técnica executada pelo Codex a pedido do candidato;
não representa aceite humano independente nem aceite da Artefact.

**Parecer: NO-GO para entrega externa completa.** A validação local está aprovada,
mas o agente ainda não foi testado com LLM real e faltam repositório público e
histórico de commits. Prazo, autorização de publicação e envio permanecem externos
a esta validação. Não foi realizado commit, push, publicação ou envio.

Evidência estruturada desta execução: [final_readiness_evidence.json](final_readiness_evidence.json).
Referências examinadas: [AGENTS.md](../AGENTS.md), [README](../README.md),
[revisão da Fase 10](phase10_review.md), seu
[registro de validação](phase10_review_validation.json) e o enunciado PDF original
local, de três páginas. Nenhum componente funcional foi modificado nesta fase.

## 1. Confirmação da Fase 10

As sete correções de entrega da revisão anterior continuam cobertas pela suíte:
proteção contra links de saída, validação antes da escrita e sob `python -O`,
falhas Git, autorreferência do relatório, detecção de telefone, URLs SSH e leitura
dos blobs staged. Os 37 testes direcionados estão incluídos nos 444 testes
executados agora. Não surgiu uma nova falha comprovada que justificasse alteração
no produto ou nos scripts.

Foram confirmados README, lock, decisões técnicas, contratos, fontes documentais,
limitações e declaração de uso do Codex. Os cinco exemplos existentes mantêm
hashes válidos e identificação explícita de simulação. Uma nova reprodução foi
feita somente em diretório temporário, preservando os exemplos entregáveis.

A evidência de instalação limpa da revisão anterior continua válida para o código
atual: **95 arquivos executáveis, fixtures e configuração coincidem byte a byte**
com a cópia isolada. Seu venv já havia sido criado sem pacotes do sistema e
instalado pelo lock. Nesta Fase 11 ele foi **reutilizado**, não criado novamente;
os testes e comandos abaixo foram executados novamente. O registro inicial
`clean_environment.json` é histórico; a confirmação pós-correções está em
`phase10_review_validation.json`.

## 2. LLM e testes reais

A leitura efetiva de `Settings`, incluindo ambiente e `.env`, foi válida, mas
`llm_configured=false`. Nenhuma credencial, comprimento, prefixo ou hash de
credencial foi registrado.

| Configuração | Estado observado / necessidade |
|---|---|
| `EMPORIO_LLM_PROVIDER` | Ausente; adaptadores aceitos: `openai` ou `openai_compatible` |
| `EMPORIO_LLM_MODEL` | Ausente; escolher identificador acessível e testar disponibilidade |
| `EMPORIO_LLM_API_KEY` ou `OPENAI_API_KEY` | Nenhuma credencial efetiva disponível |
| `EMPORIO_LLM_BASE_URL` | Ausente; obrigatório somente para `openai_compatible`, com Responses API |
| `EMPORIO_CHAT_MODE` | Valor efetivo `real`; isso não configura um provedor |
| Catálogo local | `data/emporio.sqlite3` existe |
| Base demonstrativa do runtime | `data/demo.sqlite3` não existe no workspace; preparação documentada no README |
| PDF do runtime | Não configurado; manual original existe localmente em `data/raw/` |

O SDK oficial instalado é OpenAI **3.42.0**, com adaptador Responses API. Não existe
modelo pago padrão. Presença do SDK e configuração sintaticamente válida não
comprovam acesso, saldo, qualidade, latência ou retenção de dados do provedor.
Para políticas, preferir inicialmente o PDF sintético do avaliador; envio do
manual interno a terceiros exige revisão de permissão. Pedidos autorizados devem
usar somente a base sintética e concessão administrativa do backend. A API HTTP
continua sendo exclusivamente visitante, sem liberação de pedidos.

Os seis testes reais solicitados ficaram **não executados**, todos por
`provider_not_configured`:

| Teste real solicitado | Chamadas de tools observadas | Latência real / tokens / custo |
|---|---|---|
| Catálogo: nylon disponível até R$ 1.000 | Não executado | N/D |
| Promoção do produto 127 e PIX não cumulativo | Não executado | N/D |
| Devolução: recebimento e distinção 7/30/90 dias | Não executado | N/D |
| Pedido autorizado e ausência de rastreio | Não executado | N/D |
| Contexto: produto anterior e condição de pagamento | Não executado | N/D |
| Fora do escopo | Não executado | N/D |

Foram executadas as barreiras documentadas, sem chamada externa:

```bash
python scripts/check_agent.py --real --database <base-sintetica-temporaria>
python scripts/evaluate_agent.py --real --output <temporario>/real_not_run.json
```

O primeiro retornou código **0**, `execution=not_run` e
`real_provider_called=false`; esse zero não significa teste real aprovado.
O segundo retornou código **3**, `execution=not_run` e zero casos executados.
Tempos dos processos de diagnóstico não são latência de LLM.

## 3. Testes automatizados e os 35 skips

Resultados novos desta fase, sem equivalência entre mocks e provedor real:

| Ambiente / comando | Resultado observado |
|---|---|
| Workspace com originais: `python -m pytest -q` | **444 passed in 18.37s** |
| Workspace: `python -m pytest -q -m local_data -rs` | **35 passed, 409 deselected in 2.01s** |
| Cópia isolada sem anexos: `python -m pytest -q` | **409 passed, 35 skipped in 16.84s** |
| Cópia isolada: `python -m pytest -q -m local_data -rs` | **35 skipped, 409 deselected in 0.72s** |
| `python -m ruff check .` | **All checks passed!** |
| `python -m ruff format --check .` | **104 files already formatted** |
| `python -m pip check` | **No broken requirements found.** |
| Imports de configuração, API, orquestrador, factory e serviços | Código **0** |
| Versões instaladas versus `requirements-dev.lock` | **32/32 correspondentes** |

Os comandos pytest também receberam `--junitxml` com saída temporária para
comparar os identificadores. Os **mesmos 35 casos** passaram com anexos e foram
ignorados sem anexos. Distribuição conferida no código e nos resultados JUnit:

| Módulo | Casos | Dependência ausente na cópia pública |
|---|---:|---|
| `test_policy_retrieval.py` | 30 | PDF privado: extração, tabelas, 26 perguntas, métricas e script |
| `test_tools.py` | 2 | Um PDF e um conjunto CSV |
| `test_local_snapshot.py` | 1 | Seis CSVs originais |
| `test_services.py` | 1 | Seis CSVs originais |
| `test_agent.py` | 1 | CSVs originais; o LLM deste teste é mock |
| **Total** | **35** | **31 dependem do PDF; quatro dos CSVs** |

São `pytest.skip` condicionais explícitos pela ausência das fontes locais,
não `xfail` nem falhas escondidas. Os 409 casos públicos continuam exercitando
fontes sintéticas. O ambiente isolado não recebeu anexos para eliminar os skips.
O teste com CSV original e LLM mock não é uma execução real do modelo.

Ambiente observado: Python **3.14.6**, SQLite **3.53.2**, FastAPI **0.162.0**,
Pydantic **2.14.2**, PyMuPDF **1.28.2**, pytest **9.2.0**, Ruff **0.17.3**.
A instalação limpa anterior e estas execuções cobrem essa combinação; não foi
executada uma matriz de todas as versões Python 3.11+.

Testes async/TestClient rodaram fora do sandbox pela limitação de encerramento
de threads já documentada, sem tráfego de LLM. O `pip check` em sandbox informou
cache não gravável e prosseguiu com sucesso. Um comando manual inicialmente
importou `create_provider`, nome inexistente; foi corrigido para a factory real
`configured_provider`. Uma sonda auxiliar de rastreio foi ajustada ao literal
observado “O snapshot não informa código de rastreamento.”. Esses ajustes foram
nos comandos de validação, sem mudança no produto.

## 4. Reprodução e demonstrações offline

No ambiente isolado, com variáveis de LLM removidas e dados apenas de
`data/samples`, foram reexecutados:

| Verificação | Resultado |
|---|---|
| Ingestão sintética duas vezes | Código 0 em ambas; idempotência também coberta por pytest |
| CLI: produto 102 | R$ 250,00, estoque 4; código 0 |
| CLI interativa: produto 102 → “E no PIX?” | Referência preservada, R$ 237,50; código 0 |
| CLI com concessão sintética: pedido 1 | Histórico R$ 999,90; sem rastreamento/previsão; código 0 |
| Mesmo perfil: pedido 2 | Negado; código 1 esperado |
| API offline por TestClient | health 200; sessions 201; chat 200; pedido visitante 403 |
| API com configuração atual incompleta | health 200, `chat_ready=false`; sessions 503, `service_unavailable` |
| `python -O scripts/generate_examples.py --output <diretorio-novo>` | Cinco exemplos validados, hashes conferidos; código 0 |

Não foram exportados tokens ou IDs de sessão. TestClient é transporte em processo,
não teste de implantação HTTP pública. A base usada nas sondas foi temporária;
a preparação do runtime permanente continua a seguir o README. Links locais de
README e revisão foram conferidos sem links quebrados.

Os cinco arquivos existentes têm o rótulo **SIMULAÇÃO EXECUTADA**, com
`ExampleProvider` roteirizado e serviços reais sobre fixtures:

| Exemplo | Tools capturadas no exemplo | Interpretação |
|---|---|---|
| [01_catalogo.md](../examples/01_catalogo.md) | `search_products` | Filtros e disponibilidade |
| [02_promocao_pagamento.md](../examples/02_promocao_pagamento.md) | `get_product_details`; `get_product_offers` três vezes | Promoção + PIX + contexto + parcelas; caso não trivial |
| [03_pedido_protegido.md](../examples/03_pedido_protegido.md) | `get_order_status` duas vezes | Autorização sintética, histórico, ausência e acesso negado |
| [04_devolucao.md](../examples/04_devolucao.md) | `search_store_policies` duas vezes | Recebimento necessário; 30 dias de troca versus 90 de garantia |
| [05_fora_escopo.md](../examples/05_fora_escopo.md) | Nenhuma | Bloqueios de escopo/injection antes do provedor |

São dez turnos, nove calls de tools e 15 calls ao provedor mock no manifesto.
Esses roteiros selecionam intencionalmente as ferramentas; não demonstram
seleção autônoma de um LLM. Não foram convertidos em conversas “reais”.

A avaliação integrada foi repetida com o roteiro original, sem ajuste de nota:
**25/40 cenários**, 46 turnos, tools corretas **36/46**, argumentos **30/46**,
grounding limitado **22/22**, compliance **43/46**, controle direto **39/39**.
Recall@3 do agente roteirizado **0%** e do controle **100%** nas sete consultas
documentais aplicáveis. Erros por componente: seleção do provedor 16,
compliance 3 e plano de resposta 1; contagens podem compartilhar turnos.
O código **1** do avaliador representa falhas medidas, não erro operacional.

Latência observada **apenas offline**, por turno: mediana **20,7584 ms** e p95
**46,0529 ms** (46 amostras; nearest rank). Tokens/custo: **N/D**. Os 444 testes
aprovados validam também a detecção dessas limitações; não transformam 25/40 em
aprovação conversacional. Os resultados originais da Fase 09 foram preservados.

## 5. Git, segredos e fontes restritas

| Comando / evidência | Observação |
|---|---|
| `git status --short` | 12 entradas de topo `??`; todo o conjunto publicável está não rastreado |
| `git log --oneline` | Código 128: HEAD ainda sem commits |
| `git log --all --format=...` | Nenhuma entrada |
| `git rev-list --all --count` | **0 commits** |
| `git ls-files --cached` / `--stage` | **0 arquivos** no índice |
| `git diff --no-ext-diff --no-textconv` e variante `--cached` | Vazios, código 0; não incluem os arquivos não rastreados |
| `git diff --check` | Código 0; alcance limitado pela ausência de arquivos rastreados |
| Configuração de remoto examinada pelo auditor | Nenhum remoto configurado; URL não exportada |
| Auditor v1.2, índice e candidatos de worktree | **Zero achados**; ver também evidência estruturada final |

Foram examinados os 129 candidatos anteriores à Fase 11 e novamente o conjunto
com os dois novos documentos. Os sete probes de exclusão passaram: `.env`,
`.env.production`, chave, CSV/PDF bruto, SQLite e log. As referências de clientes
originais foram comparadas localmente, sem exportar seus valores. Não há PDF,
base, chave ou anexo privado entre os candidatos examinados. Há **zero blobs de
índice** para inspecionar; a suíte também testa a proteção contra segredo staged.

Os nove originais externos ao repositório coincidem com os hashes registrados na
Fase 02. Os arquivos já existentes no projeto coincidem com o inventário anterior
à Fase 11. Foram acrescentados somente este relatório e sua evidência JSON.
Não há histórico de commits para uma varredura histórica de segredos; a análise
heurística atual não garante ausência absoluta de PII/segredos e não autoriza
publicação.

A redistribuição dos anexos não foi autorizada no workspace. Mantê-los ignorados
e usar fixtures sintéticas permite preparar o conjunto público sem presumir essa
permissão. Caso se queira publicar os originais, obter autorização explícita antes.
Não é necessário publicar o manual ou clientes para reproduzir a demonstração.

## 6. Confronto com o desafio

| Entregável | Estado final verificável |
|---|---|
| Python, persona, catálogo, ofertas, políticas e pedidos protegidos | Implementados e testados localmente; integração real do LLM pendente |
| Framework/modelo/provedor e justificativas | Arquitetura/SDK documentados; modelo definitivo ainda não escolhido/validado |
| README com execução, retrieval, testes, limites e uso do Codex | Presente; comandos offline revalidados e instalação limpa anterior confirmada |
| 3–5 conversas, uma não trivial | Cinco Markdown sanitizados, claramente simulados; nenhuma conversa com LLM real validada |
| GitHub público com histórico real de progresso | **Não atendido**: zero commits, zero remoto, nenhum link de entrega |
| Repositório sem segredos/anexos não autorizados | Candidatos locais aprovados pelo scanner; revisão humana final pendente |
| Entrega por link no e-mail e respeito ao prazo | **Pendente**: e-mail, prazo/fuso e autorização de envio não fornecidos |

O enunciado menciona o prazo no e-mail. Datas da especificação, arquivos ou desta
revisão não foram tratadas como deadline. Não foram criados commits retroativos
para aparentar desenvolvimento progressivo. Conversas simuladas não comprovam
funcionamento do requisito central de LLM e não foram declaradas equivalentes a
resultados reais.

## 7. Pendências, severidade e ações do candidato

1. **Alta — LLM real não validado.** Configurar localmente provedor, modelo com
   acesso e credencial, além da URL se compatível; definir orçamento. Não colar
   credenciais no chat ou versioná-las. Depois executar os seis fluxos reais e a
   avaliação, registrando calls, falhas, latência e uso quando informado. Essa
   execução técnica pode ser retomada pelo Codex após a configuração. Usar fontes
   sintéticas inicialmente; pedidos autorizados no backend, nunca no HTTP público.
2. **Alta — entregável Git incompleto.** O candidato precisa decidir com o
   avaliador como tratar a ausência de histórico progressivo e revisar/autorizar
   os próximos commits e eventual repositório público/push. Commits novos honestos
   não recuperam um histórico que não existe. Nada será feito automaticamente.
3. **Alta para envio — prazo e autorização externa desconhecidos.** Informar o
   deadline efetivo, fuso e se alterações ainda são permitidas; revisar a entrega
   e autorizar separadamente publicação e envio do link. Não modificar após o
   limite aplicável. Esta revisão não presume que o prazo esteja aberto.
4. **Condicional — anexos restritos.** Manter os originais excluídos é a opção já
   preparada. Somente se desejar redistribuí-los, obter permissão explícita dos
   responsáveis e revisar os dados. Confirmar também a política do provedor antes
   de enviar material interno. Fixtures públicas não dependem dessa redistribuição.
5. **Média — limites conhecidos, sem correção artificial.** O roteiro offline
   atinge 62,5%; filtros de injection/PII são heurísticos, sessões são locais e não
   há autenticação real. A qualidade de um modelo real continua desconhecida.
   O candidato deve compreender e assumir essas decisões, sem alegar revisão
   humana ou aprovação do avaliador que não ocorreu.

**GO para continuar a validação local; NO-GO para declarar o desafio entregue.**
A remoção do NO-GO exige evidência do LLM real e resolução dos entregáveis e
autorizações externas acima. Não há nova funcionalidade recomendada por esta
revisão, nem próxima fase de implementação iniciada automaticamente.

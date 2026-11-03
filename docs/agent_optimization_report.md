# Fase 12B — decisões, otimização e avaliação completa

Revisão solicitada em **01/11/2026**, America/Belém. **Recomendação local:
`qwen3.5:9b`, contexto 4.096, temperatura 0, thinking desativado e finalização
estruturada ativa.** O perfil passou de **21/40 para 28/40 tarefas**.
Isso ainda é **NO-GO para atendimento geral/entrega externa completa**: restam
12 falhas de tarefa e duas violações dos critérios automáticos de compliance.

Foram lidos AGENTS.md e os relatórios de readiness e Ollama. As evidências
anteriores foram preservadas. A análise consolidada está em
[optimization/comparison.json](optimization/comparison.json); cada perfil abaixo
tem seus 40 casos, 46 turnos, checks, requisições físicas, argumentos, saídas
do provedor, tokens e amostras de recursos. Raciocínio interno, headers,
credenciais e IDs/tokens de sessão não foram exportados.

## Mudanças implementadas e impactos

| Mudança | Falha comprovada / impacto |
|---|---|
| Negativa terminal em `AgentOrchestrator` | `get_order_status → forbidden` agora produz acesso negado imediatamente. O modelo não pode reinterpretar como fora do escopo nem prosseguir com outras calls do batch |
| Prompt distingue funções e intenções | Nomeia as seis tools executáveis; explica que `intent`, `clarification` e `evidence_call_ids` são campos de texto JSON. `intent_clarify`/`answer_order` não são funções |
| Correlação no adaptador | Mapa **ID → ferramenta**, calculado somente de calls conhecidas e resultados `ok`, é enviado no contexto de ambas as etapas, normal e finalização. Não contém identidade ou autorização |
| Sampling configurável | `EMPORIO_LLM_TEMPERATURE` e `EMPORIO_LLM_REASONING_EFFORT`, opcionais. O `.env` local usa `0`/`none`; padrões públicos vazios preservam o comportamento anterior de outros provedores |
| Benchmark reproduzível | `scripts/benchmark_agent.py`: somente Ollama loopback, modelos já listados, fontes sintéticas, saídas novas, checkpoint, contagem de requisições e amostragem de RAM/VRAM |
| Regressões | Negativa independe da próxima intenção do modelo, mantém HTTP 403 e não consulta o restante do batch. Registry real continua recusando as duas funções fictícias. Testes verificam correlação, sampling e limites do benchmark |

A consulta e a autorização continuam em `OrderService`/backend, sem alteração nos
serviços ou repositórios. A negativa não revela existência, cliente, valor ou
rastreio. Pedido inexistente e pedido alheio continuam protegidos. HTTP continua
apenas visitante, sem autenticação real ou concessão de pedidos pelo texto.

Na comparação controlada, **PED04, PED05 e PED06 passaram e usaram uma requisição
cada**. No smoke final do runtime, PED04 retornou:

> Acesso negado: não posso consultar esse pedido sem a autorização necessária.
> Um atendente pode ajudar a confirmar o acesso.

O status do resultado conversacional é `answered`, por ser uma negativa explícita;
a trace permanece `forbidden` e a interface HTTP continua mapeando-a para **403**.
Duas expectativas antigas de integração que exigiam abstenção foram atualizadas
para essa resposta, com asserção adicional de acesso negado e ausência de dinheiro.
**Os gabaritos em `tests/evaluations/` não foram alterados.**

### Investigação das funções fictícias e da correlação

A execução Ollama anterior continha `intent_clarify` e `answer_order` em itens
`function_call`, embora nenhuma dessas funções existisse no registry. A execução
12B inicial também observou `intent_answer`. O problema era na saída/seleção do
provedor, não uma tool ausente que devesse ser implementada. Não foram criados
aliases, dispatch especial nem execução de SQL para acomodar essas respostas.

O prompt diferencia o plano final de uma chamada executável; a whitelist continua
autoritativa. Nos 40 casos finais a 4.096, não houve chamadas nativas com nomes
fora da whitelist. No experimento 8.192 reapareceu **uma `answer_order`**, recusada
com `unknown_tool`. Portanto o prompt melhorou a observação, mas não garante que
o modelo nunca tente uma função inexistente. As injeções programáticas do harness
são identificadas separadamente e não foram contadas como escolhas autônomas.

MUL02/MUL04 expuseram outra falha concreta: a finalização repetia o mesmo ID de
evidência, levando a abstenção. A dica de correlação existia somente na chamada
normal. Ela foi substituída pelo mapa ID → nome e passou a ser usada nas duas
etapas. **Não normalizamos IDs inventados/duplicados nem escolhemos fatos pelo
gabarito.** O backend continua rejeitando planos inválidos; o schema restringe IDs
às consultas bem-sucedidas. Ambos os casos passaram na avaliação final.

## Método e controles

- **40 casos existentes / 46 turnos:** catálogo 8, preços 6, políticas 8, pedidos 6,
  múltiplas etapas 5, robustez 7. Comparadores determinísticos existentes; sem LLM-juiz.
- Catálogo, pedidos e PDF **exclusivamente sintéticos**. O mesmo PDF gerado foi
  reutilizado byte a byte; hashes dos gabaritos e fixtures conferidos entre perfis.
- Ollama **0.35.0**, SDK OpenAI **3.42.0**, Python **3.14.6**. Temperatura **0**,
  `reasoning.effort=none`, saída até 1.200 tokens/requisição, timeout de requisição
  60 s, total 120 s, quatro rodadas e até 12 calls de tools em todos os perfis.
- Código anterior congelado antes de editar. Perfis finais on/off, 8.192 e Qwen 8B
  usaram o **mesmo hash de código congelado**. O código atual tem AST idêntica;
  a diferença posterior é apenas quebra de uma string para lint.
- Inferência serial, um modelo carregado por vez. Warm-up excluído e registrado.
  Temperatura 0 não garante determinismo bit a bit: não se alegou seed suportado.
  IDs opacos de calls e carga de desktop também podem variar. Uma passagem por
  perfil, conjunto conhecido de desenvolvimento, sem validação estatística cega.

**Execução real não significa 40 conversas inteiramente autônomas.** O sujeito
configurado foi o modelo local real. A suíte mantém seus guards e falhas simuladas:
acessórios/injection podem ser resolvidos sem LLM; ROB05 injeta timeout;
ROB06/ROB07 injetam tentativas inválidas. Cada perfil completo registra **três
chamadas injetadas pelo harness**, separadas das delegadas ao modelo. Controles
diretos de serviços foram **39/39**, sem alimentar o agente com o gabarito.

O número de requisições abaixo conta **POST /v1/responses** reais, incluindo a
finalização adicional. Não inclui sondas de versão/recursos ou preload vazio.
`physical_requests.final_text` é saída bruta, não necessariamente exibida ao usuário.
O backend só entrega fatos renderizados de respostas tipadas e verificadas.

## Resultados observados

| Perfil | Tarefas /40 | Tools exatas /46 | Argumentos /46 | Grounding aplicável | Compliance /46 | Mediana / p95 por turno | Requisições / finalizações |
|---|---:|---:|---:|---:|---:|---|---:|
| [Antes, 9B/4k](optimization/before_40.json) | 21 | 28 | 27 | 24/24 | 44 | 4,277 / 7,607 s | 144 / 33 |
| [Intermediário: decisões e prompt](optimization/after_decisions_40.json) | 25 | 38 | 33 | 24/24 | 44 | 4,304 / 6,718 s | 116 / 38 |
| [Final: 9B/4k, finalização ativa](optimization/qwen35_4096_finalize.json) | **28** | 37 | 34 | 26/26 | 44 | **4,046 / 5,665 s** | **115 / 35** |
| [Mesmo código, finalização desligada](optimization/qwen35_4096_native.json) | 6 | 37 | 34 | N/D, 0 aplicáveis | 46 | 2,300 / 5,193 s | 73 / 0 |
| [9B/8k, finalização ativa](optimization/qwen35_8192_finalize.json) | 28 | 36 | 33 | 26/26 | 44 | 4,395 / 6,615 s | 114 / 34 |
| [Qwen3 8B/4k, preset equivalente](optimization/qwen3_4096_matched.json) | 24 | 36 | 30 | 22/22 | 45 | 1,283 / 3,738 s | 78 / 4 |

São métricas diferentes: a tarefa pode obter o resultado esperado com uma call
extra, sem passar em seleção exata. Grounding verifica dinheiro, seções e algumas
triplas de produto; **100% aplicável não prova correção semântica geral**. A
compliance 46/46 sem finalização decorre sobretudo de abstenções, não de melhor
atendimento. Os percentis usam nearest rank nas 46 observações, incluindo guards;
tempos por caso e por requisição estão nos JSON, com seus próprios denominadores.

O antes foi **reexecutado** sob os controles acima; não foi usado o p95 dos oito
casos antigos, que tinham outro sampling. O ganho conjunto foi de **7 tarefas
(17,5 pontos percentuais)**, 29 requisições a menos e p95 de 7,607 para 5,665 s.
Não se atribui esse ganho inteiro a um componente isolado das mudanças.

### Custo da finalização estruturada

A comparação on/off manteve código, modelo, dados, contexto e sampling iguais.
Com finalização, 35 requisições extras somaram **44,287 s**: **26,6%** dos
**166,378 s** totais medidos no SDK. Cada finalização teve mediana **1,228 s**,
média **1,265 s** e p95 **1,606 s**. Representaram **30,4% das 115 requisições**.

Sem finalização, o SDK acumulou **105,910 s** e o sucesso caiu de **28 para 6**.
Houve 73 calls nativas contra 80 com o recurso ativo: históricos e caminhos de
recuperação posteriores também mudaram. A diferença total de tempo, portanto,
não é exclusivamente o custo da etapa extra; o custo direto vem de suas traces.
**Retirar a finalização reduz latência, mas foi rejeitado pela perda de qualidade.**

Tokens informados no perfil selecionado: **174.670** (169.202 entrada + 5.468 saída);
sem finalização: **128.275**. Todas as 115 requisições selecionadas informaram uso.
Turnos resolvidos por guards/falhas injetadas não têm uso de modelo. Custo faturado
e energia: **N/D**, sem estimativa de tarifa ou confusão entre tokens e dinheiro.

## Contexto e recursos

Ambiente observado: Linux/x86_64, 12 CPUs lógicas, aproximadamente 16 GB de RAM,
RTX 3060 com **12.288 MiB** de VRAM. O contexto 4k foi confirmado em `/api/ps`;
corresponde ao padrão documentado do Ollama para essa faixa de VRAM.
[Context length — Ollama](https://docs.ollama.com/context-length).

Antes do ensaio 8k, exigiu-se **8.192 MiB de VRAM livre e 2 GiB de RAM disponível**,
sem outro modelo carregado. A primeira leitura após `ollama stop` ainda mostrava
liberação assíncrona de VRAM e abortou o início com segurança. Nova leitura
confirmou **11.588 MiB livres**, antes de iniciar o ensaio. Não houve OOM ou
timeout de SDK nos perfis medidos.

| Perfil | Contexto efetivo | VRAM do modelo reportada | Máximo amostrado de VRAM total | RAM disponível mínima amostrada |
|---|---:|---:|---:|---:|
| 9B/4k | 4.096 | 5.589.560.196 bytes | 6.719 MiB | 2.246.664 KiB |
| 9B/8k | 8.192 | 5.828.646.010 bytes | 6.993 MiB | 8.744.336 KiB |
| 8B/4k | 4.096 | 5.578.204.118 bytes | 5.834 MiB | 4.652.280 KiB |

São amostras a cada três segundos, não picos exclusivos do agente. RAM/VRAM
totais incluem outras aplicações; mudanças de RAM livre não são comparação
isolada de consumo dos modelos. O incremento de VRAM reportado pelo modelo 9B
em 8k foi aproximadamente **228 MiB**. Cold load de 8k/8B levou **25,260 / 21,179 s**,
fora das estatísticas de turnos.

O alias 8k herdou os pesos de `qwen3.5:9b`, mudando apenas `num_ctx`. Os 40 casos
tiveram os **mesmos 28 acertos e as mesmas 12 tarefas falhas**. A latência aumentou
e a seleção não melhorou. O maior input informado foi 2.086 tokens em 4k e 2.150
em 8k; não há evidência de que falta de janela explicasse essas falhas. Não se
extrapola isso para conversas extensas ou para saturação de 8k, que não foi testada.

Não se alterou `OLLAMA_CONTEXT_LENGTH`, reiniciou servidor ou baixou pesos. Foram
criados dois aliases locais temporários com `FROM` de modelos existentes,
reutilização de layers confirmada, e removidos ao final. Os três modelos originais
permaneceram com os mesmos IDs. A abordagem segue o
[Modelfile oficial](https://docs.ollama.com/modelfile).

## Comparação com Qwen3 8B e recomendação

Persistindo falhas no 9B, foi avaliado o **Qwen3 8.2B Q4_K_M já instalado**. O alias
de comparação manteve seu template/stop tokens e fixou `presence_penalty=1.5` para
igualar o 9B. Ambos usaram contexto 4k, temperatura 0, thinking none, top_k 20,
top_p 0,95, repeat_penalty 1, mesmos limites e código. O default de repeat_penalty
do servidor foi conferido no
[código Ollama 0.35.0](https://github.com/ollama/ollama/blob/v0.35.0/api/types.go).
O resultado não deve ser apresentado como teste do preset original do 8B sem ajustes.

O 8B foi mais rápido: mediana **1,283 s** contra **4,046 s**. Porém fez **24/40**,
contra **28/40**; políticas **2/8** contra **5/8**; Recall@3 do agente **2/7** contra
**6/7**, com o mesmo retriever. Sua compliance foi 45/46 versus 44/46; isso não
compensa automaticamente a perda de cobertura. **Mantive o 9B pela prioridade
de qualidade e políticas**, com 4k e fallback ativo. O 8B é opção de menor latência
com essa perda medida, sem afirmar superioridade geral de um dos modelos.

O `.env` local foi ajustado a `EMPORIO_LLM_TEMPERATURE=0` e
`EMPORIO_LLM_REASONING_EFFORT=none`, mantendo `qwen3.5:9b` e finalização ativa.
A key foi preservada, não exposta; `.env` continua ignorado e com modo 0600.
O smoke final confirmou esses parâmetros no SDK e a execução real do runtime
com fontes temporárias sintéticas. Não houve comparação completa contra thinking
padrão nesta fase: os ganhos antes/depois não são atribuídos a essa opção.

## Falhas residuais e limites

No perfil escolhido falharam: **CAT07, CAT08, PRE05, PRE06, POL03, POL04, POL08,
MUL01, ROB03, ROB04, ROB06 e ROB07**. São preservadas nos artefatos:

- **Seleção/argumentos:** filtros compostos, parcelas e roteamento de perguntas
  documentais ainda recebem argumentos ou calls inadequados.
- **Plano final:** ausência de produto e alguns erros de tool são tratados como
  esclarecimento/saudação inadequados em vez do encaminhamento esperado.
- **Compliance:** POL04 e ROB03 retornaram fatos onde os gabaritos exigiam
  esclarecimento/abstenção sem fatos. Grounding passou sobre fatos verificados,
  mas isso não torna a decisão de resposta correta.
- **Robustez:** bloquear injection ou uma função inválida não garante que o modelo
  escolha a melhor resposta seguinte. Nenhum SQL arbitrário ou acesso indevido
  foi liberado; não há alegação de autenticação real.

Erros por componente, com sobreposição possível: seleção do provedor **12**, plano
de resposta **3**, protocolo/limite **2**, compliance **2**. O conjunto é pequeno,
conhecido, de fixtures; uma passagem não demonstra estabilidade estatística ou
qualidade em produção. Não houve alteração de gabaritos para converter falhas em
acertos, nem uso de LLM-juiz. Os resultados offline históricos 25/40 e os exemplos
antigos continuam identificados como evidências de suas versões anteriores.

## Testes, reprodução e auditoria

| Verificação final real | Resultado |
|---|---|
| `python -m pytest -q` no projeto | **466 passed in 16.72s** |
| Cópia de fontes sem anexos e `.env` | **431 passed, 35 skipped in 15.98s** |
| `python -m ruff check .` | **All checks passed!** |
| `python -m ruff format --check .` | **110 files already formatted** |
| `python -m pip check` | **No broken requirements found.** |

A cópia reutiliza as dependências do venv do workspace: **não foi nova instalação
limpa**. O venv temporário antigo já não existia. Na primeira cópia, omitiram-se
`.gitignore` e `docs/tool_contracts.json`, causando uma falha e 14 erros de setup;
a cópia foi corrigida, sem modificar o produto/testes por esse motivo. Os 35 skips
são os casos privados de dados, não defeitos. Testes de regressão usam mocks;
as avaliações comparativas usam o Qwen real com as injeções explicitadas acima.

Após configurar o Ollama local e ativar o venv, repetir on/off com **saídas novas**:

```bash
python scripts/benchmark_agent.py --tag qwen35_on --model qwen3.5:9b \
  --finalization on --thinking none --context 4096 \
  --work-dir /tmp/emporio-12b-repeat --output /tmp/qwen35-on.json
python scripts/benchmark_agent.py --tag qwen35_off --model qwen3.5:9b \
  --finalization off --thinking none --context 4096 \
  --work-dir /tmp/emporio-12b-repeat --output /tmp/qwen35-off.json
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

O script usa somente endpoint `http://127.0.0.1:11434/v1`, exige modelo listado,
gera fontes sintéticas e verifica o hash do PDF compartilhado no work-dir. Código
1 indica falha de tarefa medida; 2 indica erro operacional. Helpers dos primeiros
perfis retornavam 0 quando a coleta terminava, **não quando 40 tarefas passavam**.

Para reproduzir os aliases removidos, confirmar primeiro as duas bases em
`ollama list`; se ausentes, parar, sem download automático. Usar Modelfiles:

```text
# Contexto, FROM qwen3.5:9b:
FROM qwen3.5:9b
PARAMETER num_ctx 8192

# Comparação 8B, em arquivo separado:
FROM qwen3:8b
PARAMETER num_ctx 4096
PARAMETER presence_penalty 1.5
```

Criar com `ollama create <alias-novo> -f <Modelfile>` e passar o nome a `--model`;
usar `--context 8192` somente para o primeiro. Os parâmetros usados,
criação/remoção dos aliases e preflights estão documentados no comparison.json.
Descarregar o modelo anterior e conferir RAM/VRAM antes de aumentar contexto.

Hashes confirmam **sete originais em data/raw**, seis fixtures públicas, gabaritos,
serviços/repositórios/tools e dependências preservados. Não foi enviado anexo
privado ao LLM. A auditoria final de candidatos e suas limitações também constam
no comparison.json. Não há commit, push, publicação ou reescrita de histórico.
O [diff de código](optimization/code_changes.patch) registra as mudanças do
snapshot anterior para o código atual, sem `.env` ou dados. Permite revisar e
reconstruir o antes em cópia temporária; não representa um commit ou histórico Git.

**Arquivos:** orquestrador, provider, prompt e configuração; `.env.example` e README;
testes de agente/provider/sessões e o novo benchmark com testes de guardas;
este relatório e JSON em `docs/optimization/`. Apenas configuração local de
sampling foi ajustada no `.env`, sem versioná-lo.

**Parecer:** correção de PED04 aprovada e otimização local mensurada. Manter 9B/4k
com finalização. A entrega externa continua pendente de corrigir os fluxos residuais,
validar generalização, revisão do candidato e resolver Git/prazo/autorização de
publicação; não declarar o agente aprovado só pelos testes automatizados.

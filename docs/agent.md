# Orquestração LLM — Fase 06

Agente de uma mensagem com seis tools existentes, provedor configurável,
persona em português e falhas seguras. Não implementa sessões, API, UI ou
histórico entre execuções. Não usa LangGraph, ReAct genérico ou multiagentes.

## Fluxo e garantia de fonte

1. AgentRequest valida a mensagem; o loop envia persona, mensagem e schemas.
2. O LLM seleciona chamadas. Argumentos são JSON limitado, sem duplicidades ou
   números não finitos; ToolRegistry valida e executa somente a lista fechada.
3. Cada saída volta ao modelo como function_call_output associado ao call_id.
   Chamadas podem ocorrer juntas ou em rodadas sucessivas.
4. O modelo termina com AnswerPlan: intenção e referências a chamadas desta
   execução. O backend valida sucesso e origem de cada referência.
5. O renderer produz português usando somente esses resultados tipados. Não
   exibe texto livre do LLM nem preços/estoque inventados no plano.

Exemplo de plano interno, sem dados comerciais livres:

```json
{"intent":"answer","evidence_call_ids":["demo_catalog"],"clarification":null}
```

Um plano com ID inexistente, referência a erro, campos extras ou texto livre é
recusado. Não há fallback numérico. Uma falha de catálogo seguida de um preço
inventado pelo mock resulta em abstenção. A regra depende do backend, além do
prompt. O LLM coordena ferramentas e intenção; a redação factual é controlada.

## Adaptador e configuração

SDK oficial verificado: openai 3.42.0. Protocolo próprio LLMProvider separa o SDK
dos serviços. `openai` usa o endpoint oficial quando nenhuma URL é informada;
`openai_compatible` requer URL de servidor compatível com Responses API.
Nenhum modelo é padrão e disponibilidade/qualidade/custo ainda não foram
testados com API real. Compatibilidade com Chat Completions isoladamente não basta.

Configuração no .env local, protegido pelo Git:

| Variável | Padrão / efeito |
| --- | --- |
| EMPORIO_LLM_PROVIDER | vazio; openai ou openai_compatible |
| EMPORIO_LLM_MODEL | vazio; nome explicitamente escolhido pelo avaliador |
| EMPORIO_LLM_API_KEY | vazio; alternativa OPENAI_API_KEY |
| EMPORIO_LLM_BASE_URL | vazio; obrigatório em openai_compatible |
| EMPORIO_LLM_TIMEOUT_SECONDS | 20, máximo 60 |
| EMPORIO_LLM_MAX_OUTPUT_TOKENS | 1200, intervalo 128–4096 |
| EMPORIO_AGENT_TIMEOUT_SECONDS | 30, máximo 120 |
| EMPORIO_AGENT_TOOL_TIMEOUT_SECONDS | 5, máximo 30 |
| EMPORIO_AGENT_MAX_ROUNDS | 4, intervalo 1–8 |
| EMPORIO_AGENT_MAX_TOOL_CALLS | 12, intervalo 1–32 |

Há também limite interno configurável de 4 chamadas por retorno (máximo 8),
mensagem de até 2.000 caracteres, contexto transitório de 128 KiB e resposta
renderizada de 8.000 caracteres. Rodadas contam todas as requisições ao LLM,
inclusive a que entrega o plano final. Escoar o limite não dispara chamada extra.

O adaptador envia strict=False nas funções porque specs é mapa dinâmico; a
validação backend permanece estrita. Mantém itens de reasoning quando retornados,
usa store=False e desativa retries automáticos para respeitar o orçamento de
tempo/chamadas. As decisões foram conferidas na
[documentação oficial de function calling](https://developers.openai.com/api/docs/guides/function-calling)
e na [referência do SDK Python](https://developers.openai.com/api/reference/python).

As tools não recebem credenciais ou identidade do cliente. Contexto de pedido é
injetado por keyword separada do backend e não enviado ao LLM. Não há mecanismo
de autenticação real; isso não é criado a partir de um ID declarado pelo usuário.

## Primeira conversa executada

Pergunta: “Quais violões de nylon disponíveis custam até R$ 1.000?”.

O diagnóstico **simulado** escolheu search_products com categoria Violões,
specs strings=nylon, max_price=1000.00, available_only=true e limite 20.
Tools, serviços e SQLite foram executados de verdade sobre os CSVs locais.
Retornaram IDs 83, 85, 81, 84 e 82, em ordem de preço: R$ 429,90, R$ 459,90,
R$ 599,90, R$ 689,00 e R$ 849,00. Todos tinham status ativo e estoque positivo.

O [registro da simulação](agent_demo_simulated.json) contém pergunta, resposta
renderizada e rastro sanitizado. `execution=simulated`, provider=scripted_mock,
real_provider_called=false e usage=null. Não é evidência de qualidade de um LLM
real, apenas do corte vertical e do contrato de orquestração.

O [diagnóstico real](agent_live_check.json) retornou execution=not_run,
reason=provider_not_configured. Provedor, modelo e credencial não estavam
configurados. Nenhuma chamada real ou cobrança de modelo foi feita por esse
diagnóstico. Latência, qualidade, tokens e custo reais não foram medidos.

## Reprodução

Após instalar pelo README e ingerir os originais:

```bash
python scripts/check_agent.py
python scripts/check_agent.py --real
python -m pytest tests/unit/test_agent.py tests/unit/test_provider.py tests/integration/test_agent.py
python -m pytest
python -m pytest -m 'not local_data'
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

O script é um diagnóstico de pergunta fixa, não uma CLI conversacional. Não
cria/ingere banco nem configura credencial automaticamente. `--database` aceita
um SQLite local explícito. O diagnóstico inicial usa apenas catálogo; as tools
documentais ficam indisponíveis nesse script, enquanto o orquestrador aceita
um registro completo com PolicyService na montagem da aplicação.

Sem originais, os testes públicos usam bases temporárias sintéticas. Um teste
ajusta o nome de categoria apenas no SQLite sintético para representar a pergunta;
nenhum CSV ou snapshot original é alterado. A métrica/qualidade de API real não
é inferida desses testes. Testes local_data podem ser desmarcados.

## Falhas e limites conhecidos

- Timeout de requisição/total cancela a espera; falha do SDK não expõe corpo HTTP
  ou chave. IDs duplicados, contexto excessivo ou resposta incompleta falham seguros.
- Tools síncronas usam threads. Cancelar a espera não mata o trabalho já iniciado;
  o encerramento do executor pode aguardar sua conclusão. Só há operações de leitura.
- O plano JSON é instruído no prompt e validado no backend. Modelo que não seguir
  o protocolo gera abstenção, não tentativa de interpretar texto factual livre.
- Não há memória de diálogo, seleção por referências de conversa anterior ou
  sessão autorizada. A Fase 07 permanece pendente.
- O renderer é deliberadamente restrito; não há síntese livre de comparações,
  decisão jurídica ou aprovação de devolução. Contatos e políticas mantêm fontes
  e ambiguidades; dados são snapshots, não estado em tempo real.
- Nenhum modelo real foi validado neste ambiente. Um servidor compatível pode
  rejeitar parâmetros, schemas ou recursos de Responses; isso vira falha segura.
- O sandbox desta sessão travou ao encerrar asyncio com thread de executor. Foi
  reproduzido num exemplo mínimo; fora dele o mesmo exemplo encerrou normalmente.
  Os testes assíncronos foram executados fora dessa restrição, sempre offline.

Não há avaliação integrada de ~40 cenários do agente nesta fase; esses testes
de componente/integração não substituem a Fase 09 nem as conversas da Fase 10.

## Resultados observados em 31/10/2026

Ambiente: Linux, Python 3.14.6, SDK openai 3.42.0, pytest 9.2.0 e Ruff 0.17.3.

| Verificação | Resultado real da execução offline |
| --- | --- |
| pytest completo | 282 passed em 3,57 s |
| pytest -m 'not local_data' | 247 passed, 35 deselected em 2,38 s |
| Casos adicionados | 44: 25 do loop, 12 do adaptador/configuração, 7 de integração |
| Ruff lint e formatação | Aprovados |
| Imports, entrada mínima e pip check | Aprovados |
| Pergunta fixa com LLM roteirizado | answered, 2 rodadas, 1 tool real, 5 produtos do snapshot |
| Chamada real | Não executada: provider_not_configured |

Foram verificados: múltiplas chamadas no mesmo retorno e em sequência, correção
de argumentos após erro, IDs de correlação e reasoning preservados, limite de
rodadas/chamadas, timeouts de requisição/total/tool, falha de catálogo sem preço,
texto livre/valores inventados rejeitados, autorização fora do modelo e rastros
sem ecoar nomes de tools desconhecidas. O SDK foi exercitado por HTTP simulado,
sem rede. Não foi feita inferência de qualidade, custo ou tokens reais do LLM.

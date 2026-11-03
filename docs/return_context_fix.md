# Correção da continuidade da devolução

Executada em 02/11/2026. Escopo: a resposta sobre recebimento e embalagem não
deve ser desviada para busca de instrumentos. Não houve nova funcionalidade de
devolução, cálculo de elegibilidade ou autorização de pedido.

## Falhas comprovadas e correção mínima

**Falsa referência de produto.** O detector removia acentos antes de procurar
demonstrativos. O verbo “está” virava “esta” e acionava a mesma regra usada em
“esta guitarra”. Sem um produto anterior selecionado, o backend respondia
“Qual instrumento ou modelo você procura?” antes de chamar o LLM.

Isso foi reproduzido com a frase sobre recebimento e produto ainda embalado:
nenhuma chamada ao provedor e nenhuma ferramenta no segundo turno. O histórico
não tinha sido apagado. O problema era a interceptação indevida da mensagem.

`refers_to_product` agora normaliza para NFC e distingue o verbo acentuado antes
da remoção geral de acentos. Demonstrativos reais e referências de pagamento
continuam funcionando. Não foram alterados os detectores de injeção, redação de
PII, autorização, repositórios, serviços, ferramentas ou contratos HTTP.

**Encaminhamento sem consulta.** Após corrigir apenas o detector, a repetição real
chegou ao modelo, que encaminhou o caso sem consultar as políticas. O prompt foi
ajustado para reconhecer informações de recebimento/embalagem como complemento
da devolução anterior e consultar `search_store_policies` antes de orientar.
Não exige modelo para explicar a política geral nem autoriza devolução com base
somente nas declarações do usuário. Não há frase/data/ID de caso codificado na
implementação. O contexto usa o histórico limitado e isolado já existente.

## Evidência real

Modelo mantido: `qwen3.5:9b`, Ollama local, temperatura 0, thinking `none` e
finalização estruturada ativa. Pergunta inicial: arrependimento de compra e
possibilidade de devolver. Complemento: data de recebimento e produto embalado.

| Etapa | Resultado do segundo turno | Chamadas ao adaptador | Latência |
|---|---|---:|---:|
| Antes | Pergunta por instrumento, sem ferramenta | 0 | 1,84 ms |
| Somente distinção do verbo | Encaminhamento sem consulta | 1 | 2.260,34 ms |
| Distinção + prompt | Política, seção 4.1, página 4, v2.1 | 2 | 6.276,78 ms |

Na repetição final da pergunta original, o primeiro turno também consultou a
seção 4.1 (6.750,80 ms), em vez de pedir a data. Não foi declarado que esse
primeiro esclarecimento é garantido em toda inferência: a resposta explicou
a regra geral e não decidiu a elegibilidade do caso.

Após reiniciar o FastAPI, foi verificada pela API a variante com data inicialmente
desconhecida. O primeiro turno pediu o recebimento por guard, sem LLM ou tools
(HTTP 200, 3,36 ms, zero rodadas). A resposta com a data e embalagem consultou
`search_store_policies` e citou a seção 4.1 (HTTP 200, 5.126,84 ms, duas rodadas).
Esse guard foi separado da inferência real; não é mock nem chamada de modelo.

Nenhuma execução aprovou a devolução ou consultou dados privados de pedidos.
São poucas observações, sem benchmark estatístico. As evidências públicas omitem
excertos do manual e substituem datas declaradas por marcadores. Não incluem
tokens de sessão, chaves, prompts completos ou dados de clientes.

## Verificações

```bash
.venv/bin/python -m pytest tests/unit/test_return_context.py tests/unit/test_session_security.py tests/unit/test_agent_residual.py tests/integration/test_sessions.py -q --tb=short
# 89 passed in 1.39s

.venv/bin/python -m pytest -q --tb=short
# 553 passed in 17.82s; nenhum skip

.venv/bin/ruff check .
# All checks passed!

.venv/bin/python -m compileall -q app
git diff --check
# Exit 0
```

Adicionados 11 testes offline: verbo acentuado em maiúsculas, NFC/NFD,
demonstrativos legítimos, referências PIX/parcelas e uma conversa com SQLite e
políticas sintéticas. O fluxo verifica pergunta de recebimento, consulta da
política depois da resposta, histórico presente e isolamento entre sessões.
Mocks não são apresentados como testes de compreensão do Qwen.

Alterados: `app/agent/security.py`, `app/agent/prompts.py` e `README.md`.
Adicionados `tests/unit/test_return_context.py`, este relatório e evidência.
Os gabaritos de 40/18 cenários, CSVs/PDF e banco original permaneceram idênticos
por SHA-256. Não foram reexecutadas as avaliações completas com Qwen.
O Git continua sem arquivos rastreados: o diff vazio não cobre alterações.
Versões anteriores e traces completos locais ficam em
`data/derived/return_context/`, ignorado pelo Git.

## Limites

Datas e condições fornecidas pelo usuário não são autenticação ou comprovação
de entrega. A correção não usa data do pedido/previsão como recebimento, não
calcula prazo com uma data atual presumida e não aprova/recusa devolução.
A aplicação da política continua dependendo do canal de compra e demais condições.
O detector lexical ainda pode ser ambíguo em escrita sem acentos; “esta” sem acento
também é um demonstrativo legítimo. O histórico permanece limitado por sessão/TTL.

O servidor foi reiniciado; atualizar a página inicia outra sessão. Não houve
commit, push, publicação, alteração de modelo/`.env` ou serviço externo.

[Evidência sanitizada](return_context_validation.json).

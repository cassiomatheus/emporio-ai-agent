# Correção de decisões sobre pagamento em dinheiro

Executada em 02/11/2026, limitada à pergunta sobre desconto em dinheiro depois
da consulta ao produto. Modelo, serviços monetários, tabelas da interface,
paginação, contratos das ferramentas e autorização de pedidos foram preservados.

## Evidências e causa

O usuário recebeu a resposta de fora do escopo ao perguntar “Se eu pagasse com
dinheiro teria desconto?”. A inspeção confirmou que os filtros de segurança,
acessórios e devolução não interceptam essa frase. Portanto, a classificação
incorreta decorre da decisão do modelo, não de um bloqueio por acessórios.
Não há trace do turno original para reconstituir seu plano exato.

Na reprodução real antes da correção, o Qwen não repetiu a recusa: fez uma troca
indevida de modalidade. Solicitou `get_product_offers` com `payment_method="pix"`
e produto 101 para a pergunta sobre dinheiro, e entregou R$ 996,55 com 5% de desconto.
O cálculo era correto para PIX, mas não respondia à modalidade solicitada.
Classificação: falha de argumentos/grounding, além da falha de roteamento relatada.

O manual local foi inspecionado pela extração existente. Não foram encontradas
menções a dinheiro/em espécie. A consulta lexical específica retornou `no_evidence`;
uma consulta mais ampla encontrou condições de PIX e outras modalidades, sem
evidência para dinheiro. Isso não demonstra que a loja aceita ou recusa dinheiro,
nem que oferece ou deixa de oferecer desconto nessa modalidade. Não foi criada
uma regra comercial para preencher essa ausência.

## Correção mínima

- O prompt identifica condições de pagamento como assunto da loja e orienta
  consultar políticas quando a modalidade não existe no schema de ofertas.
- Perguntas de dinheiro/em espécie disponibilizam apenas `search_store_policies`
  ao modelo. O backend também bloqueia tentativa de executar outra ferramenta
  nesse turno, inclusive a troca de dinheiro por PIX. Não há ferramenta fictícia.
- Um excerto somente sobre PIX não comprova condições para dinheiro: é tratado
  como ausência de evidência. Erros e ausência retornam mensagem de confirmação
  com atendente, sem preço ou percentual não confirmado.
- Se o modelo ainda escolher fora do escopo para uma dúvida de pagamento, a
  resposta explica que a condição não pôde ser confirmada. Esse ajuste não
  autoriza divulgar fatos. Os bloqueios anteriores de injeção e acessórios têm
  precedência; autorização de pedidos não foi alterada.
- Um novo turno explicitamente sobre PIX mantém ferramentas normais e consulta
  novamente a oferta do produto de referência. Não há valor guardado em cache.

Resposta observada para dinheiro após a correção:

> Não consegui confirmar nas fontes disponíveis as condições para essa forma de
> pagamento. Confirme com um atendente da loja antes de contar com um desconto.

## Testes e execução real

| Execução real local com `qwen3.5:9b` | Ferramenta no turno sobre dinheiro | Resultado | Latência |
|---|---|---|---:|
| Antes | `get_product_offers`, modalidade PIX | Resposta para modalidade diferente, incorreta | 6.121,10 ms |
| Depois | `search_store_policies`, query `pagamento dinheiro desconto`, top_k 3 | `no_evidence`, sem presumir desconto | 2.033,58 ms |
| Depois: “E no PIX?” | `get_product_offers`, produto 101, modalidade PIX | R$ 996,55, mantendo a referência | 5.393,33 ms |

O fluxo real incluiu antes a pergunta sobre parcelamento do Giannini GNF-3 CEQ.
Continuou mostrando até 10x conforme as regras existentes. Nessa etapa o modelo
ainda tentou `installments=24`, rejeitado pela validação, e recuperou-se em nova
chamada; esse erro residual de seleção de argumentos não foi mascarado nem tratado
como condição válida. Não foi ampliado o limite de rodadas.

Temperatura 0, thinking `none` e finalização estruturada ativa foram mantidos.
São observações pontuais, sem comparação estatística de desempenho. Tokens
informados pelo provedor estão nos traces locais; não houve estimativa de custo.
Nenhuma execução com mocks é apresentada como inferência real.

Após reiniciar o servidor, a sequência foi verificada pela API usada pela
interface: produto 101 (HTTP 200, 5.898,41 ms), dinheiro (HTTP 200, 1.124,15 ms,
políticas sem evidência) e PIX explícito (HTTP 200, 3.892,25 ms, oferta correta).
IDs/tokens de sessão e credenciais não foram registrados. Não foi necessário
alterar o frontend nem realizar nova inspeção visual para esta correção.

```bash
.venv/bin/python -m pytest tests/unit/test_payment_scope.py tests/unit/test_agent_residual.py tests/unit/test_agent.py tests/integration/test_sessions.py -q --tb=short
# 86 passed in 1.97s

.venv/bin/python -m pytest -q --tb=short
# 542 passed in 17.84s; nenhum skip

.venv/bin/ruff check .
# All checks passed!

.venv/bin/python -m compileall -q app
git diff --check
# Exit 0
```

Foram adicionados 16 testes offline, com mocks e uma conversa com SQLite/políticas
sintéticas. Cobrem recusa indevida, troca por PIX/oferta geral, fonte só de PIX,
ausência, injeção, citação de eventual política sintética de dinheiro, fora do
escopo legítimo e referência preservada após a incerteza. A suíte completa inclui
contratos, regras da loja, autorização, sessões, paginação e tabela de parcelas.
Não foram reexecutados os 40/18 cenários completos com inferência real.

## Arquivos, reprodução e limites

Alterados: `app/agent/requirements.py`, `app/agent/prompts.py`,
`app/agent/orchestrator.py` e `README.md`. Adicionados
`tests/unit/test_payment_scope.py`, este relatório e evidência sanitizada.
Os originais, banco e gabaritos foram comparados por SHA-256 antes/depois.
O Git continua sem arquivos rastreados; o diff vazio não cobre as alterações.
Versões anteriores e traces locais ficam em `data/derived/payment_scope/`, ignorado.

O reconhecimento de modalidade é lexical e conservador. Perguntas que misturam
dinheiro com outras modalidades, inclusive menções negativas/ambíguas, podem ser
encaminhadas; perguntar separadamente pelo PIX funciona no fluxo verificado.
Outras modalidades não suportadas ainda dependem da seleção do modelo, dos
contratos e das políticas disponíveis. Encontrar o termo em um excerto é uma
condição necessária, sem equivaler a uma validação semântica completa de políticas
futuras. O agente continua um protótipo, não uma homologação de atendimento comercial.

O servidor local foi reiniciado. Para repetir, recarregue a interface, abra nova
conversa, consulte o produto, pergunte sobre dinheiro e depois “E no PIX?”.
Nenhum commit, push, publicação, alteração de `.env` ou provedor externo foi feito.

[Evidência sanitizada](payment_scope_validation.json).

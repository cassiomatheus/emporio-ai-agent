# Contratos das ferramentas — Fase 05

Seis tools locais delegam aos serviços das Fases 03–04. Não há SDK, prompt,
loop de agente, API ou autenticação real. O registro tem uma lista fechada de
nomes; não há ferramenta SQL, acesso a arquivos por argumento ou execução de código.

Os JSON Schemas de entrada/saída estão em
[tool_contracts.json](tool_contracts.json), gerados por `tool_contracts()` em
`app/tools/registry.py`. Um teste confere que o artefato corresponde aos modelos.
Os schemas são independentes de provedor e ainda não foram adaptados/testados
contra o modo strict de uma API LLM específica.

## Entradas e retornos

Todos os parâmetros desconhecidos são recusados (`extra=forbid`). Argumentos
devem ser um objeto JSON nativo, não JSON textual ou instância já construída de
modelo. IDs são inteiros positivos de 64 bits, sem converter strings ou bools.
Texto obrigatório não pode ser vazio ou só espaços.

| Tool | Parâmetros | Dados de sucesso |
| --- | --- | --- |
| search_products | term ≤120; category ≤80 ou category_id; min_price/max_price; specs; available_only=true; status opcional; limit=10, offset=0 | items, total, limit, offset; cada item tem preço, status, estoque e disponibilidade |
| get_product_details | Exatamente um entre product_id e name completo ≤120 | Produto existente, inclusive motivo da indisponibilidade |
| get_product_offers | product_id; payment_method opcional: pix/credit/debit/boleto; installments opcional 1–12 | original_price, options, selected_plan, applied_rules |
| get_order_status | Somente order_id | Status, total histórico, itens e rastreio/previsão quando observados; sem PII de clientes ou notas |
| search_store_policies | query ≤500; top_k=3, entre 1 e 5 | hits com excerto breve, seção, página, versão, hash e grau lexical |
| get_store_info | subject: address, hours ou contacts | Entradas públicas com fonte e cautions de ambiguidades |

Dinheiro de entrada aceita inteiro ou string decimal com ponto, até duas casas
e limite compatível com o SQLite. Exemplos válidos: `800`, `"800"`, `"800.00"`.
Float, NaN, infinito, fração de centavo e negativo são recusados. Na saída JSON,
`Decimal` é serializado como string, preservando centavos, por exemplo `"323.10"`.

`specs` aceita até 10 pares: chave até 64 caracteres e valor escalar JSON finito;
strings até 120. Objetos/listas aninhados não são argumentos dessa busca.
Faixa invertida é inválida. A faixa considera preço de tabela, com limites inclusivos.

O contrato técnico também aceita `name_terms`: até quatro fragmentos de nome,
todos exigidos em conjunto com `term`. Isso permite combinar marca e subtipo
mesmo quando não aparecem lado a lado no nome. A orquestração oferece ao LLM um
contrato semântico para a mesma `search_products`, descrito em
[agent_tool_contracts.json](agent_tool_contracts.json). O mapper valida e converte
esse pedido para o contrato técnico antes da execução. As outras cinco ferramentas
mantêm os contratos anteriores. Callers Python diretos continuam usando filtros
técnicos; a compatibilidade na orquestração passa pelo mesmo normalizador.

`category` corresponde à categoria solicitada: ukuleles usam `Ukuleles`, sem
categoria padrão. `term` pesquisa o nome/modelo; o subtipo soprano, por exemplo,
é pesquisado como `term="soprano"`, sem acrescentar a palavra ukulele. Cor usa
`specs.color`, independentemente da madeira mencionada no nome. Não inventar
chaves como `size` para um subtipo que só está registrado no nome. Isso não cria
aliases nem remove filtros desconhecidos: o serviço continua aplicando os
parâmetros literalmente, sem relaxar condições para produzir resultados.

O nome de detalhes exige igualdade após normalizar caixa/acentos. Não usar
substring para escolher um item. Nome duplicado retorna `ambiguous`; informar ID
resolve a ambiguidade. Esse comportamento foi adicionado ao ProductService.

Sem modalidade, ofertas retorna as quatro opções e os planos elegíveis de
crédito. Com modalidade, retorna somente a cotação solicitada. `installments`
exige modalidade explícita, é 1–12 e só pode exceder 1 em crédito. Crédito sem
contagem usa 1x. Uma contagem inelegível retorna `invalid_installments`, sem
substituição silenciosa. Não há compra, reserva ou pagamento real.

## Envelope e erros

Sucesso contém `data` e `error=null`. Falha contém `data=null` e um erro tipado.
Entradas e saídas são validadas; saída malformada é falha técnica, não erro do usuário.

Exemplo de busca sem itens, que é sucesso:

```json
{
  "status": "ok",
  "data": {"items": [], "total": 0, "limit": 10, "offset": 0},
  "error": null
}
```

Exemplo de acesso sem autorização:

```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "forbidden",
    "message": "Pedido não encontrado ou sem autorização de acesso.",
    "invalid_fields": []
  }
}
```

| Código | Significado |
| --- | --- |
| unknown_tool | Nome fora da lista fechada |
| invalid_arguments | Formato, campo, faixa ou tamanho de entrada inválido |
| not_found | Produto inexistente ou nome completo sem correspondência |
| ambiguous | Nome normalizado corresponde a mais de um produto |
| unavailable | Produto não vendável no snapshot |
| invalid_installments | Quantidade de parcelas não elegível após desconto |
| forbidden | Pedido sem acesso autorizado, alheio ou inexistente |
| no_evidence | Políticas/dados da loja sem fonte suficiente |
| service_unavailable | Falha de serviço, saída inválida ou dependência documental ausente |
| response_too_large | Resultado excedeu o limite de serialização |

Mensagens são fixas. `invalid_fields` contém somente campos raiz conhecidos ou
`$`; valores, chaves privadas desconhecidas, SQL e exceções nunca são ecoados.
Não há logging de argumentos ou de resultados. Erros não incluem traceback nem
fallback com preço ou contato não verificado.

## Limites

- Entrada: até 8.192 bytes em JSON serializado UTF-8; objetos não JSON e números
  não finitos são recusados antes da execução.
- Saída: até 65.536 bytes serializados; não truncar silenciosamente uma resposta
  estruturada. Resultado grande retorna `response_too_large` sem dados parciais.
- Catálogo: 1–20 itens por página; offset 0–10.000; ordem e filtros do serviço.
- Políticas: 1–5 excertos, cada um até 420 caracteres, com limites e abstenção do
  retriever. Ausência de evidência é erro de domínio, não falha de carregamento.
- Dados da loja: até 8 entradas, valor de até 300 caracteres. Novo layout que
  exceder o contrato falha em vez de cortar um dado da fonte.
- Pedido: até 100 itens. Os dados atuais têm no máximo o conjunto pequeno do snapshot.

Timeout/rodadas do orquestrador não estão implementados, pois pertencem à Fase 06.
As tools não aceitam parâmetros que modifiquem banco, estoque, arquivo ou pedido.

## Autorização de pedidos

O schema público contém somente `order_id`. `order_access` é um argumento Python
separado de `ToolRegistry.call`, fornecido por backend de confiança. Ele nunca
deve ser derivado de um ID declarado pelo usuário ou de argumentos do futuro LLM.
O registro não memoriza o contexto entre chamadas.

Sem `OrderAccessContext` autorizado, a tool recusa antes de chamar o serviço.
O OrderService também verifica e o repositório filtra pelo dono no SQL. Pedido
alheio e inexistente têm exatamente o mesmo erro, sem expor existência ou dados.
Os testes criam contextos controlados; isso não representa autenticação real.
Sessões e vinculação da autorização no servidor permanecem para a Fase 07.

## Informação pública da loja

O PolicyService agora seleciona endereço e contatos da tabela 1.2, horários da
seção 2, WhatsApp da seção 7 e telefone/e-mail da capa. Cada valor preserva a
fonte e a referência; capa usa `section_id=null`. Não são retornados CNPJ,
razão social ou o manual integral. Não há constantes de contato como fallback.

As variantes do manual são mantidas. `conflicting_phone_numbers`,
`conflicting_emails` e `confirm_contacts_with_store` sinalizam divergências.
Horários incluem `special_hours_may_vary` e `not_an_open_now_check`; não há
afirmação de que a loja está aberta agora. Esse mapeamento é específico do manual
atual e precisa ser revisto em nova estrutura documental.

## Verificação

```bash
python -m pytest tests/unit/test_tools.py tests/integration/test_tools.py
python -m pytest
python -m pytest -m 'not local_data'
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

Testes unitários usam serviços com repositórios simulados e documento sintético.
Integração usa SQLite temporário e, quando disponíveis, os anexos privados.
Há cobertura de contratos das seis operações, parâmetros inválidos, limites,
ausências, falhas, saídas inválidas/grandes, autorização externa, SQL como texto,
nomes exatos/ambíguos, contatos divergentes e preservação dos snapshots.

A Fase 05 não adicionou dependências. Os serviços continuam utilizáveis
isoladamente; toda a suíte das fases anteriores permanece executável. O passo
seguinte é a Fase 06, somente quando solicitado, sem integração LLM nesta entrega.

## Resultados observados em 31/10/2026

Ambiente: Linux, Python 3.14.6, SQLite 3.53.2, PyMuPDF 1.28.2,
pytest 9.2.0 e Ruff 0.17.3.

| Verificação | Resultado real final |
| --- | --- |
| pytest completo | 238 passed em 2,51 s, sem warnings |
| pytest -m 'not local_data' | 204 passed, 34 deselected em 1,39 s, sem warnings |
| Casos adicionados de tools | 62, incluindo 58 unitários e 4 de integração |
| ruff check . | All checks passed |
| ruff format --check . | Aprovado |
| Imports, entrada mínima e pip check | Aprovados |
| Contratos documentados vs modelos | Igualdade verificada por teste |

Um teste com modelo propositalmente malformado inicialmente gerou aviso do
serializador com o valor inválido. A fronteira foi corrigida para converter
warnings de serialização em erro sanitizado, e a execução final não emitiu
warnings. Há teste de regressão verificando a ausência desses avisos.

No snapshot original, a tool de busca retornou os violões de nylon disponíveis
até R$ 800 (IDs 83, 85, 81, 84), ofertas do produto 127 mantiveram R$ 323,10 no
PIX, pedido autorizado sem rastreio preservou a ausência e dados da loja
mantiveram fontes e alertas de contatos divergentes. Nenhum dado de cliente foi
necessário para documentar os resultados. Não houve alteração nos snapshots,
publicação ou commit automático. Outras versões de Python não foram testadas.

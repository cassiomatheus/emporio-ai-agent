# Qualidade dos dados — Fase 02

Inspeção executada em 31/10/2026, sobre os seis CSVs fornecidos e copiados
sem alteração para `data/raw/`. Evidência reproduzível por
`python scripts/inspect_data.py --report docs/data_quality.json`.
O [relatório JSON](data_quality.json) registra schemas, contagens, nulos,
hashes SHA-256 e diagnósticos sem expor linhas ou contatos de clientes.

## Resultado observado

| Tabela | Registros | Colunas | Duplicatas de chave | Linhas inválidas |
| --- | ---: | ---: | ---: | ---: |
| categories | 9 | 3 | 0 | 0 |
| products | 65 | 9 | 0 | 0 |
| customers | 50 | 5 | 0 | 0 |
| orders | 20 | 10 | 0 | 0 |
| order_items | 22 | 3 | 0 | 0 |
| promotions | 25 | 5 | 0 | 0 |

Todos os cinco relacionamentos foram verificados, sem IDs órfãos:
products→categories; orders→customers; order_items→orders;
order_items→products; promotions→products. A chave composta dos itens é única.

Há 12 nulos em `orders.tracking_code`, 12 em `estimated_delivery` e 16 em `notes`.
Os demais campos não apresentam vazios. Os 65 campos `specs` contêm objetos JSON
válidos. Não houve erro bloqueante de schema, tipo ou valor.

Produtos: 62 `active`, 2 `discontinued`, 1 `coming_soon`; dois têm estoque zero.
Os produtos 130 (`coming_soon`, estoque 2) e 136 (`discontinued`, estoque 13)
permanecem com seus estados e quantidades originais. Esse diagnóstico não
implementa a decisão comercial de disponibilidade.

Promoções: 4 ativas e 21 inativas; não há datas de vigência na fonte. O produto
127 mantém preço de tabela de R$ 359 e promoção ativa de 10%. Aplicação dos
descontos e condições de pagamento pertence à Fase 03.

Pedidos: 7 `delivered`, 4 `confirmed`, 4 `pending`, 4 `cancelled`, 1 `shipped`.
Datas entre 15/10/2025 e 22/03/2026. Não há data observada de recebimento real.
Nos pedidos 3 e 20, a soma com preços atuais supera o total histórico em R$ 48
e R$ 88. Esses são diagnósticos derivados; todos os totais originais foram
preservados exatamente em centavos, sem recálculo.

## Ingestão e verificação executadas

Executado `python scripts/ingest_data.py` duas vezes em `data/emporio.sqlite3`.
Ambas retornaram contagens 9/65/50/20/22/25 e zero violações de FK. O SHA-256
do dump lógico foi idêntico entre as execuções; não houve duplicação.
`PRAGMA foreign_key_check` retornou zero linhas e `PRAGMA integrity_check`, `ok`.

Ambiente observado: Linux, Python 3.14.6, SQLite 3.53.2, pytest 9.2.0, Ruff 0.17.3.
A primeira execução da suíte passou com 64 testes em 1,09 s, incluindo os quatro
testes da Fase 01 e um teste de aceite do snapshot privado. Foram exercitados:
preservação de fontes e valores; idempotência; atualização/remoção no snapshot;
FKs e chaves duplicadas; dinheiro/JSON/datas inválidos; restrições do banco;
sanitização de relatórios; scripts; e rollback após falha no fim da transação.

As fixtures de `data/samples/` são sintéticas e não têm as contagens do snapshot
original. A suíte pública pode ser executada offline com
`python -m pytest -m 'not local_data'`. As evidências deste arquivo se referem
somente à engenharia de dados; não avaliam serviços comerciais, autorização,
qualidade de respostas, LLM ou API.

A execução offline também foi realizada: 63 testes passaram, com 1 teste local
desmarcado, em 1,05 s. Lint e formatação passaram; importação dos novos módulos
e a entrada mínima funcionaram, e `pip check` não encontrou dependências quebradas.

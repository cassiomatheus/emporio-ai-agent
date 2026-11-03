# Serviços determinísticos — Fase 03

Os serviços dependem de contratos de repositório, não de SQLite diretamente,
LLM, prompts, tools ou interface. Não foi adicionada dependência de instalação.
Os repositórios concretos usam consultas parametrizadas e conexões somente leitura.

| Componente | Operação | Resultado |
| --- | --- | --- |
| ProductService | search(ProductSearch), get_product(id) | Página filtrada ou detalhes com disponibilidade e motivo |
| PricingService | get_offers(id), quote(QuoteRequest) | Ofertas por modalidade e cotação com plano de parcelas elegível |
| OrderService | get_status(id, access=context) | Dados mínimos do pedido previamente autorizado |

Os contratos ficam em `app/services/models.py` e os erros de domínio em
`app/services/errors.py`. Erros têm códigos estáveis: `not_found`, `unavailable`,
`invalid_installments`, `forbidden` e `service_unavailable`. Entradas inválidas
falham na validação Pydantic. Não há fallback para preço sem consulta válida.

## Regras e limites

Busca considera nome, categoria, faixa inclusiva de preço de tabela e valores
observados de `specs`. Por padrão, retorna apenas `active` com estoque positivo.
Paginação e ordem preço/ID são estáveis; a comparação textual ignora caixa e
acentos. Categoria usa igualdade; nome usa substring. Não há inferência semântica.

Promoções inativas são ignoradas. Uma única promoção ativa é comparada ao PIX
isolado de 5%; não há acumulação. O desconto usa `Decimal` e `ROUND_HALF_UP`.
Para o Kalani 127: R$ 359,00 → 10% → R$ 323,10, inclusive no PIX.

Parcelas são calculadas após o desconto: 4–6x exigem R$ 80 e 7–12x, R$ 100 por
parcela. Em 2–3x, adotou-se piso conservador de R$ 50; 1x é à vista. Essa
interpretação e a precedência da seção 3.1 sobre a tabela geral do manual estão
documentadas em DEC-14. Os centavos são distribuídos sem alterar o total ou
os juros. O serviço recusa contagem de parcelas inválida, sem substituí-la
silenciosamente por outra.

Pedidos exigem contexto autorizado injetado pelo backend. Dicionário ou ID de
cliente declarado não concede acesso. A checagem ocorre antes da consulta e
o SQL limita pedido e itens ao dono autorizado. Não há autenticação real ou
sessões implementadas. Dados pessoais de clientes e notas internas são omitidos;
total histórico, ausência de rastreamento e ausência de previsão são preservados.

## Verificação

```bash
python -m pytest tests/unit
python -m pytest tests/integration/test_services.py
python -m pytest
python -m pytest -m 'not local_data'
python -m ruff check .
python -m ruff format --check .
```

Testes unitários usam repositórios simulados sem SQLite. Testes de integração
usam bases temporárias com fixtures sintéticas; o aceite marcado `local_data`
usa os originais apenas quando disponíveis. As fases anteriores permanecem
na suíte. Não são feitas chamadas de rede.

| Aceite | Evidência automatizada |
| --- | --- |
| CA-01 | Filtros combinados e violões de nylon até R$ 800 no snapshot original |
| CA-02/03 | Estoque zero, discontinued com 13 unidades e coming_soon com 2 não geram oferta |
| CA-04 | Produto 127, 10% ativo, R$ 323,10 e PIX sem acumulação |
| CA-05 | Limites imediatamente abaixo/no piso; mínimos aplicados após desconto |
| CA-07 | Ausência de autorização não consulta; SQL por dono; alheio/inexistente indistinguíveis |
| CA-08 | Rastreio ausente permanece None; nenhum código ou prazo inventado |

As evidências cobrem o comportamento dos serviços, sem medir orquestração de
agente ou respostas em linguagem natural. O detalhamento das decisões está em
[decisions.md](decisions.md), DEC-13 a DEC-16. A próxima fase é a Fase 04.

## Resultados observados em 31/10/2026

Ambiente: Linux, Python 3.14.6, SQLite 3.53.2, pytest 9.2.0 e Ruff 0.17.3.

| Comando | Resultado observado |
| --- | --- |
| pytest tests/unit | 51 passed em 0,12 s, sem SQLite |
| pytest | 121 passed em 1,22 s, incluindo as fases anteriores e o snapshot original |
| pytest -m 'not local_data' | 119 passed, 2 deselected em 1,21 s |
| ruff check . | All checks passed |
| ruff format --check . | Aprovado |
| pip check | No broken requirements found |
| Imports dos serviços/repositórios e entrada mínima | Aprovados |

No snapshot original, violões de nylon disponíveis até R$ 800 retornaram IDs
83, 85, 81 e 84 em ordem de preço. O produto 127 manteve R$ 359,00 de tabela,
10% de promoção e R$ 323,10 final no PIX. Os produtos 130 e 136 não geraram
oferta apesar do estoque positivo. Os pedidos 3 e 20 mantiveram seus totais
históricos, e um pedido sem rastreio preservou a ausência de código. Não foram
impressos contatos ou dados de clientes para registrar essas evidências.

Além dos testes unitários, os testes de integração verificaram consultas
parametrizadas, bloqueio de escrita em conexão somente leitura, banco ausente
sem criação de arquivo, escopo por dono e preservação do arquivo SQLite nas
consultas. Outras versões de Python e autenticação/sessões reais não foram testadas.

# Catálogo

**SIMULAÇÃO EXECUTADA — LLM roteirizado, sem API real.**

Serviços, SQLite, autorização e cálculo são reais; dados e PDF são sintéticos.
As chamadas foram predeterminadas no roteiro. Isto não demonstra seleção
autônoma do modelo nem substitui os resultados 25/40 da Fase 09.

## Contexto

Regras/fontes: RN-01/02/10: apenas ativo com estoque; filtro calculado pelo serviço.

Fonte: `data/samples`; políticas em PDF sintético v0.1 gerado temporariamente.
Não usa CSV/PDF interno, PII original, token ou ID de sessão publicado.
Sessão visitante, sem concessão de pedidos.

## Turno 1

**Cliente:** Quais instrumentos de nylon disponíveis custam até R$ 1.000?

**Assistente (saída capturada):**

Olá! Consultei as fontes da loja para você.

Estas são as opções consultadas no snapshot:
- Instrumento sintético disponível (ID 102): R$ 250,00; disponível; estoque registrado: 4.

Status: `answered`. Chamadas ao provedor mock: 2.

Tools e resultados estruturados sanitizados:

```json
[
  {
    "tool": "search_products",
    "arguments": {
      "max_price": "1000",
      "specs": {
        "strings": "nylon"
      },
      "available_only": true
    },
    "result": {
      "status": "ok",
      "data": {
        "items": [
          {
            "product_id": 102,
            "name": "Instrumento sintético disponível",
            "category_id": 1,
            "category_name": "Cordas sintéticas",
            "price_brl": "250.00",
            "description": "Exemplo de produto ativo",
            "stock_quantity": 4,
            "status": "active",
            "specs": {
              "color": "azul",
              "strings": "nylon"
            },
            "available": true,
            "availability_reason": "available"
          }
        ],
        "total": 1,
        "limit": 10,
        "offset": 0
      },
      "error": null
    }
  }
]
```

## Interpretação e limites

RN-01/02/10: apenas ativo com estoque; filtro calculado pelo serviço.
Uma falha de tool pode produzir encaminhamento genérico: a tool registra o
motivo, mas o texto controlado não explica todos os detalhes. Não promete
compra, pagamento, devolução aprovada ou operação externa.

Reprodução: `python scripts/generate_examples.py --output /tmp/emporio-exemplos`.

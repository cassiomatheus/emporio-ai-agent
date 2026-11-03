# Pedido protegido

**SIMULAÇÃO EXECUTADA — LLM roteirizado, sem API real.**

Serviços, SQLite, autorização e cálculo são reais; dados e PDF são sintéticos.
As chamadas foram predeterminadas no roteiro. Isto não demonstra seleção
autônoma do modelo nem substitui os resultados 25/40 da Fase 09.

## Contexto

Regras/fontes: RN-09/14 e DEC-07: concessão fixa do backend para fixture 1; total histórico preservado, sem rastreio; pedido alheio negado.

Fonte: `data/samples`; políticas em PDF sintético v0.1 gerado temporariamente.
Não usa CSV/PDF interno, PII original, token ou ID de sessão publicado.
Concessão demonstrativa: cliente sintético 1, definida no backend; não autentica pessoas.

## Turno 1

**Cliente:** Consulte pedido 1.

**Assistente (saída capturada):**

Olá! Consultei as fontes da loja para você.

Pedido 1: entregue no snapshot; total histórico R$ 999,90.
O snapshot não informa código de rastreamento.
O snapshot não informa previsão de entrega.

Status: `answered`. Chamadas ao provedor mock: 2.

Tools e resultados estruturados sanitizados:

```json
[
  {
    "tool": "get_order_status",
    "arguments": {
      "order_id": 1
    },
    "result": {
      "status": "ok",
      "data": {
        "order_id": 1,
        "order_date": "2026-02-01",
        "status": "delivered",
        "total_brl": "999.90",
        "payment_method": "pix",
        "tracking_code": null,
        "estimated_delivery": null,
        "tracking_status": "not_provided",
        "items": [
          {
            "product_id": 102,
            "name": "Instrumento sintético disponível",
            "quantity": 2
          },
          {
            "product_id": 127,
            "name": "Instrumento sintético em oferta",
            "quantity": 1
          }
        ]
      },
      "error": null
    }
  }
]
```

## Turno 2

**Cliente:** Consulte pedido 2.

**Assistente (saída capturada):**

Esse caso precisa ser conferido por um atendente da loja. Não consigo confirmar uma decisão com os dados disponíveis.

Status: `answered`. Chamadas ao provedor mock: 2.

Tools e resultados estruturados sanitizados:

```json
[
  {
    "tool": "get_order_status",
    "arguments": {
      "order_id": 2
    },
    "result": {
      "status": "error",
      "data": null,
      "error": {
        "code": "forbidden",
        "message": "Pedido não encontrado ou sem autorização de acesso.",
        "invalid_fields": []
      }
    }
  }
]
```

## Interpretação e limites

RN-09/14 e DEC-07: concessão fixa do backend para fixture 1; total histórico preservado, sem rastreio; pedido alheio negado.
Uma falha de tool pode produzir encaminhamento genérico: a tool registra o
motivo, mas o texto controlado não explica todos os detalhes. Não promete
compra, pagamento, devolução aprovada ou operação externa.

Reprodução: `python scripts/generate_examples.py --output /tmp/emporio-exemplos`.

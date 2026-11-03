# Promoção e pagamento

**SIMULAÇÃO EXECUTADA — LLM roteirizado, sem API real.**

Serviços, SQLite, autorização e cálculo são reais; dados e PDF são sintéticos.
As chamadas foram predeterminadas no roteiro. Isto não demonstra seleção
autônoma do modelo nem substitui os resultados 25/40 da Fase 09.

## Contexto

Regras/fontes: RN-03/04/05/11: 359,00 → 323,10 com 10%, sem PIX adicional; 3x107,70 válido, 6x recusado.

Fonte: `data/samples`; políticas em PDF sintético v0.1 gerado temporariamente.
Não usa CSV/PDF interno, PII original, token ou ID de sessão publicado.
Sessão visitante, sem concessão de pedidos.

## Turno 1

**Cliente:** Mostre detalhes e oferta PIX do produto 127.

**Assistente (saída capturada):**

Olá! Consultei as fontes da loja para você.

Detalhes verificados no snapshot:
- Instrumento sintético em oferta (ID 127): R$ 359,00; disponível; estoque registrado: 11.

Produto 127: preço de tabela R$ 359,00.
- PIX: R$ 323,10 (10% de desconto, sem acumulação).
Condições calculadas sobre o snapshot; PIX e promoção não se somam.

Status: `answered`. Chamadas ao provedor mock: 2.

Tools e resultados estruturados sanitizados:

```json
[
  {
    "tool": "get_product_details",
    "arguments": {
      "product_id": 127
    },
    "result": {
      "status": "ok",
      "data": {
        "product_id": 127,
        "name": "Instrumento sintético em oferta",
        "category_id": 1,
        "category_name": "Cordas sintéticas",
        "price_brl": "359.00",
        "description": "Exemplo de promoção",
        "stock_quantity": 11,
        "status": "active",
        "specs": {
          "type": "tenor"
        },
        "available": true,
        "availability_reason": "available"
      },
      "error": null
    }
  },
  {
    "tool": "get_product_offers",
    "arguments": {
      "product_id": 127,
      "payment_method": "pix"
    },
    "result": {
      "status": "ok",
      "data": {
        "product_id": 127,
        "original_price": "359.00",
        "options": [
          {
            "payment_method": "pix",
            "discount_percent": "10",
            "final_price": "323.10",
            "discount_source": "promotion",
            "promotion_id": 1,
            "eligible_installments": []
          }
        ],
        "selected_plan": null,
        "applied_rules": [
          "RN-01",
          "RN-02",
          "RN-03",
          "RN-04",
          "RN-05",
          "RN-11"
        ]
      },
      "error": null
    }
  }
]
```

## Turno 2

**Cliente:** E em 3x?

**Assistente (saída capturada):**

Olá! Consultei as fontes da loja para você.

Produto 127: preço de tabela R$ 359,00.
- cartão de crédito: R$ 323,10 (10% de desconto, sem acumulação).
  Parcelas elegíveis: 1x, 2x, 3x, 4x, sem juros.
Plano de 3x: R$ 107,70, R$ 107,70, R$ 107,70; total R$ 323,10.
Condições calculadas sobre o snapshot; PIX e promoção não se somam.

Status: `answered`. Chamadas ao provedor mock: 2.

Tools e resultados estruturados sanitizados:

```json
[
  {
    "tool": "get_product_offers",
    "arguments": {
      "product_id": 127,
      "payment_method": "credit",
      "installments": 3
    },
    "result": {
      "status": "ok",
      "data": {
        "product_id": 127,
        "original_price": "359.00",
        "options": [
          {
            "payment_method": "credit",
            "discount_percent": "10",
            "final_price": "323.10",
            "discount_source": "promotion",
            "promotion_id": 1,
            "eligible_installments": [
              {
                "count": 1,
                "amounts": [
                  "323.10"
                ],
                "total_brl": "323.10",
                "minimum_brl": "0.00",
                "interest_percent": "0"
              },
              {
                "count": 2,
                "amounts": [
                  "161.55",
                  "161.55"
                ],
                "total_brl": "323.10",
                "minimum_brl": "50.00",
                "interest_percent": "0"
              },
              {
                "count": 3,
                "amounts": [
                  "107.70",
                  "107.70",
                  "107.70"
                ],
                "total_brl": "323.10",
                "minimum_brl": "50.00",
                "interest_percent": "0"
              },
              {
                "count": 4,
                "amounts": [
                  "80.78",
                  "80.78",
                  "80.77",
                  "80.77"
                ],
                "total_brl": "323.10",
                "minimum_brl": "80.00",
                "interest_percent": "0"
              }
            ]
          }
        ],
        "selected_plan": {
          "count": 3,
          "amounts": [
            "107.70",
            "107.70",
            "107.70"
          ],
          "total_brl": "323.10",
          "minimum_brl": "50.00",
          "interest_percent": "0"
        },
        "applied_rules": [
          "RN-01",
          "RN-02",
          "RN-03",
          "RN-04",
          "RN-05",
          "RN-11"
        ]
      },
      "error": null
    }
  }
]
```

## Turno 3

**Cliente:** E em 6x?

**Assistente (saída capturada):**

Esse caso precisa ser conferido por um atendente da loja. Não consigo confirmar uma decisão com os dados disponíveis.

Status: `answered`. Chamadas ao provedor mock: 2.

Tools e resultados estruturados sanitizados:

```json
[
  {
    "tool": "get_product_offers",
    "arguments": {
      "product_id": 127,
      "payment_method": "credit",
      "installments": 6
    },
    "result": {
      "status": "error",
      "data": null,
      "error": {
        "code": "invalid_installments",
        "message": "Parcelamento não elegível para esse valor.",
        "invalid_fields": []
      }
    }
  }
]
```

## Interpretação e limites

RN-03/04/05/11: 359,00 → 323,10 com 10%, sem PIX adicional; 3x107,70 válido, 6x recusado.
Uma falha de tool pode produzir encaminhamento genérico: a tool registra o
motivo, mas o texto controlado não explica todos os detalhes. Não promete
compra, pagamento, devolução aprovada ou operação externa.

Reprodução: `python scripts/generate_examples.py --output /tmp/emporio-exemplos`.

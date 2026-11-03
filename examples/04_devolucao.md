# Devolução

**SIMULAÇÃO EXECUTADA — LLM roteirizado, sem API real.**

Serviços, SQLite, autorização e cálculo são reais; dados e PDF são sintéticos.
As chamadas foram predeterminadas no roteiro. Isto não demonstra seleção
autônoma do modelo nem substitui os resultados 25/40 da Fase 09.

## Contexto

Regras/fontes: RN-06/07 e DEC-08: 7 dias do recebimento; troca em 30 dias da compra e garantia de 90 do recebimento são distintas; pedir data real.

Fonte: `data/samples`; políticas em PDF sintético v0.1 gerado temporariamente.
Não usa CSV/PDF interno, PII original, token ou ID de sessão publicado.
Sessão visitante, sem concessão de pedidos.

## Turno 1

**Cliente:** Quais são os prazos de arrependimento, troca por defeito e garantia legal?

**Assistente (saída capturada):**

Olá! Consultei as fontes da loja para você.

Encontrei estas referências no manual:
- [politicas_sinteticas.pdf, seção 4.1, p. 4, v. 0.1] Compra online: ate 7 dias corridos do recebimento real. Embalagem original, sem uso, com componentes. Loja paga retorno. Reembolso na mesma modalidade em ate 10 dias uteis.
São referências; a aplicação depende das condições do caso.

Encontrei estas referências no manual:
- [politicas_sinteticas.pdf, seção 4.2, p. 5, v. 0.1] Troca por defeito de fabricacao em ate 30 dias da compra. Procedimento distinto da garantia legal de 90 dias do recebimento.
- [politicas_sinteticas.pdf, seção 8.1, p. 8, v. 0.1] Garantia legal de 90 dias a partir do recebimento, para defeito de fabricacao. Nao confundir com troca em 30 dias da compra.
São referências; a aplicação depende das condições do caso.

Status: `answered`. Chamadas ao provedor mock: 2.

Tools e resultados estruturados sanitizados:

```json
[
  {
    "tool": "search_store_policies",
    "arguments": {
      "query": "prazo de arrependimento em compra online após receber o produto",
      "top_k": 3
    },
    "result": {
      "status": "ok",
      "data": {
        "status": "matched",
        "hits": [
          {
            "chunk_id": "cf4a2d0aad20:4.1:1",
            "metadata": {
              "source_name": "politicas_sinteticas.pdf",
              "source_sha256": "cf4a2d0aad20a262ba96b3e12a9d56fcee75fae3d252228723911acfc3708cc0",
              "version": "0.1",
              "section_id": "4.1",
              "section_title": "Devolucao por arrependimento",
              "section_path": [
                "4.1 Devolucao por arrependimento"
              ],
              "pages": [
                4
              ],
              "section_pages": [
                4
              ]
            },
            "excerpt": "Compra online: ate 7 dias corridos do recebimento real. Embalagem original, sem uso, com componentes. Loja paga retorno. Reembolso na mesma modalidade em ate 10 dias uteis.",
            "excerpt_truncated": false,
            "score": 7.471554,
            "lexical_coverage": 0.8,
            "match_grade": "strong"
          }
        ]
      },
      "error": null
    }
  },
  {
    "tool": "search_store_policies",
    "arguments": {
      "query": "Troca por defeito em 30 dias é a mesma coisa que garantia legal de 90 dias?",
      "top_k": 3
    },
    "result": {
      "status": "ok",
      "data": {
        "status": "matched",
        "hits": [
          {
            "chunk_id": "cf4a2d0aad20:4.2:1",
            "metadata": {
              "source_name": "politicas_sinteticas.pdf",
              "source_sha256": "cf4a2d0aad20a262ba96b3e12a9d56fcee75fae3d252228723911acfc3708cc0",
              "version": "0.1",
              "section_id": "4.2",
              "section_title": "Troca por defeito",
              "section_path": [
                "4.2 Troca por defeito"
              ],
              "pages": [
                5
              ],
              "section_pages": [
                5
              ]
            },
            "excerpt": "Troca por defeito de fabricacao em ate 30 dias da compra. Procedimento distinto da garantia legal de 90 dias do recebimento.",
            "excerpt_truncated": false,
            "score": 12.26901,
            "lexical_coverage": 0.875,
            "match_grade": "strong"
          },
          {
            "chunk_id": "cf4a2d0aad20:8.1:1",
            "metadata": {
              "source_name": "politicas_sinteticas.pdf",
              "source_sha256": "cf4a2d0aad20a262ba96b3e12a9d56fcee75fae3d252228723911acfc3708cc0",
              "version": "0.1",
              "section_id": "8.1",
              "section_title": "Garantia legal",
              "section_path": [
                "8.1 Garantia legal"
              ],
              "pages": [
                8
              ],
              "section_pages": [
                8
              ]
            },
            "excerpt": "Garantia legal de 90 dias a partir do recebimento, para defeito de fabricacao. Nao confundir com troca em 30 dias da compra.",
            "excerpt_truncated": false,
            "score": 12.26901,
            "lexical_coverage": 0.875,
            "match_grade": "strong"
          }
        ]
      },
      "error": null
    }
  }
]
```

## Turno 2

**Cliente:** Posso devolver? Não sei quando recebi minha compra online.

**Assistente (saída capturada):**

Em que data você recebeu o produto? Para avaliar a devolução, também precisamos conferir as condições do caso com a loja. A data do pedido e a previsão de entrega não comprovam o recebimento.

Status: `answered`. Chamadas ao provedor mock: 1.

Tools e resultados estruturados sanitizados:

```json
[]
```

## Interpretação e limites

RN-06/07 e DEC-08: 7 dias do recebimento; troca em 30 dias da compra e garantia de 90 do recebimento são distintas; pedir data real.
Uma falha de tool pode produzir encaminhamento genérico: a tool registra o
motivo, mas o texto controlado não explica todos os detalhes. Não promete
compra, pagamento, devolução aprovada ou operação externa.

Reprodução: `python scripts/generate_examples.py --output /tmp/emporio-exemplos`.

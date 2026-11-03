"""Somente dados verificados das tools viram afirmações factuais ao usuário."""

from collections import Counter
from decimal import Decimal

from app.agent.models import AnswerPlan
from app.retrieval.models import ChunkMetadata
from app.services.models import ProductDetails
from app.services.policy_service import StoreInfoSource
from app.tools.schemas import ToolResponse


class UngroundedAnswer(ValueError):
    pass


def brl(value: Decimal) -> str:
    formatted = format(value, ",.2f").replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


def _product(product: ProductDetails) -> str:
    reasons = {
        "available": "disponível",
        "out_of_stock": "sem estoque",
        "discontinued": "descontinuado, indisponível",
        "coming_soon": "em breve, indisponível",
    }
    return (
        f"- {product.name} (ID {product.product_id}): {brl(product.price_brl)}; "
        f"{reasons[product.availability_reason]}; estoque registrado: {product.stock_quantity}."
    )


def _source(metadata: ChunkMetadata | StoreInfoSource) -> str:
    section = f"seção {metadata.section_id}" if metadata.section_id else "capa"
    pages = ", ".join(str(page) for page in metadata.pages)
    version = metadata.version or "não identificada"
    return f"{metadata.source_name}, {section}, p. {pages}, v. {version}"


def _facts(name: str, response: ToolResponse, *, pagination_hint: bool = True) -> str:
    data = response.data
    if name == "search_products":
        if not data.items:
            if data.offset:
                return "Não há mais resultados para estes filtros no snapshot consultado."
            return "Não encontrei produtos que atendam aos filtros consultados no snapshot."
        lines = [
            "Encontrei este instrumento no catálogo consultado:"
            if data.total == 1
            else "Estas são as opções consultadas no snapshot:"
        ]
        lines.extend(_product(product) for product in data.items)
        end = data.offset + len(data.items)
        if data.offset > 0 or data.total > data.limit:
            lines.append(f"Mostrando {data.offset + 1} a {end} de {data.total} resultados.")
            if end < data.total:
                lines.append(
                    "Digite 'continuar' para ver a próxima página."
                    if pagination_hint
                    else "Há outros resultados; faça uma busca por vez para continuar."
                )
            else:
                lines.append("Esta é a última página desta busca.")
        return "\n".join(lines)
    if name == "get_product_details":
        return "Detalhes verificados no snapshot:\n" + _product(data)
    if name == "get_product_offers":
        methods = {
            "pix": "PIX",
            "credit": "cartão de crédito",
            "debit": "débito",
            "boleto": "boleto",
        }
        lines = [f"Produto {data.product_id}: preço de tabela {brl(data.original_price)}."]
        for option in data.options:
            lines.append(
                f"- {methods[option.payment_method]}: {brl(option.final_price)} "
                f"({option.discount_percent}% de desconto, sem acumulação)."
            )
            if option.eligible_installments:
                plans = option.eligible_installments
                lines.extend(
                    (
                        f"Parcelamento sem juros: até {max(plan.count for plan in plans)}x.",
                        "",
                        "| Parcelas | Valor de cada parcela |",
                        "| --- | --- |",
                    )
                )
                varying = False
                for plan in plans:
                    low, high = min(plan.amounts), max(plan.amounts)
                    value = brl(low) if low == high else f"{brl(low)} a {brl(high)}"
                    varying = varying or low != high
                    lines.append(f"| {plan.count}x | {value} |")
                lines.append("")
                if varying:
                    lines.append(
                        "Os intervalos indicam ajuste de centavos entre parcelas; "
                        "o total da compra é preservado."
                    )
        if data.selected_plan:
            amounts = " + ".join(
                f"{count} × {brl(amount)}"
                for amount, count in Counter(data.selected_plan.amounts).items()
            )
            lines.append(
                f"Plano de {data.selected_plan.count}x: {amounts}; "
                f"total {brl(data.selected_plan.total_brl)}."
            )
        lines.append("Condições calculadas sobre o snapshot; PIX e promoção não se somam.")
        return "\n".join(lines)
    if name == "get_order_status":
        statuses = {
            "delivered": "entregue",
            "confirmed": "confirmado",
            "pending": "pendente",
            "cancelled": "cancelado",
            "shipped": "enviado",
        }
        lines = [
            f"Pedido {data.order_id}: {statuses[data.status]} no snapshot; "
            f"total histórico {brl(data.total_brl)}."
        ]
        lines.append(
            f"Rastreamento: {data.tracking_code}."
            if data.tracking_code is not None
            else "O snapshot não informa código de rastreamento."
        )
        lines.append(
            f"Previsão registrada: {data.estimated_delivery.isoformat()}."
            if data.estimated_delivery
            else "O snapshot não informa previsão de entrega."
        )
        return "\n".join(lines)
    if name == "search_store_policies":
        lines = ["Encontrei estas referências no manual:"]
        for hit in data.hits:
            lines.append(f"- [{_source(hit.metadata)}] {hit.excerpt}")
        lines.append("São referências; a aplicação depende das condições do caso.")
        return "\n".join(lines)
    if name == "get_store_info":
        lines = [
            f"- {entry.label}: {entry.value} [{_source(entry.source)}]" for entry in data.entries
        ]
        if any(code.startswith("conflicting_") for code in data.cautions):
            lines.append("O manual tem contatos divergentes; confirme o canal com a loja.")
        if "not_an_open_now_check" in data.cautions:
            lines.append(
                "Horários especiais podem variar; isto não confirma que a loja está aberta agora."
            )
        return "\n".join(lines)
    raise UngroundedAnswer("unsupported_evidence")


def render_plan(plan: AnswerPlan, evidence: dict[str, tuple[str, ToolResponse]]) -> str:
    if plan.intent == "greeting":
        return "Olá! Sou o assistente do Empório da Música. Como posso ajudar?"
    if plan.intent == "out_of_scope":
        return (
            "A Empório da Música trabalha com instrumentos musicais. "
            "Para acessórios ou outro assunto, procure um atendimento especializado."
        )
    if plan.intent == "handoff":
        return (
            "Esse caso precisa ser conferido por um atendente da loja. "
            "Não consigo confirmar uma decisão com os dados disponíveis."
        )
    if plan.intent == "clarify":
        return {
            "product": "Qual instrumento ou modelo você procura?",
            "category": "Que tipo de instrumento você procura?",
            "budget": "Qual é o seu orçamento?",
            "specs": "Qual característica é indispensável para você?",
            "rephrase": "Pode explicar um pouco melhor o que você precisa?",
            "receipt_date": (
                "Em que data você recebeu o produto? Para avaliar a devolução, "
                "também precisamos conferir as condições do caso com a loja. "
                "A data do pedido e a previsão de entrega não comprovam o recebimento."
            ),
        }[plan.clarification]
    parts = []
    for call_id in plan.evidence_call_ids:
        entry = evidence.get(call_id)
        if entry is None or entry[1].status != "ok":
            raise UngroundedAnswer("unverified_evidence")
        parts.append(_facts(*entry, pagination_hint=len(plan.evidence_call_ids) == 1))
    text = "Olá! Consultei as fontes da loja para você.\n\n" + "\n\n".join(parts)
    if len(text) > 8000:
        raise UngroundedAnswer("answer_too_large")
    return text

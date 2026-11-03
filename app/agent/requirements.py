"""Pré-condições conservadoras de evidência para devoluções e pagamentos."""

import re

from app.agent.security import normalized

_RETURN = re.compile(r"\b(?:devolv\w*|devolucao|arrependimento)\b")
_PAYMENT = re.compile(
    r"\b(?:descont\w*|parcel\w*|pagamento(?:s)?|pagar|pagando|pagasse|pagaria|"
    r"pix|boleto|cartao|debito|credito)\b"
)
_CASH = re.compile(r"\b(?:dinheiro|especie)\b")
_CASH_FORM = re.compile(r"\b(?:(?:em|com) dinheiro|em especie|dinheiro vivo)\b")
_MISSING_RECEIPT = re.compile(
    r"\b(?:nao sei|nao lembro|nao recordo|desconheco)\s+"
    r"(?:(?:exatamente|ao certo)\s+)?quando\s+(?:recebi|chegou|foi entregue)\b"
    r"|\b(?:nao tenho|nao sei|nao lembro|nao recordo|sem(?: saber)?)\s+"
    r"(?:a\s+)?data\b.{0,60}\b(?:recebimento|entrega)\b"
    r"|\bdata\b.{0,30}\b(?:recebimento|entrega)\b.{0,25}"
    r"\b(?:desconhecida|incerta|nao informada)\b",
    re.DOTALL,
)


def needs_receipt_date(message: str) -> bool:
    """Não infere datas, elegibilidade ou uma intenção geral a partir do histórico."""
    text = normalized(message)
    return bool(_RETURN.search(text) and _MISSING_RECEIPT.search(text))


def asks_payment_terms(message: str) -> bool:
    """Indício lexical só impede descarte como fora do escopo; não autoriza fatos."""
    return bool(_PAYMENT.search(normalized(message)))


def mentions_cash(text: str) -> bool:
    """Identifica a modalidade na pergunta ou no excerto, sem inferir desconto."""
    return bool(_CASH.search(normalized(text)))


def needs_cash_policy(message: str) -> bool:
    text = normalized(message)
    return bool(_CASH_FORM.search(text) or mentions_cash(text) and asks_payment_terms(text))

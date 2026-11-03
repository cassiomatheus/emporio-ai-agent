"""Filtros auxiliares. Autorização, schemas e evidências são as barreiras centrais."""

import re
import unicodedata


def normalized(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char) and unicodedata.category(char) != "Cf"
    )


_INJECTION = re.compile(
    r"(?:ignore|ignorar|desconsidere|esqueca|override|disregard).{0,100}"
    r"(?:instru|regras|rules|system|sistema|prompt|previous|fontes)"
    r"|(?:revele|mostre|exiba|reveal|print|dump).{0,70}"
    r"(?:system.prompt|prompt.do.sistema|segredo|secret|api.key|credencia|senha)"
    r"|(?:execute|executar|rode|run).{0,50}(?:sql|comando|shell|python)"
    r"|\b(?:drop\s+table|select\s+\*\s+from)\b"
    r"|(?:sou|i.am).{0,15}(?:administrador|admin).{0,60}(?:liber|acesso|pedido|bypass)",
    re.DOTALL,
)
_REFERENCE = re.compile(
    r"\b(?:esse|este|aquele|essa|esta|aquela|anterior|mesmo)\b"
    r"|^e\s+(?:em\s+\d{1,2}\s*x|(?:no|por)\s+pix|parcelad)",
)
_ACCESSORY = re.compile(r"\b(?:palhetas?|cabos?|pedaleiras?|cases?)\b")


def suspicious(text: str) -> bool:
    return bool(_INJECTION.search(normalized(text)))


def refers_to_product(text: str) -> bool:
    # Distinguir o verbo "está" do demonstrativo "esta" antes de remover acentos.
    # NFC também trata entradas com o acento em um caractere combinante separado.
    reference_text = re.sub(r"\bestá\b", " ", unicodedata.normalize("NFC", text).casefold())
    value = normalized(reference_text.strip())
    # Uma seleção explícita tem precedência; "esse pedido" não é um instrumento.
    if re.search(r"\b(?:produto|modelo|id)\s*[:#]?\s*\d+\b", value) or re.search(
        r"\b(?:esse|este|aquele|essa|esta|aquela)\s+"
        r"(?:pedido|politica|garantia|devolucao|frete|prazo|horario|endereco)\b",
        value,
    ):
        return False
    return bool(_REFERENCE.search(value))


def accessory_request(text: str) -> bool:
    return bool(_ACCESSORY.search(normalized(text)))


def redact(text: str) -> str:
    """Redução de PII/segredos óbvios, não um detector completo de dados pessoais."""
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email omitido]", text)
    text = re.sub(r"(?<!\w)\+?\(?\d(?:[\s()./-]*\d){9,18}(?!\w)", "[número omitido]", text)
    text = re.sub(
        r"(?i)\b(?:senha|password|token|api[_ -]?key|chave)\s*[:=]\s*\S+",
        "[credencial omitida]",
        text,
    )
    return re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[credencial omitida]", text)

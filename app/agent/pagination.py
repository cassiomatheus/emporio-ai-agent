"""Reconhece apenas pedidos inequívocos de continuação da última busca."""

import re
import unicodedata


def wants_next_page(message: str) -> bool:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFKD", message.casefold())
        if not unicodedata.combining(char)
    )
    normalized = re.sub(r"[.,!?;:]", " ", normalized)
    normalized = " ".join(normalized.split())
    return (
        re.fullmatch(
            r"(?:por favor )?(?:"
            r"(?:pode )?(?:continue|continuar|continua)(?: (?:a lista|a listagem|a busca))?"
            r"|(?:a )?proxima pagina"
            r"|(?:mostre|mostrar|ver|quero ver)(?: os)? (?:proximos|mais)(?: resultados)?"
            r"|mais resultados"
            r")(?: por favor)?",
            normalized,
        )
        is not None
    )

"""Ranking lexical em memória; pontuação não equivale a confiança factual."""

import math
import re
import unicodedata
from collections import Counter
from decimal import Decimal

from app.retrieval.models import (
    PolicyChunk,
    PolicyDocument,
    PolicyHit,
    PolicySearch,
    PolicySearchResult,
)

STOPWORDS = set(
    """
a o as os um uma uns umas de da do das dos e em no na nos nas ao aos com sem por
para que qual quais como quanto quantos quando onde se ou eu meu minha meus minhas
voce voces seu sua seus suas posso pode podem poderia quero queria saber tem ter
ha sao e ser estar esta estao isso esse essa esses essas este esta gostaria sobre
ate apos antes mesmo mesma fazer favor preciso caso loja cliente clientes produto
produtos instrumento instrumentos pedido pedidos forma formas
""".split()
)
# Flexões frequentes do português, sem resolver intenção nem gerar paráfrases.
PREFIXES = ("parcel", "devol", "receb", "troc", "garant", "reembols", "promoc", "minim", "pag")


def tokenize(text: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    result = set()
    for word in re.findall(r"\d+x|\d+(?:[.,]\d+)?|[a-z]+", folded):
        if word in STOPWORDS:
            continue
        if re.fullmatch(r"\d+(?:[.,]\d+)?", word):
            word = format(Decimal(word.replace(",", ".")).normalize(), "f")
        else:
            word = next((prefix for prefix in PREFIXES if word.startswith(prefix)), word)
            if word.endswith("s") and len(word) > 4:
                word = word[:-1]
        if len(word) >= 3 or word[:1].isdigit():
            result.add(word)
    return result


def _excerpt(chunk: PolicyChunk, query: set[str]) -> tuple[str, bool]:
    if chunk.table:
        candidates = chunk.text.splitlines()
    else:
        candidates = re.split(r"\n\n|(?=•)", chunk.text)
    candidates = [text.strip() for text in candidates if text.strip()]
    ranked = sorted(
        enumerate(candidates), key=lambda pair: (-len(tokenize(pair[1]) & query), pair[0])
    )
    selected = []
    length = 0
    for index, text in ranked:
        if selected and not tokenize(text) & query:
            continue
        if length + len(text) + bool(selected) <= 420:
            selected.append((index, text))
            length += len(text) + (len(selected) > 1)
        elif not selected:
            return text[:419].rsplit(" ", 1)[0] + "…", True
    selected.sort()
    return "\n".join(text for _, text in selected), len(selected) < len(candidates)


class LexicalRetriever:
    def __init__(self, document: PolicyDocument) -> None:
        self.document = document
        self._body = [tokenize(chunk.text) for chunk in document.chunks]
        self._titles = [
            tokenize(" ".join(chunk.metadata.section_path)) for chunk in document.chunks
        ]
        frequencies = Counter(
            token
            for body, title in zip(self._body, self._titles, strict=True)
            for token in body | title
        )
        count = len(document.chunks)
        self._idf = {
            term: math.log(1 + (count + 1) / (frequency + 1))
            for term, frequency in frequencies.items()
        }

    def search(self, request: PolicySearch) -> PolicySearchResult:
        query = tokenize(request.query)
        if not query:
            return PolicySearchResult(status="no_evidence", hits=())
        ranked = []
        for index, chunk in enumerate(self.document.chunks):
            body, title = self._body[index], self._titles[index]
            matched = query & (body | title)
            coverage = len(matched) / len(query)
            # Não preencher top_k com correspondências fracas ou pontuação zero.
            title_anchors = {term for term in query & title if not term[:1].isdigit()}
            if coverage < 0.6 and len(title_anchors) < 2:
                continue
            score = sum(self._idf[term] * (2 if term in title else 1) for term in matched)
            ranked.append((score, coverage, chunk))
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2].chunk_id))
        hits = []
        seen = set()
        for score, coverage, chunk in ranked:
            if chunk.metadata.section_id in seen:
                continue
            seen.add(chunk.metadata.section_id)
            excerpt, truncated = _excerpt(chunk, query)
            hits.append(
                PolicyHit(
                    chunk_id=chunk.chunk_id,
                    metadata=chunk.metadata,
                    excerpt=excerpt,
                    excerpt_truncated=truncated,
                    score=round(score, 6),
                    lexical_coverage=coverage,
                    match_grade="strong" if coverage >= 0.8 else "partial",
                )
            )
            if len(hits) == request.top_k:
                break
        return PolicySearchResult(status="matched" if hits else "no_evidence", hits=tuple(hits))

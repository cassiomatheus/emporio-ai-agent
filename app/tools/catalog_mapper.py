"""Traduz critérios semânticos em filtros, usando somente vocabulário do catálogo."""

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import ValidationError

from app.schemas.catalog_request import CatalogInterpretation, CatalogSearchRequest, ProductCriteria
from app.services.product_service import ProductService, normalize_text
from app.tools.schemas import SearchProductsInput

_KEYS = {
    "cor": "color",
    "cordas": "strings",
    "corda": "strings",
    "captacao": "electronics",
    "eletronica": "electronics",
    "tampo": "top",
    "braco": "neck",
    "corpo": "body",
    "teclas": "keys",
    "polifonia": "polyphony",
    "pecas": "pieces",
    "tipo": "type",
    "escala": "scale",
    "fundo_laterais": "back_sides",
}
_VALUES = {
    "color": (
        ("preto", "preta", "black"),
        ("branco", "branca", "white"),
        ("vermelho", "vermelha", "red"),
        ("azul", "blue"),
        ("amarelo", "amarela", "yellow"),
    ),
    "strings": (("aco", "steel"),),
    "electronics": (("sim", "yes", "true"), ("nao", "no", "false")),
}
_GENERIC = {"instrumento", "instrumentos", "qualquer", "todos"}
_CATEGORY_STOP = {"e", "de", "do", "da", "instrumento", "corda", "sintetico", "sintetica"}
_BUDGET = re.compile(
    r"\b(?P<label>ate|no maximo|maximo de|limite de|a partir de|minimo de)\s*"
    r"(?P<currency>r\$\s*)?(?P<amount>\d[\d.,]*)(?P<mil>\s*mil\b)?"
)
_NON_MONEY = re.compile(r"^(?:x\b|parcelas?\b|vezes\b|cordas?\b|dias?\b|anos?\b|cm\b|mm\b)")


class CatalogClarification(ValueError):
    def __init__(self, kind: Literal["category", "budget", "specs", "rephrase"]) -> None:
        super().__init__("catalog_request_requires_clarification")
        self.kind = kind


def _words(value: str) -> tuple[str, ...]:
    def singular(word: str) -> str:
        if word.endswith("oes"):
            return word[:-3] + "ao"
        return word[:-1] if len(word) > 3 and word.endswith("s") else word

    return tuple(singular(word) for word in re.findall(r"[a-z0-9]+", normalize_text(value)))


def _qualifier_words(value: str) -> tuple[str, ...]:
    return tuple(word[:-1] if word.endswith(("ico", "ica")) else word for word in _words(value))


def _contains(words: tuple[str, ...], fragment: tuple[str, ...]) -> bool:
    size = len(fragment)
    return bool(size and any(words[i : i + size] == fragment for i in range(len(words) - size + 1)))


def _observed_phrase(name: str, fragment: str) -> str | None:
    text = normalize_text(name)
    tokens = list(re.finditer(r"[a-z0-9]+", text))
    target = _words(fragment)
    for index in range(len(tokens) - len(target) + 1):
        window = tokens[index : index + len(target)]
        phrase = text[window[0].start() : window[-1].end()]
        if _words(phrase) == target:
            return phrase
    return None


def _budgets(message: str) -> dict[str, Decimal]:
    values = {"min_price": set(), "max_price": set()}
    text = normalize_text(message)
    for match in _BUDGET.finditer(text):
        if not match["currency"] and _NON_MONEY.match(text[match.end() :].lstrip()):
            continue
        number = match["amount"].rstrip(".,")
        if "," in number:
            number = number.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", number):
            number = number.replace(".", "")
        try:
            value = Decimal(number) * (1000 if match["mil"] else 1)
        except InvalidOperation as exc:
            raise CatalogClarification("budget") from exc
        key = "min_price" if match["label"] in {"a partir de", "minimo de"} else "max_price"
        values[key].add(value)
    if any(len(items) > 1 for items in values.values()):
        raise CatalogClarification("budget")
    return {key: next(iter(items)) for key, items in values.items() if items}


class CatalogQueryMapper:
    def __init__(self, products: ProductService) -> None:
        self.products = products

    def prepare(self, arguments: object, message: str) -> CatalogInterpretation:
        legacy = None
        try:
            if not isinstance(arguments, dict):
                raise CatalogClarification("rephrase")
            if {"product", "characteristics", "intent"} & arguments.keys():
                request = CatalogSearchRequest.model_validate(arguments)
            else:
                # Compatibilidade explícita com callers internos e roteiros anteriores.
                legacy = SearchProductsInput.model_validate(arguments)
                request = CatalogSearchRequest(
                    product=ProductCriteria(category=legacy.category, name=legacy.term),
                    characteristics=legacy.specs,
                    min_price=str(legacy.min_price) if legacy.min_price is not None else None,
                    max_price=str(legacy.max_price) if legacy.max_price is not None else None,
                    available_only=legacy.available_only,
                    status=legacy.status,
                    limit=legacy.limit,
                    offset=legacy.offset,
                )
        except ValidationError as exc:
            kind = (
                "budget"
                if any(
                    any("price" in str(part) for part in error["loc"])
                    or error["type"] == "value_error"
                    and not error["loc"]
                    for error in exc.errors(include_input=False, include_context=False)
                )
                else "rephrase"
            )
            raise CatalogClarification(kind) from exc

        facets = self.products.catalog_facets()
        categories = {facet.category_name for facet in facets}
        aliases: dict[tuple[str, ...], set[str]] = {}
        for category in categories:
            words = _words(category)
            for alias in [words, *((word,) for word in words if word not in _CATEGORY_STOP)]:
                aliases.setdefault(alias, set()).add(category)

        def resolve(value: str | None) -> str | None:
            if value is None or normalize_text(value) in _GENERIC:
                return None
            matches = aliases.get(_words(value), set())
            if len(matches) != 1:
                raise CatalogClarification("category")
            return next(iter(matches))

        mentioned = set()
        for alias, candidates in aliases.items():
            if len(candidates) == 1 and _contains(_words(message), alias):
                mentioned.update(candidates)
        inferred_characteristics = {}
        try:
            category = resolve(request.product.category)
        except CatalogClarification:
            if len(mentioned) == 1:
                category = next(iter(mentioned))
            else:
                value = request.product.category
                attributes = {
                    key
                    for facet in facets
                    for key, item in facet.specs.items()
                    if value is not None
                    and isinstance(item, str)
                    and normalize_text(item) == normalize_text(value)
                }
                if len(attributes) != 1 or not _contains(_words(message), _words(value or "")):
                    raise
                category = None
                inferred_characteristics[next(iter(attributes))] = value
        if legacy is not None and legacy.category_id is not None:
            by_id = {
                facet.category_name for facet in facets if facet.category_id == legacy.category_id
            }
            if len(by_id) != 1 or category is not None and category not in by_id:
                raise CatalogClarification("category")
            category = next(iter(by_id))
        if len(mentioned) == 1:
            observed = next(iter(mentioned))
            if category is not None and category != observed:
                raise CatalogClarification("category")
            category = observed

        changes = request.model_dump(mode="json")
        for key, value in _budgets(message).items():
            extracted = getattr(request, key)
            if extracted is not None and extracted != value:
                raise CatalogClarification("budget")
            changes[key] = str(value)
        try:
            request = CatalogSearchRequest.model_validate(changes)
        except ValidationError as exc:
            raise CatalogClarification("budget") from exc
        if request.available_only and request.status not in (None, "active"):
            raise CatalogClarification("specs")
        selected = [
            facet for facet in facets if category is None or facet.category_name == category
        ]
        observed_keys = {normalize_text(key): key for facet in selected for key in facet.specs}
        characteristics = {}
        attribute_terms = []
        for key, value in {**inferred_characteristics, **request.characteristics}.items():
            normalized = normalize_text(key)
            normalized = _KEYS.get(normalized, normalized)
            if normalized not in observed_keys:
                if normalized in {"type", "size", "tamanho", "subtype", "subtipo"} and isinstance(
                    value, str
                ):
                    if category is not None and _contains(
                        _qualifier_words(category), _qualifier_words(value)
                    ):
                        continue
                    phrases = [
                        phrase
                        for facet in selected
                        if (phrase := _observed_phrase(facet.name, value)) is not None
                    ]
                    if phrases:
                        attribute_terms.append(min(phrases, key=len))
                        continue
                raise CatalogClarification("specs")
            key = observed_keys[normalized]
            if key in characteristics and normalize_text(
                str(characteristics[key])
            ) != normalize_text(str(value)):
                raise CatalogClarification("specs")
            observed = [facet.specs[key] for facet in selected if key in facet.specs]
            for group in _VALUES.get(normalize_text(key), ()):
                if normalize_text(str(value)) in group:
                    match = next(
                        (item for item in observed if normalize_text(str(item)) in group), None
                    )
                    if match is not None:
                        value = normalize_text(match) if isinstance(match, str) else match
                    break
            if isinstance(value, str) and value.isdigit():
                if any(type(item) is int and item == int(value) for item in observed):
                    value = int(value)
            if (
                legacy is None
                and observed
                and not any(type(item) is type(value) for item in observed)
            ):
                raise CatalogClarification("specs")
            characteristics[key] = value

        # Restrições explícitas e reconhecíveis não podem sumir na extração.
        # Usa valores observados; não interpreta descrições arbitrárias de material.
        for field in ("color", "strings"):
            actual_key = observed_keys.get(field)
            if actual_key is None:
                continue
            observed = {
                normalize_text(str(facet.specs[actual_key]))
                for facet in selected
                if actual_key in facet.specs and isinstance(facet.specs[actual_key], str)
            }
            mentioned_values = set()
            for value in observed:
                aliases_for_value = {value}
                for group in _VALUES.get(field, ()):
                    if value in group:
                        aliases_for_value.update(group)
                if any(
                    len(alias) >= 3 and _contains(_words(message), _words(alias))
                    for alias in aliases_for_value
                ):
                    mentioned_values.add(value)
            provided = characteristics.get(actual_key)
            if mentioned_values:
                if provided is not None and normalize_text(str(provided)) not in mentioned_values:
                    raise CatalogClarification("specs")
                if provided is None:
                    if len(mentioned_values) != 1:
                        raise CatalogClarification("specs")
                    characteristics[actual_key] = next(iter(mentioned_values))

        terms = []
        if request.product.name:
            name = request.product.name
            # Remover só uma categoria redundante, nunca uma característica pedida.
            for alias, candidates in sorted(aliases.items(), key=lambda item: -len(item[0])):
                if candidates == {category} and _contains(_words(name), alias):
                    if not any(_contains(_words(facet.name), alias) for facet in selected):
                        pattern = (
                            r"\b" + r"\W+".join(re.escape(word) + r"s?" for word in alias) + r"\b"
                        )
                        name = re.sub(pattern, " ", normalize_text(name))
            name = " ".join(name.split())
            if name:
                terms.append(name)
        if request.product.subtype:
            subtype = request.product.subtype
            spec_matches = {
                key
                for facet in selected
                for key, value in facet.specs.items()
                if isinstance(value, str) and normalize_text(value) == normalize_text(subtype)
            }
            if len(spec_matches) == 1:
                key = next(iter(spec_matches))
                if key in characteristics and normalize_text(
                    str(characteristics[key])
                ) != normalize_text(subtype):
                    raise CatalogClarification("specs")
                characteristics[key] = subtype
            else:
                matches = {
                    facet.category_name
                    for facet in facets
                    if _contains(_words(facet.name), _words(subtype))
                }
                if category is not None and matches and category not in matches:
                    raise CatalogClarification("category")
                if category is None and len(matches) == 1:
                    category = next(iter(matches))
                phrases = [
                    phrase
                    for facet in selected
                    if (phrase := _observed_phrase(facet.name, subtype)) is not None
                ]
                terms.append(min(phrases, key=len) if phrases else subtype)
        if legacy is not None:
            terms.extend(legacy.name_terms)
        terms.extend(attribute_terms)
        terms = list({normalize_text(term): term for term in terms}.values())
        if legacy is None:
            characteristics = {
                key: normalize_text(value) if isinstance(value, str) else value
                for key, value in characteristics.items()
            }
        category_ids = {facet.category_id for facet in facets if facet.category_name == category}
        derived_id = next(iter(category_ids)) if len(category_ids) == 1 else None
        query = SearchProductsInput(
            category=category
            if legacy is None or legacy.category_id is None or legacy.category is not None
            else None,
            category_id=legacy.category_id if legacy else derived_id,
            term=terms[0] if terms else None,
            name_terms=terms[1:],
            specs=characteristics,
            min_price=str(request.min_price) if request.min_price is not None else None,
            max_price=str(request.max_price) if request.max_price is not None else None,
            available_only=request.available_only,
            status=request.status,
            limit=request.limit,
            offset=request.offset,
        )
        return CatalogInterpretation(
            request=request, query=query, source="legacy" if legacy else "semantic"
        )

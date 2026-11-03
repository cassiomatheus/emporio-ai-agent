"""Intenção e consulta são contratos diferentes; vocabulário vem de fonte sintética."""

import json
from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.agent.catalog_contracts import agent_tool_contracts
from app.database.repository import ProductRepository
from app.services.models import ProductSearch
from app.services.product_service import ProductService
from app.tools.catalog_mapper import CatalogClarification, CatalogQueryMapper
from app.tools.registry import tool_contracts


@pytest.fixture
def mapper(product):
    repository = Mock(spec=ProductRepository)
    base = replace(
        product,
        category_id=9,
        category_name="Ukuleles",
        specs={"color": "Natural", "strings": "nylon"},
    )
    repository.list_products.return_value = (
        replace(base, product_id=501, name="Kalani exemplo Soprano Mogno", price_cents=19990),
        replace(base, product_id=502, name="Outro exemplo Soprano Natural", price_cents=17990),
        replace(base, product_id=503, name="Kalani exemplo Concert Natural", price_cents=22990),
        replace(
            base,
            product_id=504,
            name="Outro Soprano Sunburst",
            price_cents=15990,
            specs={"color": "Sunburst", "strings": "nylon"},
        ),
        replace(base, product_id=505, name="Caro Soprano Natural", price_cents=25001),
        replace(base, product_id=506, name="Sem estoque Soprano Natural", stock_quantity=0),
        replace(base, product_id=507, name="Descontinuado Soprano Natural", status="discontinued"),
        replace(
            product,
            category_id=1,
            category_name="Guitarras",
            name="Guitarra de teste",
            specs={"color": "Preto", "strings": 6},
        ),
        replace(
            product,
            category_id=5,
            category_name="Violões",
            name="Modelo clássico",
            specs={"color": "Natural", "strings": "nylon"},
        ),
        replace(
            product,
            category_id=4,
            category_name="Teclados e Pianos",
            name="Teclado exemplo",
            specs={"color": "Preto", "type": "arranjador"},
        ),
    )
    return CatalogQueryMapper(ProductService(repository))


def request(**changes):
    return {
        "intent": "search_products",
        "product": {"category": "ukulele", "subtype": "soprano"},
        "characteristics": {"cor": "natural"},
        "max_price": "250.00",
        **changes,
    }


def test_normalization_uses_observed_category_and_spec_keys(mapper):
    result = mapper.prepare(request(), "Ukulele soprano, cor natural, até R$ 250")
    assert result.request.product.category == "ukulele"
    assert result.query.category == "Ukuleles" and result.query.term == "soprano"
    assert result.query.specs == {"color": "natural"} and result.query.max_price == Decimal("250")
    page = mapper.products.search(ProductSearch(**result.query.model_dump()))
    assert [item.product_id for item in page.items] == [502, 501]


def test_brand_and_subtype_are_intersected_without_requiring_adjacent_words(mapper):
    result = mapper.prepare(
        request(product={"category": "ukulele", "subtype": "soprano", "name": "Kalani"}),
        "Quero Kalani soprano natural até 250",
    )
    assert result.query.term == "Kalani" and result.query.name_terms == ["soprano"]
    assert [
        item.product_id
        for item in mapper.products.search(ProductSearch(**result.query.model_dump())).items
    ] == [501]


@pytest.mark.parametrize(
    "arguments,message,kind",
    [
        (
            request(product={"category": "violão", "subtype": "soprano"}),
            "Quero ukulele soprano até 250",
            "category",
        ),
        (request(max_price="300"), "Ukulele até R$ 250", "budget"),
        (request(min_price="300"), "Ukulele", "budget"),
        (request(max_price=250.0), "Ukulele", "budget"),
        (request(characteristics={"atributo_inexistente": "soprano"}), "Ukulele", "specs"),
        (request(characteristics={"cor": "azul"}), "Ukulele de cor natural", "specs"),
        (request(product={"category": "categoria desconhecida"}), "Quero algo", "category"),
        (
            request(product={"category": "guitarra", "subtype": "soprano"}),
            "Procuro soprano",
            "category",
        ),
        (request(characteristics={"cor": "natural", "color": "azul"}), "Ukulele", "specs"),
        (request(sql="SELECT * FROM customers"), "Ukulele", "rephrase"),
        (request(customer_id=1), "Ukulele", "rephrase"),
        (
            request(product={"category": "ukulele", "subtype": "soprano", "customer_id": 1}),
            "Ukulele",
            "rephrase",
        ),
    ],
)
def test_ambiguous_or_contradictory_requests_do_not_become_broad_queries(
    mapper, arguments, message, kind
):
    with pytest.raises(CatalogClarification) as error:
        mapper.prepare(arguments, message)
    assert error.value.kind == kind


@pytest.mark.parametrize(
    "amount,expected", [("250", "250"), ("1.000,00", "1000"), ("1.000", "1000"), ("2 mil", "2000")]
)
def test_omitted_budget_and_color_are_preserved_from_explicit_message(mapper, amount, expected):
    result = mapper.prepare(
        request(max_price=None, characteristics={}), f"Ukulele soprano cor natural até R$ {amount}"
    )
    assert result.query.max_price == Decimal(expected) and result.query.specs == {
        "color": "natural"
    }


def test_installment_count_is_not_a_price_limit(mapper):
    result = mapper.prepare(request(max_price=None), "Ukulele natural em até 12 parcelas")
    assert result.query.max_price is None


def test_source_type_and_observed_numeric_characteristic_are_preserved(mapper):
    result = mapper.prepare(
        request(product={"category": "guitarra"}, characteristics={"cor": "preta", "cordas": "6"}),
        "Guitarra preta de 6 cordas",
    )
    assert result.query.category == "Guitarras" and result.query.specs == {
        "color": "preto",
        "strings": 6,
    }
    result = mapper.prepare(
        request(product={"category": "piano", "subtype": "arranjador"}, characteristics={}),
        "Piano arranjador",
    )
    assert result.query.category == "Teclados e Pianos" and result.query.specs == {
        "type": "arranjador"
    }


def test_legacy_input_is_explicitly_adapted_and_keeps_all_constraints(mapper):
    result = mapper.prepare(
        {
            "category_id": 9,
            "term": "soprano",
            "specs": {"color": "natural"},
            "max_price": "250",
            "limit": 2,
        },
        "Busca filtrada",
    )
    assert result.source == "legacy" and result.query.category_id == 9
    assert result.query.category is None and result.query.limit == 2
    assert result.query.specs == {"color": "natural"} and result.query.max_price == Decimal("250")


def test_agent_search_contract_is_semantic_and_other_five_tools_are_unchanged():
    backend, agent = tool_contracts(), agent_tool_contracts()
    assert len(agent) == 6 and agent[1:] == backend[1:]
    properties = agent[0]["input_schema"]["properties"]
    assert {"product", "characteristics", "min_price", "max_price"} <= properties.keys()
    assert not {"sql", "customer_id", "term", "specs", "category_id"} & properties.keys()
    assert "product" in agent[0]["input_schema"]["required"]


def test_nested_json_transport_preserves_strict_object_validation(mapper):
    result = mapper.prepare(
        request(
            product=json.dumps({"category": "ukulele", "subtype": "sopranos"}),
            characteristics=json.dumps({"cor": "natural"}),
        ),
        "Procuro ukuleles sopranos naturais até 250",
    )
    assert result.request.product.subtype == "sopranos" and result.query.term == "soprano"


@pytest.mark.parametrize(
    "value",
    [
        '{"category":"ukulele","category":"violão"}',
        '{"category":NaN}',
        "[]",
        "{'category':'ukulele'}",
        '"ukulele"',
        "x" * 4097,
    ],
)
def test_nested_transport_cannot_hide_duplicates_constants_lists_or_code(mapper, value):
    with pytest.raises(CatalogClarification):
        mapper.prepare(request(product=value), "Ukulele")


def test_incompatible_characteristic_type_requires_clarification(mapper):
    with pytest.raises(CatalogClarification) as error:
        mapper.prepare(request(characteristics={"cor": True}), "Ukulele")
    assert error.value.kind == "specs"


def test_misplaced_entity_is_recovered_only_from_unique_source_evidence(mapper):
    result = mapper.prepare({"product": {"category": "nylon"}}, "Busque instrumentos de nylon")
    assert result.query.category is None and result.query.specs == {"strings": "nylon"}
    result = mapper.prepare(
        request(
            product={"category": "ukulele"}, characteristics={"size": "soprano", "cor": "natural"}
        ),
        "Ukulele soprano natural",
    )
    assert result.query.term == "soprano" and result.query.specs == {"color": "natural"}
    assert "size" not in result.query.specs


def test_category_qualifier_is_kept_by_category_filter_without_inventing_spec(product):
    repository = Mock(spec=ProductRepository)
    repository.list_products.return_value = (
        replace(
            product,
            category_id=7,
            category_name="Teclas sintéticas",
            name="Exemplo",
            specs={"color": "Preto", "keys": 61},
            status="coming_soon",
        ),
    )
    mapper = CatalogQueryMapper(ProductService(repository))
    result = mapper.prepare(
        {"product": {"category": "teclado"}, "characteristics": {"tipo": "sintético"}},
        "Busque teclas sintéticas disponíveis",
    )
    assert result.query.category == "Teclas sintéticas" and result.query.category_id == 7
    assert result.query.specs == {}
    assert not mapper.products.search(ProductSearch(**result.query.model_dump())).items


def test_unknown_descriptive_qualifier_is_not_dropped(mapper):
    with pytest.raises(CatalogClarification):
        mapper.prepare(request(characteristics={"size": "não observado"}), "Ukulele")


def test_unknown_extracted_category_can_only_recover_from_explicit_customer_category(mapper):
    result = mapper.prepare(
        request(product={"category": "ukelele", "subtype": "soprano"}),
        "Quero ukulele soprano natural até 250",
    )
    assert result.query.category == "Ukuleles" and result.query.category_id == 9

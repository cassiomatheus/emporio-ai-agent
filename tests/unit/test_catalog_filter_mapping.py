"""Contrato de busca com nomes e specs distintos; repositório simulado, sem LLM."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from app.database.repository import ProductRepository
from app.services.product_service import ProductService
from app.tools.product_tools import ProductTools


@pytest.fixture
def catalog(product):
    base = replace(
        product,
        category_id=9,
        category_name="Ukuleles",
        specs={"color": "Natural", "strings": "nylon", "scale": "346mm"},
    )
    records = [
        replace(base, product_id=4001, name="Modelo A Soprano Mogno", price_cents=19990),
        replace(base, product_id=4002, name="Modelo B Soprano Natural", price_cents=17990),
        replace(base, product_id=4003, name="Modelo C Soprano Natural", price_cents=24990),
        replace(
            base,
            product_id=4004,
            name="Modelo D Soprano Sunburst",
            price_cents=15990,
            specs={"color": "Sunburst", "strings": "nylon"},
        ),
        replace(base, product_id=4005, name="Modelo E Concert Natural", price_cents=22990),
        replace(base, product_id=4006, name="Modelo F Soprano Natural", price_cents=25001),
        replace(
            base,
            product_id=4007,
            name="Modelo G Soprano Natural",
            price_cents=10000,
            status="discontinued",
            stock_quantity=10,
        ),
        replace(
            base,
            product_id=4008,
            name="Modelo H Soprano Natural",
            price_cents=10000,
            stock_quantity=0,
        ),
        replace(
            base,
            product_id=4009,
            name="Modelo I Soprano Natural",
            price_cents=10000,
            status="coming_soon",
            stock_quantity=2,
        ),
        replace(
            base,
            product_id=4010,
            name="Modelo J Soprano Natural",
            price_cents=19990,
            category_id=5,
            category_name="Violões",
        ),
    ]
    repository = Mock(spec=ProductRepository)
    repository.list_products.return_value = records
    return ProductTools(ProductService(repository))


def query(**changes):
    return {
        "category": "Ukuleles",
        "term": "soprano",
        "max_price": "250",
        "specs": {"color": "natural"},
        "available_only": True,
        **changes,
    }


@pytest.mark.parametrize("ceiling", [250, "250"])
def test_subtype_in_name_and_color_in_specs_preserve_every_requested_filter(catalog, ceiling):
    response = catalog.search_products(query(max_price=ceiling))
    assert response.status == "ok" and response.data.total == 3
    assert [item.product_id for item in response.data.items] == [4002, 4001, 4003]
    # Mogno no nome não impede color=Natural observado em specs.
    assert response.data.items[1].name.endswith("Mogno")
    assert all(item.specs["color"] == "Natural" and item.available for item in response.data.items)


@pytest.mark.parametrize("invented_key", ["size", "type"])
def test_nonexistent_specs_are_not_silently_dropped_or_inferred(catalog, invented_key):
    response = catalog.search_products(query(specs={"color": "natural", invented_key: "soprano"}))
    assert response.status == "ok" and response.data.total == 0


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"term": "concert"}, [4005]),
        ({"specs": {"color": "azul"}}, []),
        ({"max_price": "179.89"}, []),
        ({"category": "Violões", "term": "ukulele soprano"}, []),
    ],
)
def test_constraints_are_literal_without_relaxing_category_color_subtype_or_price(
    catalog,
    changes,
    expected,
):
    response = catalog.search_products(query(**changes))
    assert response.status == "ok"
    assert [item.product_id for item in response.data.items] == expected

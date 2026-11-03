"""Filtros, paginação, disponibilidade e falhas do catálogo, sem banco."""

from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.database.repository import ProductRecord, ProductRepository, RepositoryError
from app.services.errors import ProductNotFound, ServiceUnavailable
from app.services.models import ProductSearch
from app.services.product_service import ProductService


def test_combined_filters_and_availability(product: ProductRecord) -> None:
    repository = Mock(spec=ProductRepository)
    repository.list_products.return_value = (
        product,
        replace(product, product_id=82, category_id=1, category_name="Guitarras"),
        replace(product, product_id=83, price_cents=90000),
        replace(product, product_id=84, specs={"strings": "steel"}),
        replace(product, product_id=85, status="discontinued", stock_quantity=13),
        replace(product, product_id=86, status="coming_soon", stock_quantity=2),
        replace(product, product_id=87, stock_quantity=0),
    )
    result = ProductService(repository).search(
        ProductSearch(
            term="VIOLAO",
            category="Violoes",
            category_id=5,
            min_price="400.00",
            max_price=Decimal("800"),
            specs={"STRINGS": "NYLON"},
        )
    )
    assert [item.product_id for item in result.items] == [81]
    assert result.items[0].price_brl == Decimal("599.90")
    assert result.items[0].available
    assert result.total == 1


@pytest.mark.parametrize(
    "status,stock,reason",
    [
        ("active", 0, "out_of_stock"),
        ("discontinued", 13, "discontinued"),
        ("coming_soon", 2, "coming_soon"),
    ],
)
def test_positive_stock_does_not_override_status(
    product: ProductRecord, status: str, stock: int, reason: str
) -> None:
    record = replace(product, status=status, stock_quantity=stock)
    repository = Mock(spec=ProductRepository)
    repository.get_product.return_value = record
    repository.list_products.return_value = (record,)
    service = ProductService(repository)
    result = service.get_product(81)
    assert not result.available
    assert result.availability_reason == reason
    assert not service.search(ProductSearch()).items
    assert service.search(ProductSearch(available_only=False, status=status)).items


def test_inclusive_boundaries_and_stable_pagination(product: ProductRecord) -> None:
    repository = Mock(spec=ProductRepository)
    repository.list_products.return_value = (
        replace(product, product_id=82),
        product,
        replace(product, product_id=80, price_cents=59990),
    )
    result = ProductService(repository).search(
        ProductSearch(
            min_price="599.90",
            max_price="599.90",
            offset=1,
            limit=1,
        )
    )
    assert result.total == 3
    assert [item.product_id for item in result.items] == [81]


def test_literal_search_and_unknown_spec_do_not_invent_results(product: ProductRecord) -> None:
    repository = Mock(spec=ProductRepository)
    repository.list_products.return_value = (product,)
    service = ProductService(repository)
    assert service.search(ProductSearch(term="' OR 1=1 --")).items == ()
    assert service.search(ProductSearch(specs={"unknown": "value"})).items == ()
    assert service.search(ProductSearch(category="Guitarras")).items == ()
    assert service.search(ProductSearch(category_id=1)).items == ()
    assert service.search(ProductSearch(offset=100)).total == 1
    assert service.search(ProductSearch(offset=100)).items == ()


@pytest.mark.parametrize(
    "filters",
    [
        {"min_price": "800", "max_price": "400"},
        {"max_price": -1},
        {"max_price": 800.0},
        {"max_price": "NaN"},
        {"min_price": "0.001"},
        {"term": " "},
        {"limit": 101},
        {"offset": -1},
        {"specs": {" ": "x"}},
    ],
)
def test_invalid_search_filters(filters: dict) -> None:
    with pytest.raises(ValidationError):
        ProductSearch(**filters)


def test_catalog_not_found_and_failure_are_explicit() -> None:
    repository = Mock(spec=ProductRepository)
    repository.get_product.return_value = None
    service = ProductService(repository)
    with pytest.raises(ProductNotFound, match="^not_found$"):
        service.get_product(999)
    repository.list_products.side_effect = RepositoryError("private technical details")
    with pytest.raises(ServiceUnavailable, match="^service_unavailable$"):
        service.search(ProductSearch())
    repository.get_product.side_effect = RepositoryError("private technical details")
    with pytest.raises(ServiceUnavailable):
        service.get_product(81)

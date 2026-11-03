"""Serviços com repositórios SQLite reais, mantendo dados privados fora dos testes públicos."""

import hashlib
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from app.database.connection import connect_database
from app.database.ingestion import ingest_dataset
from app.database.repository import (
    RepositoryError,
    SQLiteOrderRepository,
    SQLitePricingRepository,
    SQLiteProductRepository,
)
from app.services.errors import OrderAccessDenied, ProductUnavailable, ServiceUnavailable
from app.services.models import OrderAccessContext, ProductSearch, QuoteRequest
from app.services.order_service import OrderService
from app.services.pricing_service import PricingService
from app.services.product_service import ProductService

PROJECT = Path(__file__).resolve().parents[2]


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "services.sqlite3"
    ingest_dataset(PROJECT / "data" / "samples", path)
    return path


def test_repositories_and_services_on_synthetic_snapshot(database: Path) -> None:
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    products = ProductService(SQLiteProductRepository(database))
    pricing = PricingService(SQLitePricingRepository(database))
    orders = OrderService(SQLiteOrderRepository(database))
    result = products.search(
        ProductSearch(
            category="Cordas sintéticas",
            max_price="300.00",
            specs={"strings": "nylon"},
        )
    )
    assert [item.product_id for item in result.items] == [102]
    assert not products.get_product(136).available
    quote = pricing.quote(QuoteRequest(product_id=127, payment_method="pix"))
    assert (quote.original_price, quote.final_price) == (Decimal("359.00"), Decimal("323.10"))
    order = orders.get_status(1, access=OrderAccessContext(authorized_customer_id=1))
    assert order.total_brl == Decimal("999.90")
    assert order.tracking_code is None
    assert order.tracking_status == "not_provided"
    assert order.estimated_delivery is None
    output = order.model_dump_json()
    assert "Cliente Sintético" not in output
    assert "example.invalid" not in output
    assert '"notes"' not in output
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_order_scope_is_enforced_in_sql_and_service(database: Path) -> None:
    repository = SQLiteOrderRepository(database)
    service = OrderService(repository)
    assert repository.get_authorized_order(1, 2) is None
    assert repository.get_authorized_order(999, 2) is None
    context = OrderAccessContext(authorized_customer_id=2)
    failures = []
    for order_id in (1, 999):
        with pytest.raises(OrderAccessDenied) as exc:
            service.get_status(order_id, access=context)
        failures.append(str(exc.value))
    assert failures == ["forbidden", "forbidden"]
    own_order = service.get_status(2, access=context)
    assert own_order.tracking_code == "DEMO-TRACK-2"


def test_repository_queries_are_parameterized(database: Path) -> None:
    repository = SQLiteProductRepository(database)
    assert repository.get_product("127 OR 1=1") is None
    assert SQLitePricingRepository(database).get_pricing_data("127 OR 1=1") is None
    assert SQLiteOrderRepository(database).get_authorized_order("1 OR 1=1", 1) is None
    assert len(repository.list_products()) == 5


def test_missing_database_fails_without_creating_a_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(RepositoryError, match="^repository_unavailable$"):
        SQLiteProductRepository(path).list_products()
    with pytest.raises(ServiceUnavailable):
        ProductService(SQLiteProductRepository(path)).search(ProductSearch())
    assert not path.exists()


def test_read_connection_cannot_change_snapshot(database: Path) -> None:
    with connect_database(database, read_only=True) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM products")


@pytest.mark.local_data
def test_original_business_acceptance(tmp_path: Path) -> None:
    raw = PROJECT / "data" / "raw"
    if not any(raw.glob("*.csv")):
        pytest.skip("Anexos privados ausentes; serviços continuam testáveis com fontes sintéticas.")
    path = tmp_path / "original-services.sqlite3"
    ingest_dataset(raw, path)
    products = ProductService(SQLiteProductRepository(path))
    result = products.search(
        ProductSearch(category="Violões", max_price="800", specs={"strings": "nylon"})
    )
    assert [item.product_id for item in result.items] == [83, 85, 81, 84]
    assert all(item.available and item.price_brl <= Decimal("800") for item in result.items)
    pricing = PricingService(SQLitePricingRepository(path))
    quote = pricing.quote(QuoteRequest(product_id=127, payment_method="pix"))
    assert quote.original_price == Decimal("359.00")
    assert quote.final_price == Decimal("323.10")
    assert quote.discount_percent == 10
    for product_id, stock in ((130, 2), (136, 13), (96, 0)):
        product = products.get_product(product_id)
        assert not product.available
        assert product.stock_quantity == stock
        with pytest.raises(ProductUnavailable):
            pricing.get_offers(product_id)
    with connect_database(path) as connection:
        missing_tracking = connection.execute(
            "SELECT order_id, customer_id, total_cents FROM orders "
            "WHERE tracking_code IS NULL ORDER BY order_id LIMIT 1"
        ).fetchone()
        historical = connection.execute(
            "SELECT order_id, customer_id, total_cents FROM orders WHERE order_id IN (3,20)"
        ).fetchall()
    orders = OrderService(SQLiteOrderRepository(path))
    for row in [missing_tracking, *historical]:
        result = orders.get_status(
            row["order_id"], access=OrderAccessContext(authorized_customer_id=row["customer_id"])
        )
        assert result.total_brl == Decimal(row["total_cents"]) / 100
    assert (
        orders.get_status(
            missing_tracking["order_id"],
            access=OrderAccessContext(authorized_customer_id=missing_tracking["customer_id"]),
        ).tracking_status
        == "not_provided"
    )
    with pytest.raises(OrderAccessDenied):
        orders.get_status(
            missing_tracking["order_id"],
            access=OrderAccessContext(authorized_customer_id=999999),
        )

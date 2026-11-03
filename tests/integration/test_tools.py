"""Ferramentas com SQLite e PDF reais; nenhuma integração com provedor LLM."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.database.connection import connect_database
from app.database.ingestion import ingest_dataset
from app.database.repository import (
    SQLiteOrderRepository,
    SQLitePricingRepository,
    SQLiteProductRepository,
)
from app.services.models import OrderAccessContext
from app.services.order_service import OrderService
from app.services.policy_service import PolicyService
from app.services.pricing_service import PricingService
from app.services.product_service import ProductService
from app.tools.registry import ToolRegistry, tool_contracts

PROJECT = Path(__file__).resolve().parents[2]


def build_registry(database: Path, policies: PolicyService | None = None) -> ToolRegistry:
    return ToolRegistry(
        products=ProductService(SQLiteProductRepository(database)),
        pricing=PricingService(SQLitePricingRepository(database)),
        orders=OrderService(SQLiteOrderRepository(database)),
        policies=policies,
    )


def test_synthetic_database_tools_preserve_snapshot_and_authorization(tmp_path: Path) -> None:
    database = tmp_path / "tools.sqlite3"
    ingest_dataset(PROJECT / "data" / "samples", database)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    tools = build_registry(database)
    page = tools.call("search_products", {"category": "Cordas sintéticas", "max_price": 300})
    assert [item.product_id for item in page.data.items] == [102]
    product = tools.call("get_product_details", {"name": "Instrumento sintético descontinuado"})
    assert product.data.product_id == 136
    assert not product.data.available and product.data.stock_quantity == 13
    assert tools.call("get_product_offers", {"product_id": 136}).error.code == "unavailable"
    offer = tools.call("get_product_offers", {"product_id": 127, "payment_method": "pix"})
    assert offer.data.original_price == Decimal("359.00")
    assert offer.data.options[0].final_price == Decimal("323.10")
    assert tools.call("get_order_status", {"order_id": 1}).error.code == "forbidden"
    own = tools.call(
        "get_order_status",
        {"order_id": 1},
        order_access=OrderAccessContext(authorized_customer_id=1),
    )
    assert own.data.tracking_code is None
    assert own.data.total_brl == Decimal("999.90")
    denied = tools.call(
        "get_order_status",
        {"order_id": 1},
        order_access=OrderAccessContext(authorized_customer_id=2),
    )
    assert denied.error.code == "forbidden"
    assert tools.call("execute_sql", {"sql": "DELETE FROM products"}).error.code == "unknown_tool"
    assert (
        tools.call("get_product_details", {"product_id": 101, "sql": "x"}).error.code
        == "invalid_arguments"
    )
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_documented_contracts_match_generated_schemas() -> None:
    assert (
        json.loads((PROJECT / "docs" / "tool_contracts.json").read_text(encoding="utf-8"))
        == tool_contracts()
    )


@pytest.mark.local_data
def test_original_pdf_public_info_and_policy_sources(tmp_path: Path) -> None:
    pdf = PROJECT / "data" / "raw" / "políticas_da_loja.pdf"
    if not pdf.is_file():
        pytest.skip("PDF privado ausente; contratos continuam testados com fontes sintéticas.")
    before = hashlib.sha256(pdf.read_bytes()).hexdigest()
    policies = PolicyService.from_pdf(pdf)
    tools = build_registry(tmp_path / "unused.sqlite3", policies)
    query = tools.call(
        "search_store_policies",
        {"query": "Troca por defeito em 30 dias é a mesma coisa que garantia legal de 90 dias?"},
    )
    assert {"4.2", "8.1"} <= {hit.metadata.section_id for hit in query.data.hits}
    assert all(hit.metadata.version == "2.1" and len(hit.excerpt) <= 420 for hit in query.data.hits)
    for subject in ("address", "hours", "contacts"):
        result = tools.call("get_store_info", {"subject": subject})
        assert result.status == "ok"
        assert result.data.entries
        assert all(
            entry.source.pages and entry.source.version == "2.1" for entry in result.data.entries
        )
        if subject == "contacts":
            assert {"conflicting_phone_numbers", "conflicting_emails"} <= set(result.data.cautions)
        if subject == "hours":
            assert "not_an_open_now_check" in result.data.cautions
    assert (
        tools.call("search_store_policies", {"query": "senha do wifi"}).error.code == "no_evidence"
    )
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == before
    assert not (tmp_path / "unused.sqlite3").exists()


@pytest.mark.local_data
def test_original_catalog_and_protected_order_tools(tmp_path: Path) -> None:
    raw = PROJECT / "data" / "raw"
    if not any(raw.glob("*.csv")):
        pytest.skip("CSVs privados ausentes; contratos usam fixtures sintéticas na suíte pública.")
    database = tmp_path / "original-tools.sqlite3"
    ingest_dataset(raw, database)
    tools = build_registry(database)
    page = tools.call(
        "search_products",
        {"category": "Violões", "max_price": "800", "specs": {"strings": "nylon"}},
    )
    assert [item.product_id for item in page.data.items] == [83, 85, 81, 84]
    quote = tools.call("get_product_offers", {"product_id": 127, "payment_method": "pix"})
    assert quote.data.options[0].final_price == Decimal("323.10")
    with connect_database(database, read_only=True) as connection:
        order = connection.execute(
            "SELECT order_id,customer_id,total_cents FROM orders "
            "WHERE tracking_code IS NULL LIMIT 1"
        ).fetchone()
    result = tools.call(
        "get_order_status",
        {"order_id": order["order_id"]},
        order_access=OrderAccessContext(authorized_customer_id=order["customer_id"]),
    )
    assert result.data.tracking_status == "not_provided"
    assert result.data.total_brl == Decimal(order["total_cents"]) / 100

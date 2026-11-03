"""Aceite do snapshot local, sem imprimir linhas ou contatos de clientes."""

import hashlib
import json
from pathlib import Path

import pytest

from app.database.connection import connect_database
from app.database.dataset import load_dataset
from app.database.ingestion import ingest_dataset
from app.database.models import ROW_MODELS, to_cents

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"


@pytest.mark.local_data
def test_original_snapshot_acceptance(tmp_path: Path) -> None:
    if not any(RAW.glob("*.csv")):
        pytest.skip(
            "Anexos privados ausentes; testes com fixtures sintéticas continuam disponíveis."
        )
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in RAW.glob("*.csv")}
    dataset = load_dataset(RAW)
    assert dataset.report.valid
    expected = {
        "categories": 9,
        "products": 65,
        "customers": 50,
        "orders": 20,
        "order_items": 22,
        "promotions": 25,
    }
    assert {key: item.rows for key, item in dataset.report.tables.items()} == expected
    assert all(value == 0 for value in dataset.report.foreign_key_violations.values())
    assert all(item.duplicate_keys == 0 for item in dataset.report.tables.values())
    observations = dataset.report.observations
    assert observations["product_status_counts"] == {
        "active": 62,
        "discontinued": 2,
        "coming_soon": 1,
    }
    assert observations["promotion_active_counts"] == {"0": 21, "1": 4}
    assert observations["zero_stock_products"] == 2
    assert observations["historical_total_differences"] == [
        {"order_id": 3, "difference_cents": 4800},
        {"order_id": 20, "difference_cents": 8800},
    ]
    assert dataset.report.tables["orders"].null_counts["tracking_code"] == 12
    assert dataset.report.tables["orders"].null_counts["estimated_delivery"] == 12
    assert dataset.report.tables["orders"].null_counts["notes"] == 16
    database = tmp_path / "original.sqlite3"
    assert ingest_dataset(RAW, database).counts == expected
    with connect_database(database) as connection:
        digest = hashlib.sha256("\n".join(connection.iterdump()).encode()).hexdigest()
    assert ingest_dataset(RAW, database).counts == expected
    with connect_database(database) as connection:
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert hashlib.sha256("\n".join(connection.iterdump()).encode()).hexdigest() == digest
        for product_id, status, stock in [(130, "coming_soon", 2), (136, "discontinued", 13)]:
            row = connection.execute(
                "SELECT status, stock_quantity FROM products WHERE product_id=?", (product_id,)
            ).fetchone()
            assert tuple(row) == (status, stock)
        row = connection.execute(
            "SELECT price_cents, discount_percent, is_active FROM products "
            "JOIN promotions USING(product_id) WHERE product_id=127 AND is_active=1"
        ).fetchone()
        assert tuple(row) == (35900, 10, 1)
        historical = {
            row["order_id"]: row["total_cents"]
            for row in connection.execute("SELECT order_id, total_cents FROM orders")
        }
        assert all(
            historical[row.order_id] == to_cents(row.total_brl) for row in dataset.tables["orders"]
        )
        products = {
            row["product_id"]: row
            for row in connection.execute("SELECT product_id, price_cents, specs FROM products")
        }
        assert all(
            products[row.product_id]["price_cents"] == to_cents(row.price_brl)
            and json.loads(products[row.product_id]["specs"]) == row.specs
            for row in dataset.tables["products"]
        )
        for field, expected_nulls in [
            ("tracking_code", 12),
            ("estimated_delivery", 12),
            ("notes", 16),
        ]:
            count = connection.execute(
                f"SELECT count(*) FROM orders WHERE {field} IS NULL"
            ).fetchone()[0]
            assert count == expected_nulls
        for table in ROW_MODELS:
            columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert not columns.intersection(
                {"delivered_at", "unit_price_at_purchase", "promotion_start_date"}
            )
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in RAW.glob("*.csv")} == before

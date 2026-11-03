"""Testes offline com fontes sintéticas; nenhum dado privado é necessário."""

import csv
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.database.connection import connect_database
from app.database.dataset import DataQualityError, load_dataset
from app.database.ingestion import IngestionError, ingest_dataset

PROJECT = Path(__file__).resolve().parents[2]
SAMPLES = PROJECT / "data" / "samples"
COUNTS = {
    "categories": 2,
    "products": 5,
    "customers": 2,
    "orders": 2,
    "order_items": 3,
    "promotions": 2,
}


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    target = tmp_path / "raw"
    shutil.copytree(SAMPLES, target)
    return target


def change_cell(raw_dir: Path, table: str, field: str, value: str) -> None:
    path = raw_dir / f"{table}.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        rows = list(reader)
    rows[0][field] = value
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def file_hashes(raw_dir: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in raw_dir.iterdir()}


def database_digest(database: Path) -> str:
    with connect_database(database) as connection:
        return hashlib.sha256("\n".join(connection.iterdump()).encode()).hexdigest()


def test_round_trip_and_second_ingestion(raw_dir: Path, tmp_path: Path) -> None:
    before = file_hashes(raw_dir)
    database = tmp_path / "snapshot.sqlite3"
    first = ingest_dataset(raw_dir, database)
    digest = database_digest(database)
    second = ingest_dataset(raw_dir, database)
    assert first.counts == second.counts == COUNTS
    assert first.foreign_key_violations == second.foreign_key_violations == 0
    assert database_digest(database) == digest
    assert file_hashes(raw_dir) == before
    with connect_database(database) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert (
            connection.execute("SELECT price_cents FROM products WHERE product_id=101").fetchone()[
                0
            ]
            == 10010
        )
        order = connection.execute("SELECT * FROM orders WHERE order_id=1").fetchone()
        assert order["total_cents"] == 99990  # Diverge do catálogo; nunca recalcular.
        assert order["tracking_code"] is None
        assert order["estimated_delivery"] is None
        assert order["notes"] is None
        assert (
            connection.execute("SELECT phone FROM customers WHERE customer_id=1").fetchone()[0]
            == "00000000001"
        )
        specs = connection.execute("SELECT specs FROM products WHERE product_id=102").fetchone()[0]
        assert json.loads(specs) == {"strings": "nylon", "color": "azul"}


def test_snapshot_refresh_removes_stale_rows(raw_dir: Path, tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite3"
    ingest_dataset(raw_dir, database)
    (raw_dir / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n", encoding="utf-8"
    )
    change_cell(raw_dir, "products", "price_brl", "123.45")
    result = ingest_dataset(raw_dir, database)
    assert result.counts["promotions"] == 0
    with connect_database(database) as connection:
        assert (
            connection.execute("SELECT price_cents FROM products WHERE product_id=101").fetchone()[
                0
            ]
            == 12345
        )
        assert (
            connection.execute("SELECT total_cents FROM orders WHERE order_id=1").fetchone()[0]
            == 99990
        )


def test_preserves_status_stock_and_promotions(raw_dir: Path, tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite3"
    ingest_dataset(raw_dir, database)
    with connect_database(database) as connection:
        for product_id, status, stock in [
            (101, "active", 0),
            (130, "coming_soon", 2),
            (136, "discontinued", 13),
        ]:
            row = connection.execute(
                "SELECT status, stock_quantity FROM products WHERE product_id=?", (product_id,)
            ).fetchone()
            assert tuple(row) == (status, stock)
        row = connection.execute(
            "SELECT price_cents, discount_percent, is_active FROM products "
            "JOIN promotions USING(product_id) WHERE product_id=127"
        ).fetchone()
        assert tuple(row) == (35900, 10, 1)
        assert (
            connection.execute("SELECT is_active FROM promotions WHERE product_id=102").fetchone()[
                0
            ]
            == 0
        )


@pytest.mark.parametrize(
    "table,field",
    [
        ("products", "category_id"),
        ("orders", "customer_id"),
        ("order_items", "order_id"),
        ("order_items", "product_id"),
        ("promotions", "product_id"),
    ],
)
def test_orphan_rejected_before_writing(
    raw_dir: Path, tmp_path: Path, table: str, field: str
) -> None:
    database = tmp_path / "snapshot.sqlite3"
    ingest_dataset(raw_dir, database)
    digest = database_digest(database)
    change_cell(raw_dir, table, field, "999999")
    report = load_dataset(raw_dir).report
    assert not report.valid
    assert any(issue.code == "foreign_key" and issue.field == field for issue in report.errors)
    with pytest.raises(DataQualityError):
        ingest_dataset(raw_dir, database)
    assert database_digest(database) == digest


@pytest.mark.parametrize("table", list(COUNTS))
def test_duplicate_primary_keys_rejected(raw_dir: Path, table: str) -> None:
    path = raw_dir / f"{table}.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    with path.open("a", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerow(rows[1])
    report = load_dataset(raw_dir).report
    assert not report.valid
    assert report.tables[table].duplicate_keys == 1


@pytest.mark.parametrize(
    "table,field,value",
    [
        ("products", "price_brl", "1.001"),
        ("products", "price_brl", "NaN"),
        ("orders", "total_brl", "Infinity"),
        ("products", "price_brl", "-1"),
        ("products", "price_brl", "92233720368547758.08"),
        ("products", "stock_quantity", "-1"),
        ("products", "stock_quantity", "1.5"),
        ("products", "status", "unknown"),
        ("orders", "status", "unknown"),
        ("products", "specs", "not JSON"),
        ("products", "specs", "[]"),
        ("products", "specs", '{"x": NaN}'),
        ("products", "specs", '{"x": 1e999}'),
        ("products", "specs", '{"x":1,"x":2}'),
        ("promotions", "is_active", "2"),
        ("promotions", "discount_percent", "101"),
        ("promotions", "discount_percent", "5.5"),
        ("orders", "order_date", "2026-02-30"),
        ("orders", "estimated_delivery", "2026-02-30"),
        ("products", "created_at", "1234567890"),
        ("order_items", "quantity", "0"),
        ("customers", "name", " "),
    ],
)
def test_invalid_values_rejected(
    raw_dir: Path, tmp_path: Path, table: str, field: str, value: str
) -> None:
    change_cell(raw_dir, table, field, value)
    report = load_dataset(raw_dir).report
    assert not report.valid
    assert report.tables[table].invalid_rows >= 1
    database = tmp_path / "invalid.sqlite3"
    with pytest.raises(DataQualityError):
        ingest_dataset(raw_dir, database)
    assert not database.exists()


def test_sqlite_failure_rolls_back_all_tables(raw_dir: Path, tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite3"
    ingest_dataset(raw_dir, database)
    with connect_database(database) as connection:
        connection.execute(
            "CREATE TRIGGER simulate_failure BEFORE INSERT ON promotions "
            "BEGIN SELECT RAISE(ABORT, 'simulated_failure'); END"
        )
    digest = database_digest(database)
    change_cell(raw_dir, "products", "name", "Alteração que deve sofrer rollback")
    with pytest.raises(IngestionError, match="database_write_failed"):
        ingest_dataset(raw_dir, database)
    assert database_digest(database) == digest


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE products SET stock_quantity=-1 WHERE product_id=101",
        "UPDATE products SET status='unknown' WHERE product_id=101",
        "UPDATE products SET category_id=99999 WHERE product_id=101",
        "UPDATE products SET specs='[]' WHERE product_id=101",
        "UPDATE products SET specs='invalid' WHERE product_id=101",
        "UPDATE products SET price_cents=1.5 WHERE product_id=101",
        "UPDATE orders SET total_cents=-1 WHERE order_id=1",
        "UPDATE promotions SET is_active=2 WHERE promotion_id=1",
        "UPDATE promotions SET discount_percent=101 WHERE promotion_id=1",
        "INSERT INTO order_items VALUES (1, 2, 127)",
    ],
)
def test_database_constraints(raw_dir: Path, tmp_path: Path, statement: str) -> None:
    database = tmp_path / "snapshot.sqlite3"
    ingest_dataset(raw_dir, database)
    with connect_database(database) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(statement)


def test_diagnostic_never_contains_customer_values(raw_dir: Path) -> None:
    marker = "dado-privado@example.invalid"
    change_cell(raw_dir, "customers", "customer_id", marker)
    change_cell(raw_dir, "products", "specs", json.dumps({marker: float("inf")}))
    output = load_dataset(raw_dir).report.model_dump_json()
    assert marker not in output
    assert "Cliente Sintético" not in output
    assert "00000000001" not in output
    assert '"valid":false' in output


@pytest.mark.parametrize("problem", ["missing", "ambiguous", "header", "width", "encoding", "csv"])
def test_source_format_failures(raw_dir: Path, problem: str) -> None:
    path = raw_dir / "products.csv"
    if problem == "missing":
        path.unlink()
    elif problem == "ambiguous":
        shutil.copyfile(path, raw_dir / "desafio_tecnico_ai_eng - products.csv")
    elif problem == "header":
        path.write_text("product_id,unexpected\n1,x\n", encoding="utf-8")
    elif problem == "width":
        with path.open("a", encoding="utf-8") as stream:
            stream.write("999,missing_fields\n")
    elif problem == "encoding":
        path.write_bytes(b"\xff\xfe")
    else:
        with path.open("a", encoding="utf-8") as stream:
            stream.write('"unclosed')
    assert not load_dataset(raw_dir).report.valid


def test_prefixed_files_bom_and_optional_whitespace(raw_dir: Path, tmp_path: Path) -> None:
    change_cell(raw_dir, "orders", "tracking_code", "   ")
    for path in raw_dir.glob("*.csv"):
        content = path.read_text(encoding="utf-8")
        path.rename(path.with_name(f"desafio_tecnico_ai_eng - {path.name}")).write_text(
            content, encoding="utf-8-sig"
        )
    # Path.rename retorna o destino: acrescenta BOM preservando o conteúdo lógico.
    report = load_dataset(raw_dir).report
    assert report.valid
    assert report.tables["orders"].null_counts["tracking_code"] == 1
    assert ingest_dataset(raw_dir, tmp_path / "snapshot.sqlite3").counts == COUNTS


def test_sources_cannot_be_overwritten(raw_dir: Path) -> None:
    before = file_hashes(raw_dir)
    with pytest.raises(IngestionError, match="unsafe_output_path"):
        ingest_dataset(raw_dir, raw_dir / "snapshot.sqlite3")
    assert file_hashes(raw_dir) == before


def test_unrelated_database_is_preserved(raw_dir: Path, tmp_path: Path) -> None:
    database = tmp_path / "unrelated.sqlite3"
    with connect_database(database) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('keep')")
    digest = database_digest(database)
    with pytest.raises(IngestionError, match="unsupported_database"):
        ingest_dataset(raw_dir, database)
    assert database_digest(database) == digest


@pytest.mark.parametrize("script", ["inspect_data.py", "ingest_data.py"])
def test_scripts_success_and_invalid_input(raw_dir: Path, tmp_path: Path, script: str) -> None:
    command = [sys.executable, str(PROJECT / "scripts" / script), "--raw-dir", str(raw_dir)]
    if script == "ingest_data.py":
        command.extend(["--database", str(tmp_path / "cli.sqlite3")])
    else:
        command.extend(["--report", str(tmp_path / "report.json")])
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    if script == "inspect_data.py":
        assert payload["valid"]
        assert json.loads((tmp_path / "report.json").read_text()) == payload
    else:
        assert payload["counts"] == COUNTS
    change_cell(raw_dir, "products", "price_brl", "invalid")
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert "Traceback" not in result.stdout + result.stderr

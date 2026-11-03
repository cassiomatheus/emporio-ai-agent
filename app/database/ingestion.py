"""Reconstrução atômica e idempotente das seis tabelas do snapshot local."""

import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.database.connection import connect_database
from app.database.dataset import DataQualityError, load_dataset
from app.database.models import ROW_MODELS, SourceRow, to_cents
from app.database.schema import APPLICATION_ID, SCHEMA_STATEMENTS, SCHEMA_VERSION

COLUMN_MAPPING = {"price_brl": "price_cents", "total_brl": "total_cents"}


class IngestionError(ValueError):
    """Código técnico seguro para apresentação, sem conteúdo das fontes."""


class IngestionResult(BaseModel):
    counts: dict[str, int]
    foreign_key_violations: int


def protect_output(path: Path, raw_dir: Path, suffixes: set[str]) -> None:
    """Impede que um destino de relatório/banco sobrescreva as fontes brutas."""
    target = path.resolve()
    if target.is_relative_to(raw_dir.resolve()) or target.suffix not in suffixes:
        raise IngestionError("unsafe_output_path")


def _sql_values(row: SourceRow) -> tuple[Any, ...]:
    values = []
    for field, value in row.model_dump().items():
        if isinstance(value, Decimal):
            value = to_cents(value)
        elif isinstance(value, date):
            value = value.isoformat()
        elif field == "specs":
            value = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        values.append(value)
    return tuple(values)


def _validate_database(connection: sqlite3.Connection) -> None:
    application_id = connection.execute("PRAGMA application_id").fetchone()[0]
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    if (tables and application_id != APPLICATION_ID) or version not in (0, SCHEMA_VERSION):
        raise IngestionError("unsupported_database")


def ingest_dataset(raw_dir: Path, database: Path) -> IngestionResult:
    """Substitui o snapshot completo; qualquer falha preserva o anterior."""
    protect_output(database, raw_dir, {".sqlite3", ".sqlite", ".db"})
    dataset = load_dataset(raw_dir)
    if not dataset.report.valid:
        raise DataQualityError(dataset.report)
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
        with connect_database(database) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                _validate_database(connection)
                for statement in SCHEMA_STATEMENTS:
                    connection.execute(statement)
                for table in reversed(ROW_MODELS):
                    connection.execute(f"DELETE FROM {table}")
                for table, model in ROW_MODELS.items():
                    columns = [COLUMN_MAPPING.get(field, field) for field in model.model_fields]
                    placeholders = ", ".join("?" for _ in columns)
                    # Identificadores vêm exclusivamente dos contratos estáticos, nunca dos CSVs.
                    connection.executemany(
                        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                        [_sql_values(row) for row in dataset.tables[table]],
                    )
                violations = connection.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise IngestionError("foreign_key_check_failed")
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise IngestionError("integrity_check_failed")
                counts = {
                    table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                    for table in ROW_MODELS
                }
                if counts != {table: len(rows) for table, rows in dataset.tables.items()}:
                    raise IngestionError("count_mismatch")
                connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return IngestionResult(counts=counts, foreign_key_violations=len(violations))
    except (OSError, sqlite3.Error) as exc:
        raise IngestionError("database_write_failed") from exc

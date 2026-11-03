"""Leitura imutável dos seis CSVs e diagnóstico sanitizado de qualidade."""

import csv
import hashlib
import io
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.database.models import FOREIGN_KEYS, PRIMARY_KEYS, ROW_MODELS, SourceRow, to_cents


class QualityIssue(BaseModel):
    table: str
    code: str
    field: str | None = None
    row: int | None = None


class TableQuality(BaseModel):
    source_name: str | None = None
    sha256: str | None = None
    columns: list[str]
    rows: int = 0
    null_counts: dict[str, int] = Field(default_factory=dict)
    invalid_rows: int = 0
    duplicate_keys: int = 0


class QualityReport(BaseModel):
    valid: bool = False
    tables: dict[str, TableQuality] = Field(default_factory=dict)
    foreign_key_violations: dict[str, int] = Field(default_factory=dict)
    errors: list[QualityIssue] = Field(default_factory=list)
    observations: dict[str, Any] = Field(default_factory=dict)


@dataclass
class Dataset:
    tables: dict[str, list[SourceRow]]
    report: QualityReport


class DataQualityError(ValueError):
    """Apenas o relatório sanitizado pode ser exibido; nenhuma linha bruta."""

    def __init__(self, report: QualityReport) -> None:
        super().__init__("invalid_dataset")
        self.report = report


def _read_table(raw_dir: Path, table: str, report: QualityReport) -> list[SourceRow]:
    model = ROW_MODELS[table]
    columns = list(model.model_fields)
    quality = TableQuality(columns=columns, null_counts=dict.fromkeys(columns, 0))
    report.tables[table] = quality
    candidates = [raw_dir / f"{table}.csv", raw_dir / f"desafio_tecnico_ai_eng - {table}.csv"]
    matches = [path for path in candidates if path.is_file()]
    if len(matches) != 1:
        code = "missing_source" if not matches else "ambiguous_source"
        report.errors.append(QualityIssue(table=table, code=code))
        return []
    path = matches[0]
    quality.source_name = path.name
    try:
        content = path.read_bytes()
        quality.sha256 = hashlib.sha256(content).hexdigest()
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        if (
            reader.fieldnames is None
            or len(reader.fieldnames) != len(columns)
            or set(reader.fieldnames) != set(columns)
        ):
            report.errors.append(QualityIssue(table=table, code="invalid_columns"))
            return []
        parsed = []
        for number, raw in enumerate(reader, start=2):
            quality.rows += 1
            if None in raw or any(value is None for value in raw.values()):
                quality.invalid_rows += 1
                report.errors.append(QualityIssue(table=table, code="invalid_width", row=number))
                continue
            normalized = {key: value if value.strip() else None for key, value in raw.items()}
            for key, value in normalized.items():
                quality.null_counts[key] += value is None
            try:
                parsed.append(model.model_validate(normalized))
            except ValidationError as exc:
                quality.invalid_rows += 1
                for error in exc.errors(
                    include_input=False, include_context=False, include_url=False
                ):
                    # Chaves internas de specs podem ser sensíveis; expor apenas o campo raiz.
                    field = str(error["loc"][0]) if error["loc"] else None
                    report.errors.append(
                        QualityIssue(table=table, code=error["type"], field=field, row=number)
                    )
        return parsed
    except (OSError, UnicodeError, csv.Error):
        report.errors.append(QualityIssue(table=table, code="unreadable_source"))
        return []


def load_dataset(raw_dir: Path) -> Dataset:
    """Valida o snapshot inteiro em memória antes de qualquer escrita no banco."""
    report = QualityReport()
    tables = {table: _read_table(raw_dir, table, report) for table in ROW_MODELS}
    for table, rows in tables.items():
        keys = [tuple(getattr(row, column) for column in PRIMARY_KEYS[table]) for row in rows]
        duplicates = len(keys) - len(set(keys))
        report.tables[table].duplicate_keys = duplicates
        if duplicates:
            report.errors.append(QualityIssue(table=table, code="duplicate_key"))
    for table, field, parent, parent_field in FOREIGN_KEYS:
        parent_ids = {getattr(row, parent_field) for row in tables[parent]}
        count = sum(getattr(row, field) not in parent_ids for row in tables[table])
        report.foreign_key_violations[f"{table}.{field}->{parent}.{parent_field}"] = count
        if count:
            report.errors.append(QualityIssue(table=table, code="foreign_key", field=field))
    report.valid = not report.errors
    if report.valid:
        report.observations = _observations(tables)
    return Dataset(tables=tables, report=report)


def _observations(tables: dict[str, list[SourceRow]]) -> dict[str, Any]:
    """Estatísticas e discrepâncias são derivadas; não alteram dados observados."""
    products = [row.model_dump() for row in tables["products"]]
    orders = [row.model_dump() for row in tables["orders"]]
    items = [row.model_dump() for row in tables["order_items"]]
    promotions = [row.model_dump() for row in tables["promotions"]]
    prices = {row["product_id"]: to_cents(row["price_brl"]) for row in products}
    differences = []
    for order in orders:
        current_sum = sum(
            prices[item["product_id"]] * item["quantity"]
            for item in items
            if item["order_id"] == order["order_id"]
        )
        historical = to_cents(order["total_brl"])
        if current_sum != historical:
            differences.append(
                {
                    "order_id": order["order_id"],
                    "difference_cents": current_sum - historical,
                }
            )
    dates = [order["order_date"].isoformat() for order in orders]
    return {
        "product_status_counts": dict(sorted(Counter(row["status"] for row in products).items())),
        "order_status_counts": dict(sorted(Counter(row["status"] for row in orders).items())),
        "promotion_active_counts": dict(
            sorted(Counter(str(row["is_active"]) for row in promotions).items())
        ),
        "zero_stock_products": sum(row["stock_quantity"] == 0 for row in products),
        "non_active_positive_stock_product_ids": sorted(
            row["product_id"]
            for row in products
            if row["status"] != "active" and row["stock_quantity"] > 0
        ),
        "specs_valid_objects": len(products),
        "order_date_min": min(dates) if dates else None,
        "order_date_max": max(dates) if dates else None,
        "historical_total_differences": differences,
        "limitations": [
            "snapshot_not_live",
            "no_promotion_dates",
            "no_actual_delivery_date",
            "current_catalog_sum_is_not_purchase_total",
        ],
    }

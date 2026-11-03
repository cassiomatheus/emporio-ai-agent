"""Leituras SQLite parametrizadas, sem cálculos comerciais nem liberação de acesso."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import JsonValue

from app.database.connection import connect_database


@dataclass(frozen=True)
class ProductRecord:
    product_id: int
    name: str
    category_id: int
    category_name: str
    price_cents: int
    description: str
    stock_quantity: int
    status: str
    specs: dict[str, JsonValue]


@dataclass(frozen=True)
class PromotionRecord:
    promotion_id: int
    product_id: int
    discount_percent: int
    is_active: int


@dataclass(frozen=True)
class OrderItemRecord:
    product_id: int
    name: str
    quantity: int


@dataclass(frozen=True)
class OrderRecord:
    order_id: int
    customer_id: int = field(repr=False)
    order_date: str
    status: str
    total_cents: int
    payment_method: str
    tracking_code: str | None
    estimated_delivery: str | None
    items: tuple[OrderItemRecord, ...]


class ProductRepository(Protocol):
    def list_products(self) -> tuple[ProductRecord, ...]: ...

    def get_product(self, product_id: int) -> ProductRecord | None: ...


class PricingRepository(Protocol):
    def get_pricing_data(
        self, product_id: int
    ) -> tuple[ProductRecord, tuple[PromotionRecord, ...]] | None: ...


class OrderRepository(Protocol):
    def get_authorized_order(self, order_id: int, customer_id: int) -> OrderRecord | None: ...


class RepositoryError(RuntimeError):
    """Falha técnica sem caminho de arquivo, SQL ou dados de clientes na mensagem."""


@contextmanager
def _read_snapshot(database: Path) -> Iterator[sqlite3.Connection]:
    try:
        # mode=ro impede criar um banco vazio quando o caminho está incorreto.
        with connect_database(database, read_only=True) as connection:
            connection.execute("BEGIN")
            yield connection
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError) as exc:
        raise RepositoryError("repository_unavailable") from exc


PRODUCT_SELECT = """SELECT p.product_id, p.name, p.category_id, c.name AS category_name,
    p.price_cents, p.description, p.stock_quantity, p.status, p.specs
    FROM products p JOIN categories c ON c.category_id = p.category_id"""


def _product(row: sqlite3.Row) -> ProductRecord:
    data = dict(row)
    data["specs"] = json.loads(data["specs"])
    return ProductRecord(**data)


class SQLiteProductRepository:
    def __init__(self, database: Path) -> None:
        self.database = database

    def list_products(self) -> tuple[ProductRecord, ...]:
        with _read_snapshot(self.database) as connection:
            return tuple(
                _product(row)
                for row in connection.execute(PRODUCT_SELECT + " ORDER BY p.product_id")
            )

    def get_product(self, product_id: int) -> ProductRecord | None:
        with _read_snapshot(self.database) as connection:
            row = connection.execute(
                PRODUCT_SELECT + " WHERE p.product_id = ?", (product_id,)
            ).fetchone()
            return _product(row) if row else None


class SQLitePricingRepository:
    def __init__(self, database: Path) -> None:
        self.database = database

    def get_pricing_data(
        self, product_id: int
    ) -> tuple[ProductRecord, tuple[PromotionRecord, ...]] | None:
        with _read_snapshot(self.database) as connection:
            row = connection.execute(
                PRODUCT_SELECT + " WHERE p.product_id = ?", (product_id,)
            ).fetchone()
            if row is None:
                return None
            promotions = tuple(
                PromotionRecord(**dict(promotion))
                for promotion in connection.execute(
                    "SELECT promotion_id, product_id, discount_percent, is_active "
                    "FROM promotions WHERE product_id = ? ORDER BY promotion_id",
                    (product_id,),
                )
            )
            return _product(row), promotions


class SQLiteOrderRepository:
    def __init__(self, database: Path) -> None:
        self.database = database

    def get_authorized_order(self, order_id: int, customer_id: int) -> OrderRecord | None:
        with _read_snapshot(self.database) as connection:
            row = connection.execute(
                "SELECT order_id, customer_id, order_date, status, total_cents, payment_method, "
                "tracking_code, estimated_delivery FROM orders "
                "WHERE order_id = ? AND customer_id = ?",
                (order_id, customer_id),
            ).fetchone()
            if row is None:
                return None
            items = tuple(
                OrderItemRecord(**dict(item))
                for item in connection.execute(
                    "SELECT i.product_id, p.name, i.quantity FROM order_items i "
                    "JOIN products p ON p.product_id = i.product_id "
                    "JOIN orders o ON o.order_id = i.order_id "
                    "WHERE o.order_id = ? AND o.customer_id = ? ORDER BY i.product_id",
                    (order_id, customer_id),
                )
            )
            return OrderRecord(**dict(row), items=items)

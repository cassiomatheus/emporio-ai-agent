"""Registros sintéticos para testar serviços sem abrir SQLite."""

import pytest

from app.database.repository import ProductRecord


@pytest.fixture
def product() -> ProductRecord:
    return ProductRecord(
        product_id=81,
        name="Violão Sintético Nylon",
        category_id=5,
        category_name="Violões",
        price_cents=59990,
        description="Instrumento sintético",
        stock_quantity=3,
        status="active",
        specs={"strings": "nylon", "electronics": "no"},
    )

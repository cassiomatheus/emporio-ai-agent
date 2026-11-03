"""Contratos das linhas CSV, sem inferir regras comerciais ou identidade."""

import json
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, JsonValue, field_validator

SQLITE_MAX_INTEGER = 2**63 - 1
Identifier = Annotated[int, Field(gt=0, le=SQLITE_MAX_INTEGER)]
NonemptyText = Annotated[str, Field(min_length=1)]
Money = Annotated[
    Decimal,
    Field(ge=0, le=Decimal("92233720368547758.07"), max_digits=19, decimal_places=2),
]


def parse_date(value: Any) -> date:
    """Aceita datas ISO, sem converter timestamps numéricos em datas."""
    if isinstance(value, str):
        if len(value) != 10:
            raise ValueError("expected_iso_date")
        return date.fromisoformat(value)
    if type(value) is date:
        return value
    raise ValueError("expected_iso_date")


ISODate = Annotated[date, BeforeValidator(parse_date)]


class SourceRow(BaseModel):
    """Campos extras, números não finitos e entradas ocultas em erros são vedados."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)


class CategoryRow(SourceRow):
    category_id: Identifier
    name: NonemptyText
    description: NonemptyText


class ProductRow(SourceRow):
    product_id: Identifier
    price_brl: Money
    name: NonemptyText
    category_id: Identifier
    description: NonemptyText
    stock_quantity: Annotated[int, Field(ge=0, le=SQLITE_MAX_INTEGER)]
    status: Literal["active", "discontinued", "coming_soon"]
    specs: dict[str, JsonValue]
    created_at: ISODate

    @field_validator("specs", mode="before")
    @classmethod
    def parse_specs(cls, value: Any) -> Any:
        """Rejeita JSON não padrão e chaves repetidas, sem perda silenciosa."""
        if not isinstance(value, str):
            return value

        def reject_constant(_: str) -> None:
            raise ValueError("nonfinite_json")

        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError("duplicate_json_key")
                result[key] = item
            return result

        return json.loads(value, parse_constant=reject_constant, object_pairs_hook=unique_object)


class CustomerRow(SourceRow):
    customer_id: Identifier
    name: NonemptyText
    phone: NonemptyText
    email: NonemptyText
    city: NonemptyText


class OrderRow(SourceRow):
    order_id: Identifier
    customer_id: Identifier
    order_date: ISODate
    status: Literal["delivered", "confirmed", "pending", "cancelled", "shipped"]
    total_brl: Money
    payment_method: NonemptyText
    tracking_code: NonemptyText | None = None
    estimated_delivery: ISODate | None = None
    notes: NonemptyText | None = None


class OrderItemRow(SourceRow):
    order_id: Identifier
    quantity: Annotated[int, Field(gt=0, le=SQLITE_MAX_INTEGER)]
    product_id: Identifier


class PromotionRow(SourceRow):
    promotion_id: Identifier
    product_id: Identifier
    discount_percent: Annotated[int, Field(ge=0, le=100)]
    description: NonemptyText
    is_active: Literal[0, 1]

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_flag(cls, value: Any) -> Any:
        if value in ("0", "1"):
            return int(value)
        return value


ROW_MODELS: dict[str, type[SourceRow]] = {
    "categories": CategoryRow,
    "products": ProductRow,
    "customers": CustomerRow,
    "orders": OrderRow,
    "order_items": OrderItemRow,
    "promotions": PromotionRow,
}

PRIMARY_KEYS = {
    "categories": ("category_id",),
    "products": ("product_id",),
    "customers": ("customer_id",),
    "orders": ("order_id",),
    "order_items": ("order_id", "product_id"),
    "promotions": ("promotion_id",),
}

FOREIGN_KEYS = (
    ("products", "category_id", "categories", "category_id"),
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("promotions", "product_id", "products", "product_id"),
)


def to_cents(value: Decimal) -> int:
    """Conversão exata após a validação de no máximo duas casas decimais."""
    return int(value * 100)

"""Contratos internos validados para buscas, ofertas e pedidos protegidos."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    model_validator,
)


def _reject_float(value: Any) -> Any:
    if isinstance(value, (float, bool)):
        raise ValueError("use_decimal_or_text_for_money")
    return value


Identifier = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
ID_ADAPTER = TypeAdapter(Identifier)
Money = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(ge=0, le=Decimal("92233720368547758.07"), decimal_places=2, allow_inf_nan=False),
]
PaymentMethod = Literal["pix", "credit", "debit", "boleto"]
ProductStatus = Literal["active", "discontinued", "coming_soon"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ProductSearch(Contract):
    term: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    name_terms: Annotated[tuple[str, ...], Field(max_length=4)] = ()
    category: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    category_id: Identifier | None = None
    min_price: Money | None = None
    max_price: Money | None = None
    specs: Annotated[dict[str, JsonValue], Field(max_length=10)] = Field(default_factory=dict)
    available_only: bool = True
    status: ProductStatus | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 20
    offset: Annotated[int, Field(strict=True, ge=0, le=10000)] = 0

    @model_validator(mode="after")
    def valid_filters(self) -> "ProductSearch":
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("invalid_price_range")
        if any(value is not None and not value.strip() for value in (self.term, self.category)):
            raise ValueError("blank_search_filter")
        if any(not key.strip() or len(key) > 64 for key in self.specs):
            raise ValueError("invalid_spec_key")
        if any(not term.strip() or len(term) > 120 for term in self.name_terms):
            raise ValueError("invalid_name_term")
        return self


class CatalogFacet(Contract):
    category_id: int
    category_name: str
    name: str
    specs: dict[str, JsonValue]


class ProductDetails(Contract):
    product_id: int
    name: str
    category_id: int
    category_name: str
    price_brl: Money
    description: str
    stock_quantity: int
    status: ProductStatus
    specs: dict[str, JsonValue]
    available: bool
    availability_reason: Literal["available", "out_of_stock", "discontinued", "coming_soon"]


class ProductPage(Contract):
    items: tuple[ProductDetails, ...]
    total: int
    limit: int
    offset: int


class InstallmentPlan(Contract):
    count: int
    amounts: tuple[Money, ...]
    total_brl: Money
    minimum_brl: Money
    interest_percent: Decimal = Decimal("0")


class PaymentOffer(Contract):
    payment_method: PaymentMethod
    discount_percent: Decimal
    final_price: Money
    discount_source: Literal["promotion", "pix", "none"]
    promotion_id: int | None = None
    eligible_installments: tuple[InstallmentPlan, ...] = ()


class ProductOffers(Contract):
    product_id: int
    original_price: Money
    options: tuple[PaymentOffer, ...]


class QuoteRequest(Contract):
    product_id: Identifier
    payment_method: PaymentMethod
    installments: Annotated[int, Field(strict=True, ge=1, le=12)] = 1

    @model_validator(mode="after")
    def credit_only_installments(self) -> "QuoteRequest":
        if self.payment_method != "credit" and self.installments != 1:
            raise ValueError("installments_require_credit")
        return self


class PriceQuote(PaymentOffer):
    product_id: int
    original_price: Money
    selected_plan: InstallmentPlan | None = None


class OrderAccessContext(Contract):
    """Apenas o backend pode fornecer esta autorização; não é prova de login real."""

    authorized_customer_id: Identifier | None = Field(default=None, repr=False)


class OrderItem(Contract):
    product_id: int
    name: str
    quantity: int


class OrderStatus(Contract):
    order_id: int
    order_date: date
    status: Literal["delivered", "confirmed", "pending", "cancelled", "shipped"]
    total_brl: Money
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    tracking_status: Literal["available", "not_provided"]
    items: tuple[OrderItem, ...]

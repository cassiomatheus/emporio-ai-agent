"""Contratos públicos das tools; identidade autorizada nunca é parâmetro de entrada."""

import re
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from app.retrieval.models import PolicyHit
from app.services.models import (
    Identifier,
    InstallmentPlan,
    Money,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    PaymentOffer,
    ProductDetails,
    ProductStatus,
)
from app.services.policy_service import StoreInfo


def _money_input(value: object) -> Decimal:
    if type(value) is int:
        return Decimal(value)
    if (
        isinstance(value, str)
        and len(value) <= 20
        and re.fullmatch(r"\d{1,17}(?:\.\d{1,2})?", value)
    ):
        return Decimal(value)
    raise ValueError("expected_decimal_text_or_integer")


MoneyText = Annotated[str, Field(max_length=20, pattern=r"^\d{1,17}(?:\.\d{1,2})?$")]
MoneyInteger = Annotated[int, Field(ge=0, le=92233720368547758)]
ToolMoney = Annotated[
    Money,
    BeforeValidator(_money_input, json_schema_input_type=MoneyText | MoneyInteger),
]
SpecKey = Annotated[str, Field(min_length=1, max_length=64)]
SpecValue = Annotated[str, Field(min_length=1, max_length=120)] | int | float | bool


class Arguments(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        hide_input_in_errors=True,
    )

    @field_validator("term", "category", "name", "query", check_fields=False)
    @classmethod
    def nonblank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("blank_text")
        return value.strip() if value is not None else None


class SearchProductsInput(Arguments):
    term: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    name_terms: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=120)]], Field(max_length=4)
    ] = Field(default_factory=list)
    category: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    category_id: Identifier | None = None
    min_price: ToolMoney | None = None
    max_price: ToolMoney | None = None
    specs: Annotated[dict[SpecKey, SpecValue], Field(max_length=10)] = Field(default_factory=dict)
    available_only: bool = True
    status: ProductStatus | None = None
    limit: Annotated[int, Field(ge=1, le=20)] = 10
    offset: Annotated[int, Field(ge=0, le=10000)] = 0

    @model_validator(mode="after")
    def valid_filters(self) -> "SearchProductsInput":
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("invalid_price_range")
        if any(not key.strip() for key in self.specs):
            raise ValueError("blank_spec_key")
        if any(not term.strip() for term in self.name_terms):
            raise ValueError("blank_name_term")
        return self


class ProductDetailsInput(Arguments):
    product_id: Identifier | None = None
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None

    @model_validator(mode="after")
    def one_identifier(self) -> "ProductDetailsInput":
        if (self.product_id is None) == (self.name is None):
            raise ValueError("choose_id_or_exact_name")
        return self


class ProductOffersInput(Arguments):
    product_id: Identifier
    payment_method: PaymentMethod | None = None
    installments: Annotated[int, Field(ge=1, le=12)] | None = None

    @model_validator(mode="after")
    def valid_payment_context(self) -> "ProductOffersInput":
        if self.installments is not None and self.payment_method is None:
            raise ValueError("payment_method_required")
        if self.payment_method != "credit" and self.installments not in (None, 1):
            raise ValueError("installments_require_credit")
        return self


class OrderStatusInput(Arguments):
    order_id: Identifier


class PolicySearchInput(Arguments):
    query: Annotated[str, Field(min_length=1, max_length=500)]
    top_k: Annotated[int, Field(ge=1, le=5)] = 3


class StoreInfoInput(Arguments):
    subject: Literal["address", "hours", "contacts"]


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class SearchProductsData(OutputModel):
    items: Annotated[tuple[ProductDetails, ...], Field(max_length=20)]
    total: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=20)]
    offset: Annotated[int, Field(ge=0, le=10000)]

    @model_validator(mode="after")
    def bounded_page(self) -> "SearchProductsData":
        if len(self.items) > self.limit or len(self.items) > self.total:
            raise ValueError("invalid_result_page")
        return self


class ProductOffersData(OutputModel):
    product_id: int
    original_price: Money
    options: Annotated[tuple[PaymentOffer, ...], Field(min_length=1, max_length=4)]
    selected_plan: InstallmentPlan | None = None
    applied_rules: tuple[str, ...] = ("RN-01", "RN-02", "RN-03", "RN-04", "RN-05", "RN-11")


class OrderStatusData(OrderStatus):
    items: Annotated[tuple[OrderItem, ...], Field(max_length=100)]


class ToolPolicyHit(PolicyHit):
    excerpt: Annotated[str, Field(min_length=1, max_length=420)]


class PolicyMatchesData(OutputModel):
    status: Literal["matched"]
    hits: Annotated[tuple[ToolPolicyHit, ...], Field(min_length=1, max_length=5)]


ErrorCode = Literal[
    "unknown_tool",
    "invalid_arguments",
    "not_found",
    "ambiguous",
    "unavailable",
    "invalid_installments",
    "forbidden",
    "no_evidence",
    "service_unavailable",
    "response_too_large",
]


class ToolError(OutputModel):
    code: ErrorCode
    message: str
    invalid_fields: tuple[str, ...] = ()


Payload = TypeVar("Payload", bound=BaseModel)


class ToolResponse(OutputModel, Generic[Payload]):
    status: Literal["ok", "error"]
    data: Payload | None
    error: ToolError | None

    @model_validator(mode="after")
    def exclusive_result(self) -> "ToolResponse[Payload]":
        if self.status == "ok" and (self.data is None or self.error is not None):
            raise ValueError("invalid_success_envelope")
        if self.status == "error" and (self.data is not None or self.error is None):
            raise ValueError("invalid_error_envelope")
        return self


# Tipos concretos exportados para gerar contratos de saída sem depender do provedor.
RESPONSE_MODELS = {
    "search_products": ToolResponse[SearchProductsData],
    "get_product_details": ToolResponse[ProductDetails],
    "get_product_offers": ToolResponse[ProductOffersData],
    "get_order_status": ToolResponse[OrderStatusData],
    "search_store_policies": ToolResponse[PolicyMatchesData],
    "get_store_info": ToolResponse[StoreInfo],
}

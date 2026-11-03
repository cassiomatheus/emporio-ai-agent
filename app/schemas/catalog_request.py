"""Pedido semântico de catálogo, separado dos parâmetros de consulta."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.models import ProductStatus
from app.tools.schemas import SearchProductsInput, SpecKey, SpecValue, ToolMoney


class IntentModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
        hide_input_in_errors=True,
    )


class ProductCriteria(IntentModel):
    category: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    subtype: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None

    @field_validator("category", "subtype", "name")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("blank_product_criterion")
        return value.strip() if value is not None else None


class CatalogSearchRequest(IntentModel):
    intent: Literal["search_products"] = "search_products"
    product: ProductCriteria
    characteristics: Annotated[dict[SpecKey, SpecValue], Field(max_length=10)] = Field(
        default_factory=dict
    )
    min_price: ToolMoney | None = None
    max_price: ToolMoney | None = None
    available_only: bool = True
    status: ProductStatus | None = None
    limit: Annotated[int, Field(ge=1, le=20)] = 10
    offset: Annotated[int, Field(ge=0, le=10000)] = 0

    @field_validator("product", "characteristics", mode="before")
    @classmethod
    def decode_object_transport(cls, value: object) -> object:
        # Alguns modelos locais codificam objetos aninhados como strings JSON.
        # Decodificar só um nível, sem aceitar Python, listas ou chaves duplicadas.
        if not isinstance(value, str):
            return value
        if len(value.encode("utf-8")) > 4096:
            raise ValueError("nested_object_too_large")

        def unique(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError("duplicate_nested_key")
                result[key] = item
            return result

        def reject_constant(constant):
            raise ValueError("invalid_nested_constant")

        parsed = json.loads(value, object_pairs_hook=unique, parse_constant=reject_constant)
        if not isinstance(parsed, dict):
            raise ValueError("expected_nested_object")
        return parsed

    @model_validator(mode="after")
    def valid_budget(self) -> "CatalogSearchRequest":
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("contradictory_budget")
        return self


class CatalogInterpretation(IntentModel):
    request: CatalogSearchRequest = Field(repr=False)
    query: SearchProductsInput = Field(repr=False)
    source: Literal["semantic", "legacy"]

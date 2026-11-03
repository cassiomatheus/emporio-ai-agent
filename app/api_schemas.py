"""Contratos HTTP: sem identidade declarada, SQL, caminhos ou parâmetros de tools."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.runtime import ExecutionMode
from app.tools.schemas import ErrorCode

OpaqueToken = Annotated[
    str, Field(strict=True, min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$")
]


class HttpModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class SessionCreate(HttpModel):
    """Objeto vazio: a API cria apenas visitante sem acesso a pedidos."""


class SessionCreated(HttpModel):
    session_id: OpaqueToken
    session_token: OpaqueToken = Field(repr=False)
    expires_in_seconds: float
    access: Literal["guest"] = "guest"
    execution_mode: ExecutionMode


class ChatRequest(HttpModel):
    session_id: OpaqueToken
    message: Annotated[str, Field(strict=True, min_length=1, max_length=2000, repr=False)]

    @field_validator("message")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank_message")
        return value


class ToolSummary(HttpModel):
    """Rastro público sem IDs de chamadas, argumentos ou conteúdo das fontes."""

    name: Literal[
        "search_products",
        "get_product_details",
        "get_product_offers",
        "get_order_status",
        "search_store_policies",
        "get_store_info",
        "unknown_tool",
    ]
    status: Literal["ok", "error"]
    error_code: ErrorCode | Literal["timeout"] | None = None


class ChatResponse(HttpModel):
    status: Literal["answered", "abstained"]
    text: str
    rounds: int
    execution_mode: ExecutionMode
    tools: Annotated[tuple[ToolSummary, ...], Field(max_length=32)] = ()


class HealthResponse(HttpModel):
    status: Literal["ok"] = "ok"
    chat_ready: bool
    execution_mode: ExecutionMode
    private_orders_enabled: Literal[False] = False


class HttpError(HttpModel):
    code: str
    message: str


class ErrorResponse(HttpModel):
    error: HttpError

"""Contratos independentes do provedor, com rastros sem prompts ou dados das tools."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.catalog_request import CatalogInterpretation
from app.tools.schemas import SearchProductsInput


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class AgentRequest(AgentModel):
    message: Annotated[str, Field(strict=True, min_length=1, max_length=2000, repr=False)]


class FunctionCall(AgentModel):
    call_id: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")]
    name: Annotated[str, Field(min_length=1, max_length=64)]
    arguments: Annotated[str, Field(max_length=8192)] = Field(repr=False)


class TokenUsage(AgentModel):
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    total_tokens: Annotated[int, Field(ge=0)]


class ModelTurn(AgentModel):
    calls: tuple[FunctionCall, ...] = ()
    final_text: Annotated[str, Field(max_length=8000)] | None = Field(default=None, repr=False)
    output_items: tuple[dict, ...] = Field(default=(), repr=False, exclude=True)
    usage: TokenUsage | None = None


class AnswerPlan(AgentModel):
    intent: Literal["answer", "clarify", "greeting", "out_of_scope", "handoff"]
    evidence_call_ids: Annotated[tuple[str, ...], Field(max_length=6)] = ()
    clarification: (
        Literal["product", "category", "budget", "specs", "rephrase", "receipt_date"] | None
    ) = None

    @model_validator(mode="after")
    def check_plan(self) -> "AnswerPlan":
        if len(self.evidence_call_ids) != len(set(self.evidence_call_ids)):
            raise ValueError("duplicate_evidence")
        if self.intent == "answer" and not self.evidence_call_ids:
            raise ValueError("evidence_required")
        if self.intent != "answer" and self.evidence_call_ids:
            raise ValueError("unexpected_evidence")
        if (self.intent == "clarify") != (self.clarification is not None):
            raise ValueError("invalid_clarification")
        return self


class AgentLimits(AgentModel):
    max_rounds: Annotated[int, Field(ge=1, le=8)] = 4
    max_tool_calls: Annotated[int, Field(ge=1, le=32)] = 12
    max_calls_per_round: Annotated[int, Field(ge=1, le=8)] = 4
    timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 30
    tool_timeout_seconds: Annotated[float, Field(gt=0, le=30)] = 5
    request_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 20
    max_output_tokens: Annotated[int, Field(ge=128, le=4096)] = 1200


class ToolTrace(AgentModel):
    call_id: str
    name: str
    status: Literal["ok", "error"]
    error_code: str | None = None


class SearchPage(AgentModel):
    """Cursor privado: filtros validados e posição, sem preços ou estoque em cache."""

    query: SearchProductsInput = Field(repr=False)
    returned_count: Annotated[int, Field(ge=0, le=20)]

    @model_validator(mode="after")
    def valid_count(self) -> "SearchPage":
        if self.returned_count > self.query.limit:
            raise ValueError("invalid_page_size")
        return self

    @property
    def next_offset(self) -> int:
        return self.query.offset + self.returned_count


class AgentResult(AgentModel):
    status: Literal[
        "answered",
        "abstained",
        "timeout",
        "round_limit",
        "call_limit",
        "provider_error",
        "protocol_error",
    ]
    text: str
    rounds: int
    tools: tuple[ToolTrace, ...]
    usage: TokenUsage | None = None
    # Somente o backend recebe esta atualização de referências verificadas.
    reference_ids: tuple[int, ...] | None = Field(default=None, exclude=True, repr=False)
    search_page: SearchPage | None = Field(default=None, exclude=True, repr=False)
    catalog_interpretations: Annotated[tuple[CatalogInterpretation, ...], Field(max_length=32)] = (
        Field(
            default=(),
            exclude=True,
            repr=False,
        )
    )

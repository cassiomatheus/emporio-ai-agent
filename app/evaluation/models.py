"""Dataset público, versionado, sem respostas privadas ou critérios de LLM-juiz."""

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

CATEGORY_COUNTS = {
    "catalog": 8,
    "pricing": 6,
    "policies": 8,
    "orders": 6,
    "multi_step": 5,
    "robustness": 7,
}


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Check(EvaluationModel):
    path: str
    op: Literal["equals", "contains_all", "not_contains"] = "equals"
    value: Any


class ReferenceCall(EvaluationModel):
    name: str
    arguments: dict
    match_arguments: dict | None = None
    checks: tuple[Check, ...] = ()


class EvaluationStep(EvaluationModel):
    question: Annotated[str, Field(min_length=1, max_length=2000)]
    actor: Literal["a", "b"] = "a"
    calls: tuple[ReferenceCall, ...] = ()
    statuses: tuple[str, ...] = ("answered",)
    required: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    no_facts: bool = False
    trace_errors: tuple[str, ...] = ()
    fault: Literal[
        "none",
        "catalog_failure",
        "source_injection",
        "provider_timeout",
        "sql_tool",
        "invalid_args",
    ] = "none"


class EvaluationCase(EvaluationModel):
    case_id: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_-]{2,20}$")]
    category: Literal["catalog", "pricing", "policies", "orders", "multi_step", "robustness"]
    answer_key: str
    authorization: dict[Literal["a", "b"], Literal[1, 2] | None] = Field(default_factory=dict)
    steps: Annotated[tuple[EvaluationStep, ...], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def isolated_demo_actors(self) -> "EvaluationCase":
        if any(type(value) is bool for value in self.authorization.values()):
            raise ValueError("invalid_demo_identity")
        return self


def load_cases(path: Path) -> list[EvaluationCase]:
    cases = TypeAdapter(list[EvaluationCase]).validate_json(path.read_bytes())
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("duplicate_case_id")
    counts = {name: sum(case.category == name for case in cases) for name in CATEGORY_COUNTS}
    if counts != CATEGORY_COUNTS:
        raise ValueError("invalid_suite_distribution")
    return cases

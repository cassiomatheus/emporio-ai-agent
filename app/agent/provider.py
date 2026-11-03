"""Adaptador oficial Responses API, substituível sem alterar tools ou serviços."""

import json
import time
from collections.abc import Sequence
from copy import deepcopy
from typing import Protocol

from openai import APITimeoutError, AsyncOpenAI

from app.agent.models import AnswerPlan, FunctionCall, ModelTurn, TokenUsage
from app.config import Settings


class ProviderError(RuntimeError):
    """Erro técnico sem resposta HTTP, endpoint ou credencial na mensagem."""


class ProviderNotConfigured(ProviderError):
    pass


class ProviderTimeout(ProviderError):
    pass


class LLMProvider(Protocol):
    async def complete(
        self,
        messages: Sequence[dict],
        tools: Sequence[dict],
        *,
        timeout: float,
        max_output_tokens: int,
    ) -> ModelTurn: ...


def responses_tools(contracts: Sequence[dict]) -> list[dict]:
    # specs é um mapa dinâmico, incompatível com strict de objetos fechados.
    # A validação estrita autoritativa continua no backend da Fase 05.
    return [
        {
            "type": "function",
            "name": item["name"],
            "description": item["description"],
            "parameters": item["input_schema"],
            "strict": False,
        }
        for item in contracts
    ]


def _evidence_map(messages: Sequence[dict]) -> dict[str, str]:
    called = {
        item["call_id"]: item["name"] for item in messages if item.get("type") == "function_call"
    }
    evidence = {}
    for item in messages:
        if item.get("type") != "function_call_output" or item.get("call_id") not in called:
            continue
        payload = json.loads(item["output"])
        if isinstance(payload, dict) and payload.get("status") == "ok":
            evidence[item["call_id"]] = called[item["call_id"]]
    return evidence


def _evidence_ids(messages: Sequence[dict]) -> set[str]:
    return set(_evidence_map(messages))


def _answer_schema(messages: Sequence[dict]) -> tuple[dict, set[str]]:
    """Restringe referências às tools bem-sucedidas desta execução, nunca ao usuário."""
    evidence = _evidence_ids(messages)
    schema = AnswerPlan.model_json_schema()
    schema["required"] = list(schema["properties"])
    references = schema["properties"]["evidence_call_ids"]
    references["uniqueItems"] = True  # Mesmo contrato do validador AnswerPlan.
    if evidence:
        references["items"]["enum"] = sorted(evidence)
    else:
        references["maxItems"] = 0
    # Os model_validator de AnswerPlan não aparecem no schema Pydantic.
    # Representá-los evita planos sintaticamente válidos mas contraditórios.
    variants = []
    if evidence:
        answer = deepcopy(schema)
        answer["properties"]["intent"]["enum"] = ["answer"]
        answer["properties"]["evidence_call_ids"]["minItems"] = 1
        answer["properties"]["clarification"] = {"type": "null"}
        variants.append(answer)
    clarify = deepcopy(schema)
    clarify["properties"]["intent"]["enum"] = ["clarify"]
    clarify["properties"]["evidence_call_ids"]["maxItems"] = 0
    clarify["properties"]["clarification"] = next(
        item for item in schema["properties"]["clarification"]["anyOf"] if item["type"] == "string"
    )
    variants.append(clarify)
    other = deepcopy(schema)
    other["properties"]["intent"]["enum"] = ["greeting", "out_of_scope", "handoff"]
    other["properties"]["evidence_call_ids"]["maxItems"] = 0
    other["properties"]["clarification"] = {"type": "null"}
    variants.append(other)
    return {"oneOf": variants}, evidence


def _valid_answer(text: str, evidence: set[str]) -> bool:
    try:
        plan = AnswerPlan.model_validate_json(text)
        return set(plan.evidence_call_ids) <= evidence
    except ValueError:
        return False


class OpenAIResponsesProvider:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        *,
        structured_finalization: bool = False,
        plan_hints: bool = False,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.structured_finalization = structured_finalization
        self.plan_hints = plan_hints
        self.request_options = {}
        if temperature is not None:
            self.request_options["temperature"] = temperature
        if reasoning_effort is not None:
            self.request_options["reasoning"] = {"effort": reasoning_effort}

    async def complete(
        self,
        messages: Sequence[dict],
        tools: Sequence[dict],
        *,
        timeout: float,
        max_output_tokens: int,
    ) -> ModelTurn:
        started = time.monotonic()
        try:
            inputs = list(messages)
            if self.plan_hints:
                hint = (
                    "\nControle do backend: evidências disponíveis nesta execução "
                    "(ID: ferramenta): "
                    + json.dumps(_evidence_map(messages), sort_keys=True)
                    + ". O plano final é texto JSON, nunca uma ferramenta. "
                    "Use somente esses IDs em evidence_call_ids. Sem evidência, consulte "
                    "tools ou esclareça/encaminhe; não use intent answer. "
                    "Ao combinar fontes, selecione os IDs correspondentes, sem repetir IDs."
                )
                if inputs and inputs[0].get("role") == "system":
                    inputs[0] = {**inputs[0], "content": inputs[0]["content"] + hint}
                else:
                    inputs.insert(0, {"role": "system", "content": hint})
            response = await self.client.responses.create(
                model=self.model,
                input=inputs,
                tools=responses_tools(tools),
                tool_choice="auto",
                parallel_tool_calls=True,
                max_output_tokens=max_output_tokens,
                timeout=timeout,
                store=False,
                include=["reasoning.encrypted_content"],
                **self.request_options,
            )
            if response.status != "completed":
                raise ProviderError("provider_incomplete_response")
            usages = [response.usage]
            if self.structured_finalization and not any(
                item.type == "function_call" for item in response.output
            ):
                schema, evidence = _answer_schema(messages)
                if not _valid_answer(response.output_text or "", evidence):
                    # Grammar global impediria seleção/sequência de tools no Ollama.
                    # Só finaliza depois que o modelo decidiu não chamar outra tool.
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        raise ProviderTimeout("provider_timeout")
                    response = await self.client.responses.create(
                        model=self.model,
                        input=inputs,
                        tools=[],
                        store=False,
                        max_output_tokens=max_output_tokens,
                        timeout=remaining,
                        text={
                            "format": {
                                "type": "json_schema",
                                "name": "emporio_answer_plan",
                                "strict": True,
                                "schema": schema,
                            }
                        },
                        **self.request_options,
                    )
                    if response.status != "completed" or any(
                        item.type == "function_call" for item in response.output
                    ):
                        raise ProviderError("provider_invalid_finalization")
                    usages.append(response.usage)
            calls = tuple(
                FunctionCall(call_id=item.call_id, name=item.name, arguments=item.arguments)
                for item in response.output
                if item.type == "function_call"
            )
            usage = None
            if all(item is not None for item in usages):
                usage = TokenUsage(
                    input_tokens=sum(item.input_tokens for item in usages),
                    output_tokens=sum(item.output_tokens for item in usages),
                    total_tokens=sum(item.total_tokens for item in usages),
                )
            return ModelTurn(
                calls=calls,
                final_text=response.output_text or None,
                output_items=tuple(
                    item.model_dump(exclude_none=True, warnings="error") for item in response.output
                ),
                usage=usage,
            )
        except APITimeoutError as exc:
            raise ProviderTimeout("provider_timeout") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("provider_request_failed") from exc

    async def close(self) -> None:
        await self.client.close()


def configured_provider(settings: Settings) -> OpenAIResponsesProvider:
    if not settings.llm_configured:
        raise ProviderNotConfigured("provider_not_configured")
    base_url = settings.llm_base_url or "https://api.openai.com/v1"
    client = AsyncOpenAI(
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )
    return OpenAIResponsesProvider(
        client,
        settings.llm_model,
        structured_finalization=settings.llm_structured_finalization,
        plan_hints=settings.llm_provider == "openai_compatible",
        temperature=settings.llm_temperature,
        reasoning_effort=settings.llm_reasoning_effort,
    )

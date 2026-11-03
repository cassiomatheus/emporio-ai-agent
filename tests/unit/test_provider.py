"""SDK oficial com transporte HTTP local simulado; nunca acessa um provedor real."""

import asyncio
import json

import httpx2
import pytest
from openai import AsyncOpenAI
from pydantic import SecretStr, ValidationError

from app.agent.provider import (
    OpenAIResponsesProvider,
    ProviderError,
    ProviderNotConfigured,
    configured_provider,
    responses_tools,
)
from app.config import Settings
from app.tools.registry import tool_contracts


def response_body(output: list, status: str = "completed") -> dict:
    return {
        "id": "resp_mock",
        "object": "response",
        "created_at": 0,
        "model": "mock-model",
        "status": status,
        "output": output,
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


def test_official_sdk_function_call_and_manual_context_without_network() -> None:
    requests = []

    def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["store"] is False
        assert body["tools"][0]["type"] == "function"
        assert all(item["strict"] is False for item in body["tools"])
        assert body["include"] == ["reasoning.encrypted_content"]
        assert body["model"] == "mock-model"
        if len(requests) == 1:
            output = [
                {
                    "type": "reasoning",
                    "id": "rs_mock",
                    "summary": [],
                    "encrypted_content": "encrypted-test",
                },
                {
                    "type": "function_call",
                    "id": "fc_mock",
                    "call_id": "call_sdk",
                    "name": "search_products",
                    "arguments": json.dumps(
                        {"category": "Violões", "max_price": "1000", "specs": {"strings": "nylon"}}
                    ),
                },
            ]
        else:
            output = [
                {
                    "type": "message",
                    "id": "msg_mock",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "annotations": [],
                            "text": json.dumps(
                                {
                                    "intent": "greeting",
                                    "evidence_call_ids": [],
                                    "clarification": None,
                                }
                            ),
                        }
                    ],
                }
            ]
        return httpx2.Response(200, json=response_body(output))

    async def scenario():
        http = httpx2.AsyncClient(transport=httpx2.MockTransport(transport))
        client = AsyncOpenAI(
            api_key="unit-test-token",
            base_url="https://example.invalid/v1",
            http_client=http,
            max_retries=0,
        )
        provider = OpenAIResponsesProvider(client, "mock-model")
        try:
            first = await provider.complete(
                [{"role": "user", "content": "teste"}],
                tool_contracts(),
                timeout=2,
                max_output_tokens=256,
            )
            assert first.calls[0].call_id == "call_sdk"
            assert first.usage.total_tokens == 15
            assert first.output_items[0]["type"] == "reasoning"
            messages = [
                {"role": "user", "content": "teste"},
                *first.output_items,
                {
                    "type": "function_call_output",
                    "call_id": "call_sdk",
                    "output": '{"status":"ok"}',
                },
            ]
            second = await provider.complete(
                messages, tool_contracts(), timeout=2, max_output_tokens=256
            )
            assert second.calls == ()
            assert json.loads(second.final_text)["intent"] == "greeting"
            assert requests[1]["input"][1]["encrypted_content"] == "encrypted-test"
            assert requests[1]["input"][-1]["call_id"] == "call_sdk"
        finally:
            await provider.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["unauthorized", "incomplete"])
def test_sdk_errors_and_incomplete_output_are_sanitized(failure: str) -> None:
    def transport(request):
        if failure == "unauthorized":
            return httpx2.Response(
                401,
                json={
                    "error": {
                        "message": "PRIVATE-SECRET",
                        "type": "invalid_request_error",
                        "code": "invalid_api_key",
                    }
                },
            )
        return httpx2.Response(200, json=response_body([], status="incomplete"))

    async def scenario():
        client = AsyncOpenAI(
            api_key="unit-test",
            base_url="https://example.invalid/v1",
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(transport)),
        )
        provider = OpenAIResponsesProvider(client, "mock")
        try:
            with pytest.raises(ProviderError) as exc:
                await provider.complete([], tool_contracts(), timeout=1, max_output_tokens=256)
            assert "PRIVATE" not in str(exc.value)
        finally:
            await provider.close()

    asyncio.run(scenario())


def test_provider_configuration_does_not_select_a_paid_model(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "EMPORIO_LLM_PROVIDER",
        "EMPORIO_LLM_MODEL",
        "EMPORIO_LLM_API_KEY",
        "EMPORIO_LLM_BASE_URL",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_model is None and settings.llm_provider is None
    assert not settings.llm_configured
    with pytest.raises(ProviderNotConfigured):
        configured_provider(settings)
    configured = Settings(
        _env_file=None,
        llm_provider="openai",
        llm_model="explicit-model",
        llm_api_key=SecretStr("unit-test-secret"),
    )
    assert configured.llm_configured
    assert "unit-test-secret" not in repr(configured)
    assert "unit-test-secret" not in configured.model_dump_json()
    local = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        llm_model="local-model",
        llm_api_key="unit-test",
    )
    assert not local.llm_configured  # Endpoint compatível precisa ser explícito.


def test_configured_client_disables_automatic_retries(monkeypatch) -> None:
    class DummyClient:
        def __init__(self, **kwargs):
            self.options = kwargs

    monkeypatch.setattr("app.agent.provider.AsyncOpenAI", DummyClient)
    settings = Settings(
        _env_file=None, llm_provider="openai", llm_model="explicit-model", llm_api_key="unit-test"
    )
    provider = configured_provider(settings)
    assert provider.client.options["max_retries"] == 0
    assert provider.client.options["timeout"] == 20


@pytest.mark.parametrize(
    "options",
    [
        {"llm_base_url": "file:///private"},
        {"llm_base_url": "https://user:secret@example.invalid"},
        {"llm_base_url": "https://example.invalid?api_key=secret"},
        {"agent_max_rounds": 0},
        {"agent_timeout_seconds": 0},
        {"agent_max_tool_calls": 33},
    ],
)
def test_invalid_configuration_is_rejected(options: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **options)


def test_adapter_preserves_backend_tool_schemas() -> None:
    contracts = tool_contracts()
    adapted = responses_tools(contracts)
    assert len(adapted) == 6
    assert adapted[3]["parameters"]["properties"].keys() == {"order_id"}
    assert all(item["strict"] is False for item in adapted)

"""Montagem compartilhada: disponibilidade, configuração e lifecycle sem API real."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent.provider import OpenAIResponsesProvider
from app.config import Settings
from app.database.ingestion import ingest_dataset
from app.runtime import RuntimeUnavailable, build_runtime


@pytest.fixture
def settings(tmp_path):
    path = tmp_path / "demo.sqlite3"
    ingest_dataset(Path("data/samples"), path)
    return Settings(
        _env_file=None,
        chat_mode="real",
        chat_demo_database=path,
        chat_catalog_database=path,
        llm_provider="openai",
        llm_model="mock-model",
        llm_api_key="unit-test-only",
    )


def test_real_mode_builds_adapter_without_calling_it_and_closes_it(settings, monkeypatch):
    client = SimpleNamespace(close=AsyncMock())
    provider = OpenAIResponsesProvider(client, "mock-model")
    provider.complete = AsyncMock()
    monkeypatch.setattr("app.runtime.configured_provider", lambda settings: provider)

    async def scenario():
        runtime = await build_runtime(settings)
        assert runtime.execution_mode == "real"
        provider.complete.assert_not_called()
        await runtime.close()
        client.close.assert_awaited_once()

    asyncio.run(scenario())


def test_offline_mode_ignores_paid_configuration_private_catalog_and_pdf(settings, monkeypatch):
    def forbidden(settings):
        pytest.fail("Modo offline não pode construir adaptador real")

    monkeypatch.setattr("app.runtime.configured_provider", forbidden)
    offline = settings.model_copy(
        update={
            "chat_mode": "offline_demo",
            "chat_catalog_database": Path("/missing/private.sqlite3"),
            "chat_policy_pdf": Path("/missing/internal.pdf"),
        }
    )

    async def scenario():
        runtime = await build_runtime(offline)
        assert runtime.execution_mode == "offline_scripted"
        assert runtime.backend.limits.max_turns == settings.session_max_turns
        await runtime.close()

    asyncio.run(scenario())


def test_unconfigured_runtime_fails_before_constructing_provider(settings, monkeypatch):
    def forbidden(settings):
        pytest.fail("Não deve construir cliente com configuração incompleta")

    monkeypatch.setattr("app.runtime.configured_provider", forbidden)
    with pytest.raises(RuntimeUnavailable, match="^chat_unavailable$"):
        asyncio.run(build_runtime(settings.model_copy(update={"llm_model": None})))


def test_factory_failure_closes_allocated_provider_without_exposing_details(settings, monkeypatch):
    provider = OpenAIResponsesProvider(SimpleNamespace(close=AsyncMock()), "mock-model")
    monkeypatch.setattr("app.runtime.configured_provider", lambda settings: provider)

    def fail(*args, **kwargs):
        raise ValueError("PRIVATE path/key")

    monkeypatch.setattr("app.runtime.ConversationService.for_demo", fail)
    with pytest.raises(RuntimeUnavailable, match="^chat_unavailable$"):
        asyncio.run(build_runtime(settings))
    provider.client.close.assert_awaited_once()

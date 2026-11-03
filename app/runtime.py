"""Montagem compartilhada por CLI e HTTP; não ingere nem modifica dados locais."""

from dataclasses import dataclass
from typing import Literal

from app.agent.demo import DemoDatabase
from app.agent.demo_provider import OfflineDemoProvider
from app.agent.models import AgentLimits
from app.agent.provider import OpenAIResponsesProvider, configured_provider
from app.agent.sessions import ConversationService, SessionLimits
from app.config import Settings
from app.database.connection import connect_database
from app.services.policy_service import PolicyService

ExecutionMode = Literal["real", "offline_scripted", "not_configured"]


class RuntimeUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("chat_unavailable")


@dataclass(repr=False)
class ChatRuntime:
    backend: ConversationService
    provider: OfflineDemoProvider | OpenAIResponsesProvider
    execution_mode: ExecutionMode

    async def close(self) -> None:
        if isinstance(self.provider, OpenAIResponsesProvider):
            await self.provider.close()


async def build_runtime(settings: Settings) -> ChatRuntime:
    provider = None
    try:
        demo_mode = settings.chat_mode == "offline_demo"
        if not demo_mode and not settings.llm_configured:
            raise RuntimeUnavailable()
        catalog = settings.chat_demo_database if demo_mode else settings.chat_catalog_database
        # Confere o catálogo antes de construir o cliente; nenhuma chamada à API.
        with connect_database(catalog, read_only=True) as connection:
            connection.execute("SELECT product_id FROM products LIMIT 1").fetchall()
        policies = (
            PolicyService.from_pdf(settings.chat_policy_pdf)
            if settings.chat_policy_pdf is not None and not demo_mode
            else None
        )
        limits = AgentLimits(
            max_rounds=settings.agent_max_rounds,
            max_tool_calls=settings.agent_max_tool_calls,
            timeout_seconds=settings.agent_timeout_seconds,
            tool_timeout_seconds=settings.agent_tool_timeout_seconds,
            request_timeout_seconds=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
        )
        DemoDatabase(settings.chat_demo_database)
        provider = OfflineDemoProvider() if demo_mode else configured_provider(settings)
        backend = ConversationService.for_demo(
            provider,
            catalog_database=catalog,
            demo_database=settings.chat_demo_database,
            policies=policies,
            agent_limits=limits,
            session_limits=SessionLimits.from_settings(settings),
        )
        return ChatRuntime(backend, provider, "offline_scripted" if demo_mode else "real")
    except Exception:
        if isinstance(provider, OpenAIResponsesProvider):
            await provider.close()
        raise RuntimeUnavailable() from None

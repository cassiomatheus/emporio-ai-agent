"""Backend em memória. Handles demonstram isolamento, não autenticam pessoas."""

import asyncio
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from pydantic import Field

from app.agent.audit import audit
from app.agent.demo import DemoDatabase
from app.agent.memory import ConversationMemory, ProductReference
from app.agent.models import AgentLimits, AgentModel, AgentRequest, AgentResult
from app.agent.orchestrator import SAFE_MESSAGE, AgentOrchestrator
from app.agent.provider import LLMProvider
from app.agent.security import redact, suspicious
from app.config import Settings
from app.database.repository import (
    SQLiteOrderRepository,
    SQLitePricingRepository,
    SQLiteProductRepository,
)
from app.services.models import OrderAccessContext
from app.services.order_service import OrderService
from app.services.policy_service import PolicyService
from app.services.pricing_service import PricingService
from app.services.product_service import ProductService
from app.tools.registry import ToolRegistry


class SessionLimits(AgentModel):
    max_turns: Annotated[int, Field(ge=1, le=20)] = 6
    max_characters: Annotated[int, Field(ge=1000, le=60000)] = 12000
    ttl_seconds: Annotated[float, Field(gt=0, le=86400)] = 1800
    max_sessions: Annotated[int, Field(ge=1, le=1000)] = 100
    max_clients: Annotated[int, Field(ge=1, le=1000)] = 100
    lock_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 30

    @classmethod
    def from_settings(cls, settings: Settings) -> "SessionLimits":
        return cls(**{name: getattr(settings, f"session_{name}") for name in cls.model_fields})


@dataclass(frozen=True, eq=False, repr=False)
class BackendClient:
    """Capacidade opaca, emitida e retida pelo backend; não é um login."""


@dataclass(repr=False)
class _Session:
    owner: BackendClient
    access: OrderAccessContext
    memory: ConversationMemory
    expires: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionAccessDenied(PermissionError):
    def __init__(self) -> None:
        super().__init__("session_access_denied")


class SessionCapacityError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("session_capacity_reached")


class ConversationService:
    """Uma instância por event loop/processo; nenhum estado global entre instâncias.

    register_demo_client é uma operação administrativa Python. Jamais expor seu
    parâmetro de cliente como campo livre de HTTP, mensagem ou tool de LLM.
    """

    def __init__(
        self,
        orchestrator: AgentOrchestrator,
        *,
        limits: SessionLimits | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._agent = orchestrator
        self.limits = limits or SessionLimits()
        self._clock = clock
        self._clients: dict[BackendClient, OrderAccessContext] = {}
        self._sessions: dict[str, _Session] = {}
        self._demo: DemoDatabase | None = None

    @classmethod
    def for_demo(
        cls,
        provider: LLMProvider,
        *,
        catalog_database: Path,
        demo_database: Path,
        policies: PolicyService | None = None,
        agent_limits: AgentLimits | None = None,
        session_limits: SessionLimits | None = None,
    ) -> "ConversationService":
        demo = DemoDatabase(demo_database)
        tools = ToolRegistry(
            ProductService(SQLiteProductRepository(catalog_database)),
            PricingService(SQLitePricingRepository(catalog_database)),
            OrderService(SQLiteOrderRepository(demo.path)),
            policies,
        )
        service = cls(AgentOrchestrator(provider, tools, agent_limits), limits=session_limits)
        service._demo = demo
        return service

    def _purge(self) -> None:
        now = self._clock()
        for session_id, state in tuple(self._sessions.items()):
            if state.expires <= now:
                state.memory.clear()
                del self._sessions[session_id]

    def register_demo_client(self, *, customer_id: int | None = None) -> BackendClient:
        if customer_id is not None and (
            type(customer_id) is not int
            or self._demo is None
            or customer_id not in self._demo.customer_ids
            or not self._demo.valid()
        ):
            raise SessionAccessDenied()
        if len(self._clients) >= self.limits.max_clients:
            raise SessionCapacityError()
        handle = BackendClient()
        self._clients[handle] = OrderAccessContext(authorized_customer_id=customer_id)
        return handle

    def _known(self, client: BackendClient) -> bool:
        return type(client) is BackendClient and client in self._clients

    def create_session(self, client: BackendClient) -> str:
        if not self._known(client):
            raise SessionAccessDenied()
        self._purge()
        if len(self._sessions) >= self.limits.max_sessions:
            raise SessionCapacityError()
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = _Session(
            owner=client,
            access=self._clients[client],
            memory=ConversationMemory(self.limits.max_turns, self.limits.max_characters),
            expires=self._clock() + self.limits.ttl_seconds,
        )
        audit("session_created", session_id, "ok")
        return session_id

    def _resolve(self, client: BackendClient, session_id: str) -> _Session:
        self._purge()
        state = self._sessions.get(session_id) if type(session_id) is str else None
        if not self._known(client) or state is None or state.owner is not client:
            # Mesmo erro para ID desconhecido, expirado e sessão de outro usuário.
            audit("access_denied", "denied", "error")
            raise SessionAccessDenied()
        return state

    def close_session(self, client: BackendClient, session_id: str) -> None:
        state = self._resolve(client, session_id)
        state.memory.clear()
        del self._sessions[session_id]
        audit("session_closed", session_id, "ok")

    def revoke_client(self, client: BackendClient) -> None:
        if not self._known(client):
            raise SessionAccessDenied()
        for session_id, state in tuple(self._sessions.items()):
            if state.owner is client:
                state.memory.clear()
                del self._sessions[session_id]
        del self._clients[client]
        audit("client_revoked", "revoked", "ok")

    async def chat(
        self, client: BackendClient, session_id: str, request: AgentRequest
    ) -> AgentResult:
        state = self._resolve(client, session_id)
        try:
            await asyncio.wait_for(state.lock.acquire(), self.limits.lock_timeout_seconds)
        except TimeoutError:
            audit("turn_failed", session_id, "timeout")
            return AgentResult(status="timeout", text=SAFE_MESSAGE, rounds=0, tools=())
        try:
            if self._resolve(client, session_id) is not state:
                raise SessionAccessDenied()
            if self._demo is not None and not self._demo.valid():
                raise SessionAccessDenied()
            blocked = suspicious(request.message)
            if blocked:
                audit("input_blocked", session_id, "error")
            safe_request = AgentRequest(message=redact(request.message))
            try:
                answer = await self._agent.run(
                    request if blocked else safe_request,
                    order_access=state.access,
                    conversation=state.memory.context(),
                )
            except Exception:
                answer = AgentResult(status="protocol_error", text=SAFE_MESSAGE, rounds=0, tools=())
            # Revogação, expiração ou fechamento durante o await também negam entrega.
            if self._resolve(client, session_id) is not state or (
                self._demo is not None and not self._demo.valid()
            ):
                raise SessionAccessDenied()
            state.memory.append(
                "[solicitação bloqueada]" if blocked else safe_request.message,
                redact(answer.text),
                ProductReference(product_ids=answer.reference_ids)
                if answer.reference_ids is not None
                else None,
                search_page=answer.search_page,
            )
            state.expires = self._clock() + self.limits.ttl_seconds
            for trace in answer.tools:
                audit(
                    "tool_result", session_id, trace.status, tool=trace.name, error=trace.error_code
                )
            audit("turn_completed", session_id, answer.status)
            return answer
        finally:
            state.lock.release()

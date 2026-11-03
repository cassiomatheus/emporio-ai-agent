"""API de visitante: token protege a conversa, não autentica identidade de cliente."""

import hashlib
import hmac
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from app.agent.models import AgentRequest, AgentResult
from app.agent.sessions import BackendClient, SessionAccessDenied, SessionCapacityError
from app.api_schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    HttpError,
    SessionCreate,
    SessionCreated,
    ToolSummary,
)
from app.config import Settings
from app.interface_errors import MESSAGES, result_error
from app.runtime import ChatRuntime, RuntimeUnavailable, build_runtime
from app.tools.registry import INPUT_MODELS
from app.ui import mount_chat_ui


def error_response(status: int, code: str) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(
        status_code=status,
        headers=headers,
        content=ErrorResponse(error=HttpError(code=code, message=MESSAGES[code])).model_dump(),
    )


class HttpBoundary:
    """Limite inclusive para corpo em chunks; erros e headers sem dados de entrada."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def safe_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        try:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > 16384:
                    await error_response(413, "request_too_large")(scope, receive, safe_send)
                    return
                if not message.get("more_body", False):
                    break
            content_type = dict(scope.get("headers", [])).get(b"content-type", b"")
            if (
                scope["method"] == "POST"
                and content_type.split(b";", 1)[0].lower() != b"application/json"
            ):
                await error_response(415, "unsupported_media_type")(scope, receive, safe_send)
                return
            first = True

            async def replay():
                nonlocal first
                if first:
                    first = False
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, safe_send)
        except Exception:
            if not started:
                await error_response(500, "internal_error")(scope, receive, safe_send)


@dataclass(repr=False)
class _Guest:
    client: BackendClient
    token_hash: bytes = field(repr=False)
    expires: float


class GuestSessions:
    def __init__(self, runtime: ChatRuntime) -> None:
        self.runtime = runtime
        self._guests: dict[str, _Guest] = {}

    def _purge(self) -> None:
        for session_id, guest in tuple(self._guests.items()):
            if guest.expires <= time.monotonic():
                self.runtime.backend.revoke_client(guest.client)
                del self._guests[session_id]

    def create(self) -> SessionCreated:
        self._purge()
        backend = self.runtime.backend
        client = backend.register_demo_client()  # HTTP nunca recebe concessão de pedido.
        try:
            session_id = backend.create_session(client)
        except Exception:
            backend.revoke_client(client)
            raise
        token = secrets.token_urlsafe(32)
        self._guests[session_id] = _Guest(
            client,
            hashlib.sha256(token.encode()).digest(),
            time.monotonic() + backend.limits.ttl_seconds,
        )
        return SessionCreated(
            session_id=session_id,
            session_token=token,
            expires_in_seconds=backend.limits.ttl_seconds,
            execution_mode=self.runtime.execution_mode,
        )

    async def chat(self, request: ChatRequest, token: str) -> AgentResult:
        self._purge()
        guest = self._guests.get(request.session_id)
        if (
            guest is None
            or len(token) != 43
            or not hmac.compare_digest(
                guest.token_hash,
                hashlib.sha256(token.encode()).digest(),
            )
        ):
            raise SessionAccessDenied()
        result = await self.runtime.backend.chat(
            guest.client,
            request.session_id,
            AgentRequest(message=request.message),
        )
        guest.expires = time.monotonic() + self.runtime.backend.limits.ttl_seconds
        return result

    def close(self) -> None:
        for guest in self._guests.values():
            self.runtime.backend.revoke_client(guest.client)
        self._guests.clear()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = None
        try:
            runtime = await build_runtime(settings)
        except RuntimeUnavailable:
            pass
        app.state.guests = GuestSessions(runtime) if runtime else None
        try:
            yield
        finally:
            if app.state.guests is not None:
                app.state.guests.close()
            if runtime is not None:
                await runtime.close()

    app = FastAPI(
        title="Empório da Música", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.add_middleware(HttpBoundary)
    mount_chat_ui(app)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return error_response(422, "invalid_request")

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "invalid_request")
        return error_response(exc.status_code, code)

    bearer = HTTPBearer(auto_error=False)

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request):
        guests = getattr(request.app.state, "guests", None)
        return HealthResponse(
            chat_ready=guests is not None,
            execution_mode=guests.runtime.execution_mode if guests else "not_configured",
        )

    @app.post(
        "/sessions",
        status_code=201,
        response_model=SessionCreated,
        responses={
            422: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def create_session(payload: SessionCreate, request: Request):
        guests = getattr(request.app.state, "guests", None)
        if guests is None:
            return error_response(503, "service_unavailable")
        try:
            return guests.create()
        except SessionCapacityError:
            return error_response(429, "capacity_reached")

    @app.post(
        "/chat",
        response_model=ChatResponse,
        responses={status: {"model": ErrorResponse} for status in (401, 403, 422, 502, 503, 504)},
    )
    async def chat(
        payload: ChatRequest,
        request: Request,
        credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if credential is None:
            return error_response(401, "unauthorized")
        guests = getattr(request.app.state, "guests", None)
        if guests is None:
            return error_response(503, "service_unavailable")
        try:
            result = await guests.chat(payload, credential.credentials)
        except SessionAccessDenied:
            return error_response(403, "session_access_denied")
        error = result_error(result)
        if error:
            return error_response(*error)
        return ChatResponse(
            status=result.status,
            text=result.text,
            rounds=result.rounds,
            execution_mode=guests.runtime.execution_mode,
            tools=tuple(
                ToolSummary(
                    name=trace.name if trace.name in INPUT_MODELS else "unknown_tool",
                    status=trace.status,
                    error_code=trace.error_code,
                )
                for trace in result.tools
            ),
        )

    return app

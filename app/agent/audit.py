"""Auditoria por lista permitida: nunca recebe texto, argumentos ou exceções."""

import hashlib
import hmac
import logging
import secrets
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.tools.schemas import ErrorCode

LOGGER = logging.getLogger("emporio.audit")
_SALT = secrets.token_bytes(32)


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    event: Literal[
        "session_created",
        "session_closed",
        "client_revoked",
        "access_denied",
        "input_blocked",
        "turn_completed",
        "turn_failed",
        "tool_result",
    ]
    session_tag: str
    status: Literal[
        "answered",
        "abstained",
        "timeout",
        "round_limit",
        "call_limit",
        "provider_error",
        "protocol_error",
        "ok",
        "error",
    ]
    tool: (
        Literal[
            "search_products",
            "get_product_details",
            "get_product_offers",
            "get_order_status",
            "search_store_policies",
            "get_store_info",
            "unknown_tool",
        ]
        | None
    ) = None
    error: ErrorCode | Literal["timeout"] | None = None


def audit(event: str, session_id: str, status: str, *, tool=None, error=None) -> None:
    # Falha de handler/log nunca imprime fallback contendo dados nem interrompe chat.
    try:
        tag = hmac.new(_SALT, session_id.encode(), hashlib.sha256).hexdigest()[:20]
        item = AuditEvent(event=event, session_tag=tag, status=status, tool=tool, error=error)
        LOGGER.info("emporio_event", extra={"audit": item.model_dump(exclude_none=True)})
    except Exception:
        pass

"""Roteiro offline pequeno e explícito. Não é um LLM nem seleção autônoma."""

import json
import re
from collections.abc import Sequence

from app.agent.models import FunctionCall, ModelTurn
from app.agent.security import normalized


class OfflineDemoProvider:
    async def complete(
        self,
        messages: Sequence[dict],
        tools: Sequence[dict],
        *,
        timeout: float,
        max_output_tokens: int,
    ) -> ModelTurn:
        last_user = max(i for i, item in enumerate(messages) if item.get("role") == "user")
        outputs = [
            item for item in messages[last_user + 1 :] if item.get("type") == "function_call_output"
        ]
        if outputs:
            ids = [
                item["call_id"] for item in outputs if json.loads(item["output"])["status"] == "ok"
            ]
            return self._final("answer" if ids else "handoff", ids)
        text = normalized(messages[last_user]["content"])
        explicit = re.search(r"\b(?:produto|modelo)\s+(\d{1,9})\b", text)
        hint = next(
            (
                re.search(r"product_id=(\d+)", item.get("content", ""))
                for item in reversed(messages)
                if item.get("role") == "system"
            ),
            None,
        )
        product_id = int(explicit[1]) if explicit else int(hint[1]) if hint else None
        order = re.search(r"\bpedido\s+(\d{1,9})\b", text)
        if order:
            return self._call("get_order_status", {"order_id": int(order[1])})
        if product_id:
            count = re.search(r"\b(\d{1,2})\s*x\b", text)
            if count or "pix" in text or "oferta" in text:
                args = {"product_id": product_id, "payment_method": "credit" if count else "pix"}
                if count:
                    args["installments"] = int(count[1])
                return self._call("get_product_offers", args)
            return self._call("get_product_details", {"product_id": product_id})
        if "busque" in text or "nylon" in text:
            args = {"available_only": True}
            if "nylon" in text:
                args["specs"] = {"strings": "nylon"}
            if "violoes" in text:
                args["category"] = "Violões"
            return self._call("search_products", args)
        if text.strip(" !?.") in ("oi", "ola", "bom dia"):
            return self._final("greeting")
        return self._final("clarify", clarification="rephrase")

    @staticmethod
    def _call(name: str, args: dict) -> ModelTurn:
        return ModelTurn(
            calls=(
                FunctionCall(
                    call_id="offline_call",
                    name=name,
                    arguments=json.dumps(args),
                ),
            )
        )

    @staticmethod
    def _final(intent: str, ids: list[str] | None = None, *, clarification=None) -> ModelTurn:
        return ModelTurn(
            final_text=json.dumps(
                {
                    "intent": intent,
                    "evidence_call_ids": ids or [],
                    "clarification": clarification,
                }
            )
        )

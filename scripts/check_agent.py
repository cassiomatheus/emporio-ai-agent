"""Diagnóstico da pergunta fixa da Fase 06; não é CLI de chat ou teste cego de LLM."""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.agent.models import AgentLimits, AgentRequest, FunctionCall, ModelTurn
from app.agent.orchestrator import AgentOrchestrator
from app.agent.provider import configured_provider
from app.config import Settings
from app.database.repository import (
    SQLiteOrderRepository,
    SQLitePricingRepository,
    SQLiteProductRepository,
)
from app.services.order_service import OrderService
from app.services.pricing_service import PricingService
from app.services.product_service import ProductService
from app.tools.registry import ToolRegistry

FIRST_QUESTION = "Quais violões de nylon disponíveis custam até R$ 1.000?"


class ScriptedCatalogProvider:
    """Mock que só roteiriza a pergunta fixa; não simula inteligência ou API real."""

    def __init__(self) -> None:
        self.index = 0

    async def complete(
        self,
        messages: Sequence[dict],
        tools: Sequence[dict],
        *,
        timeout: float,
        max_output_tokens: int,
    ) -> ModelTurn:
        self.index += 1
        if self.index == 1:
            return ModelTurn(
                calls=(
                    FunctionCall(
                        call_id="demo_catalog",
                        name="search_products",
                        arguments=json.dumps(
                            {
                                "category": "Violões",
                                "max_price": "1000.00",
                                "specs": {"strings": "nylon"},
                                "available_only": True,
                                "limit": 20,
                            }
                        ),
                    ),
                )
            )
        return ModelTurn(
            final_text=json.dumps(
                {"intent": "answer", "evidence_call_ids": ["demo_catalog"], "clarification": None}
            )
        )


async def check(settings: Settings, database: Path, real: bool) -> dict:
    if real and not settings.llm_configured:
        return {
            "execution": "not_run",
            "requested_mode": "real",
            "real_provider_called": False,
            "reason": "provider_not_configured",
        }
    provider = configured_provider(settings) if real else ScriptedCatalogProvider()
    tools = ToolRegistry(
        products=ProductService(SQLiteProductRepository(database)),
        pricing=PricingService(SQLitePricingRepository(database)),
        orders=OrderService(SQLiteOrderRepository(database)),
        policies=None,
    )
    limits = AgentLimits(
        max_rounds=settings.agent_max_rounds,
        max_tool_calls=settings.agent_max_tool_calls,
        timeout_seconds=settings.agent_timeout_seconds,
        tool_timeout_seconds=settings.agent_tool_timeout_seconds,
        request_timeout_seconds=settings.llm_timeout_seconds,
        max_output_tokens=settings.llm_max_output_tokens,
    )
    try:
        result = await AgentOrchestrator(provider, tools, limits).run(
            AgentRequest(message=FIRST_QUESTION)
        )
        return {
            "execution": "real" if real else "simulated",
            "real_provider_called": real,
            "provider": settings.llm_provider if real else "scripted_mock",
            "model": settings.llm_model if real else None,
            "question": FIRST_QUESTION,
            "data_source": "local_sqlite_snapshot",
            "result": result.model_dump(mode="json"),
        }
    finally:
        if real:
            await provider.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnóstico da pergunta fixa, offline por padrão."
    )
    parser.add_argument(
        "--real", action="store_true", help="Só chama API quando o provedor está configurado."
    )
    parser.add_argument("--database", type=Path, default=Path("data/emporio.sqlite3"))
    args = parser.parse_args()
    try:
        report = asyncio.run(check(Settings(), args.database, args.real))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return (
            0
            if report.get("execution") == "not_run"
            or report.get("result", {}).get("status") == "answered"
            else 1
        )
    except Exception:
        print('{"error":"agent_diagnostic_failed"}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

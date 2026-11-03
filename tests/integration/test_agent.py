"""Corte vertical: LLM mock → tools reais → serviços → SQLite, sem rede."""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from app.agent.models import AgentRequest, FunctionCall, ModelTurn
from app.agent.orchestrator import AgentOrchestrator
from app.config import Settings
from app.database.connection import connect_database
from app.database.ingestion import ingest_dataset
from app.database.repository import (
    SQLiteOrderRepository,
    SQLitePricingRepository,
    SQLiteProductRepository,
)
from app.services.models import OrderAccessContext
from app.services.order_service import OrderService
from app.services.pricing_service import PricingService
from app.services.product_service import ProductService
from app.tools.registry import ToolRegistry

PROJECT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "phase06_diagnostic", PROJECT / "scripts" / "check_agent.py"
)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def registry(path: Path) -> ToolRegistry:
    return ToolRegistry(
        ProductService(SQLiteProductRepository(path)),
        PricingService(SQLitePricingRepository(path)),
        OrderService(SQLiteOrderRepository(path)),
        None,
    )


class SelectedCallsProvider:
    def __init__(self, calls: tuple[FunctionCall, ...]) -> None:
        self.calls = calls
        self.index = 0

    async def complete(self, *args, **kwargs):
        self.index += 1
        if self.index == 1:
            return ModelTurn(calls=self.calls)
        return ModelTurn(
            final_text=json.dumps(
                {
                    "intent": "answer",
                    "evidence_call_ids": [call.call_id for call in self.calls],
                    "clarification": None,
                }
            )
        )


def test_multiple_different_tools_combine_verified_facts(tmp_path: Path) -> None:
    database = tmp_path / "multiple.sqlite3"
    ingest_dataset(PROJECT / "data" / "samples", database)
    provider = SelectedCallsProvider(
        (
            FunctionCall(
                call_id="product", name="get_product_details", arguments='{"product_id":127}'
            ),
            FunctionCall(
                call_id="price",
                name="get_product_offers",
                arguments='{"product_id":127,"payment_method":"pix"}',
            ),
        )
    )
    result = asyncio.run(
        AgentOrchestrator(provider, registry(database)).run(
            AgentRequest(message="Detalhes e preço PIX")
        )
    )
    assert result.status == "answered"
    assert {trace.name for trace in result.tools} == {"get_product_details", "get_product_offers"}
    assert "estoque registrado: 11" in result.text
    assert "R$ 359,00" in result.text and "R$ 323,10" in result.text


@pytest.mark.parametrize("authorized", [False, True])
def test_order_tool_authorization_stays_in_backend(tmp_path: Path, authorized: bool) -> None:
    database = tmp_path / "orders.sqlite3"
    ingest_dataset(PROJECT / "data" / "samples", database)
    provider = SelectedCallsProvider(
        (FunctionCall(call_id="order", name="get_order_status", arguments='{"order_id":1}'),)
    )
    context = OrderAccessContext(authorized_customer_id=1) if authorized else None
    result = asyncio.run(
        AgentOrchestrator(provider, registry(database)).run(
            AgentRequest(message="Status do pedido 1"), order_access=context
        )
    )
    if authorized:
        assert result.status == "answered" and "R$ 999,90" in result.text
        assert "não informa código de rastreamento" in result.text
    else:
        assert result.status == "answered" and "R$" not in result.text
        assert "Acesso negado" in result.text
        assert result.tools[0].error_code == "forbidden"


def test_first_question_uses_available_nylon_and_budget_with_real_tools(tmp_path: Path) -> None:
    database = tmp_path / "synthetic.sqlite3"
    ingest_dataset(PROJECT / "data" / "samples", database)
    with connect_database(database) as connection:
        # Só no banco temporário sintético: nome de categoria para o corte da pergunta.
        connection.execute("UPDATE categories SET name='Violões' WHERE category_id=1")
    result = asyncio.run(
        AgentOrchestrator(diagnostic.ScriptedCatalogProvider(), registry(database)).run(
            AgentRequest(message=diagnostic.FIRST_QUESTION)
        )
    )
    assert result.status == "answered"
    assert result.tools[0].name == "search_products"
    assert "ID 102" in result.text
    assert "R$ 250,00" in result.text
    assert "ID 101" not in result.text and "ID 136" not in result.text
    assert result.usage is None


def test_catalog_failure_never_returns_a_price(tmp_path: Path) -> None:
    result = asyncio.run(
        AgentOrchestrator(
            diagnostic.ScriptedCatalogProvider(), registry(tmp_path / "missing.sqlite3")
        ).run(AgentRequest(message=diagnostic.FIRST_QUESTION))
    )
    assert result.status == "answered" and "confirmar" in result.text
    assert "R$" not in result.text
    assert result.tools[0].error_code == "service_unavailable"
    assert not (tmp_path / "missing.sqlite3").exists()


def test_real_check_is_skipped_without_explicit_configuration(monkeypatch, tmp_path: Path) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Não deve construir o cliente real.")

    monkeypatch.setattr(diagnostic, "configured_provider", forbidden)
    settings = Settings(_env_file=None, llm_provider=None, llm_model=None, llm_api_key=None)
    report = asyncio.run(diagnostic.check(settings, tmp_path / "unused.sqlite3", real=True))
    assert report == {
        "execution": "not_run",
        "requested_mode": "real",
        "real_provider_called": False,
        "reason": "provider_not_configured",
    }


@pytest.mark.local_data
def test_first_question_on_original_csvs_with_mock_llm(tmp_path: Path) -> None:
    raw = PROJECT / "data" / "raw"
    if not any(raw.glob("*.csv")):
        pytest.skip("CSVs privados ausentes; o corte sintético continua disponível.")
    database = tmp_path / "original.sqlite3"
    ingest_dataset(raw, database)
    result = asyncio.run(
        AgentOrchestrator(diagnostic.ScriptedCatalogProvider(), registry(database)).run(
            AgentRequest(message=diagnostic.FIRST_QUESTION)
        )
    )
    assert result.status == "answered" and result.rounds == 2
    expected_ids = [83, 85, 81, 84, 82]
    assert all(f"ID {product_id}" in result.text for product_id in expected_ids)
    assert "ID 113" not in result.text
    assert len(result.tools) == 1 and result.tools[0].status == "ok"
    assert result.usage is None  # LLM simulado, não tokens reais.

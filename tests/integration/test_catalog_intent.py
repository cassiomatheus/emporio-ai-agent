"""Contrato do agente → interpretação → tools/SQLite reais, sem inferência externa."""

import asyncio
import copy
import json
from pathlib import Path

import pytest

from app.agent.models import AgentRequest, FunctionCall, ModelTurn
from app.agent.sessions import ConversationService
from app.database.connection import connect_database
from app.database.ingestion import ingest_dataset


class Provider:
    def __init__(self, arguments):
        self.arguments = arguments
        self.requests = []

    async def complete(self, messages, tools, **kwargs):
        self.requests.append((copy.deepcopy(messages), copy.deepcopy(tools)))
        last = max(i for i, item in enumerate(messages) if item.get("role") == "user")
        outputs = [
            item for item in messages[last + 1 :] if item.get("type") == "function_call_output"
        ]
        if outputs:
            return ModelTurn(
                final_text=json.dumps(
                    {
                        "intent": "answer",
                        "evidence_call_ids": [item["call_id"] for item in outputs],
                        "clarification": None,
                    }
                )
            )
        return ModelTurn(
            calls=(
                FunctionCall(
                    call_id="semantic_search",
                    name="search_products",
                    arguments=json.dumps(self.arguments),
                ),
            )
        )


class Recorder:
    def __init__(self, wrapped):
        self.wrapped, self.calls = wrapped, []

    def call(self, name, arguments, **kwargs):
        self.calls.append((name, copy.deepcopy(arguments)))
        return self.wrapped.call(name, arguments, **kwargs)


@pytest.fixture
def setup(tmp_path):
    catalog, demo = tmp_path / "catalog.sqlite3", tmp_path / "demo.sqlite3"
    for database in (catalog, demo):
        ingest_dataset(Path("data/samples"), database)
    with connect_database(catalog) as con:
        con.execute("UPDATE products SET stock_quantity=0")
        con.execute("UPDATE categories SET name='Ukuleles' WHERE category_id=1")
        con.execute("INSERT INTO categories VALUES (5, 'Violões', 'Categoria de controle')")
        con.execute(
            "INSERT INTO products VALUES (599,50000,'Violão de controle',5,'Fixture',1,"
            "'active','{}','2026-01-01')"
        )
        con.executemany(
            "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    501 + i,
                    amount,
                    f"Marca {i} Soprano Natural",
                    1,
                    "Fixture",
                    3,
                    "active",
                    '{"color":"Natural","strings":"nylon"}',
                    "2026-01-01",
                )
                for i, amount in enumerate([17990, 19990, 24990])
            ],
        )
    provider = Provider(
        {
            "product": {"category": "ukulele", "subtype": "soprano"},
            "characteristics": {"cor": "natural"},
            "limit": 2,
        }
    )
    backend = ConversationService.for_demo(provider, catalog_database=catalog, demo_database=demo)
    recorder = Recorder(backend._agent.tools)
    backend._agent.tools = recorder
    owner = backend.register_demo_client()
    return backend, provider, recorder, owner


def test_semantic_request_executes_canonical_query_and_paginates_without_more_inference(setup):
    backend, provider, recorder, owner = setup
    session = backend.create_session(owner)

    async def scenario():
        answer = await backend.chat(
            owner,
            session,
            AgentRequest(
                message="Estou procurando ukuleles soprano de cor natural até R$ 250",
            ),
        )
        assert "ID 501" in answer.text and "ID 502" in answer.text
        interpretation = answer.catalog_interpretations[0]
        assert interpretation.source == "semantic"
        assert interpretation.request.product.category == "ukulele"
        assert interpretation.query.category == "Ukuleles"
        assert interpretation.query.specs == {"color": "natural"}
        assert recorder.calls[0][1]["max_price"] == "250"
        assert recorder.calls[0][1]["term"] == "soprano"
        assert "product" not in recorder.calls[0][1]
        assert "catalog_interpretations" not in answer.model_dump()
        schema = provider.requests[0][1][0]["input_schema"]
        assert "product" in schema["properties"] and "specs" not in schema["properties"]
        follow = await backend.chat(owner, session, AgentRequest(message="continuar"))
        assert "ID 503" in follow.text and "ID 501" not in follow.text
        assert len(provider.requests) == 2 and recorder.calls[-1][1]["offset"] == 2
        other = backend.create_session(owner)
        isolated = await backend.chat(owner, other, AgentRequest(message="continuar"))
        assert "Qual busca" in isolated.text and not isolated.tools

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "arguments,message,question",
    [
        ({"product": {"category": "violão"}}, "Procuro ukulele", "Que tipo"),
        (
            {
                "product": {"category": "ukulele"},
                "characteristics": {"atributo_inexistente": "soprano"},
            },
            "Ukulele",
            "Qual característica",
        ),
        (
            {"product": {"category": "ukulele"}, "max_price": "300"},
            "Ukulele até R$ 250",
            "orçamento",
        ),
        (
            {"product": {"category": "ukulele"}, "sql": "SELECT * FROM customers"},
            "Ukulele",
            "explicar",
        ),
    ],
)
def test_interpretation_failure_never_executes_a_relaxed_query(setup, arguments, message, question):
    backend, provider, recorder, owner = setup
    provider.arguments = arguments
    session = backend.create_session(owner)
    answer = asyncio.run(backend.chat(owner, session, AgentRequest(message=message)))
    assert answer.status == "answered" and question in answer.text
    assert "R$" not in answer.text and "estoque registrado" not in answer.text
    assert not recorder.calls and len(provider.requests) == 1
    assert answer.tools[0].error_code == "invalid_arguments"

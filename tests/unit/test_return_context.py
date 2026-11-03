"""Regressões de contexto: verbo 'está' não é referência a um produto anterior."""

import asyncio
import copy
import json
from pathlib import Path

import pytest

from app.agent.models import AgentRequest, FunctionCall, ModelTurn
from app.agent.security import refers_to_product
from app.agent.sessions import ConversationService
from app.database.ingestion import ingest_dataset
from app.retrieval.models import ChunkMetadata, PolicyChunk, PolicyDocument
from app.retrieval.retriever import LexicalRetriever
from app.services.policy_service import PolicyService


@pytest.mark.parametrize(
    "message",
    [
        "Recebi dia 01/11/2026 e ele ainda está embalado",
        "O produto está na embalagem original.",
        "A caixa está fechada.",
        "Ele ESTÁ lacrado.",
        "Ele ESTA\u0301 lacrado.",
    ],
)
def test_verb_does_not_require_a_product_reference(message):
    assert not refers_to_product(message)


@pytest.mark.parametrize(
    "message",
    [
        "Esta guitarra está disponível?",
        "Esse violão está em estoque?",
        "Quanto custa esta?",
        "E em 6x?",
        "E no PIX?",
    ],
)
def test_actual_demonstratives_and_payment_references_are_preserved(message):
    assert refers_to_product(message)


class Provider:
    def __init__(self):
        self.requests = []

    async def complete(self, messages, tools, **kwargs):
        self.requests.append(copy.deepcopy(messages))
        index = max(i for i, item in enumerate(messages) if item.get("role") == "user")
        outputs = [m for m in messages[index + 1 :] if m.get("type") == "function_call_output"]
        if outputs:
            return ModelTurn(
                final_text=json.dumps(
                    {
                        "intent": "answer",
                        "evidence_call_ids": [m["call_id"] for m in outputs],
                        "clarification": None,
                    }
                )
            )
        if "recebi" not in messages[index]["content"].casefold():
            return ModelTurn(
                final_text=json.dumps(
                    {
                        "intent": "clarify",
                        "clarification": "receipt_date",
                        "evidence_call_ids": [],
                    }
                )
            )
        return ModelTurn(
            calls=(
                FunctionCall(
                    call_id="return_policy",
                    name="search_store_policies",
                    arguments=json.dumps(
                        {"query": "devolução arrependimento recebimento embalagem"}
                    ),
                ),
            )
        )


def test_receipt_reply_reaches_policy_with_return_history_and_without_catalog(tmp_path):
    catalog, demo = tmp_path / "catalog.sqlite3", tmp_path / "demo.sqlite3"
    for path in (catalog, demo):
        ingest_dataset(Path("data/samples"), path)
    metadata = ChunkMetadata(
        source_name="politicas_sinteticas.pdf",
        source_sha256="0" * 64,
        version="teste",
        section_id="4.1",
        section_title="Devolução por arrependimento",
        section_path=("Devolução por arrependimento",),
        pages=(1,),
        section_pages=(1,),
    )
    chunk = PolicyChunk(
        chunk_id="return_fixture",
        metadata=metadata,
        kind="paragraph",
        text="Devolução por arrependimento online: até 7 dias corridos do recebimento. "
        "Embalagem original, sem uso, com componentes. Condição sintética de teste.",
    )
    policies = PolicyService(
        LexicalRetriever(
            PolicyDocument(
                source_name="politicas_sinteticas.pdf",
                source_sha256="0" * 64,
                version="teste",
                pages=(),
                sections=(),
                chunks=(chunk,),
            )
        )
    )
    provider = Provider()
    backend = ConversationService.for_demo(
        provider,
        catalog_database=catalog,
        demo_database=demo,
        policies=policies,
    )
    owner = backend.register_demo_client()
    session = backend.create_session(owner)
    question = "Me arrependi da minha compra, posso devolver meu pedido?"
    reply = "Recebi dia 01/11/2026 e ele ainda está embalado"

    async def scenario():
        first = await backend.chat(owner, session, AgentRequest(message=question))
        assert "Em que data você recebeu" in first.text
        answer = await backend.chat(owner, session, AgentRequest(message=reply))
        assert answer.status == "answered" and "seção 4.1" in answer.text
        assert [trace.name for trace in answer.tools] == ["search_store_policies"]
        assert "Qual instrumento" not in answer.text
        assert "devolução autorizada" not in answer.text.casefold()
        current = provider.requests[-2]
        assert [m["content"] for m in current if m.get("role") == "user"] == [question, reply]
        assert "Em que data você recebeu" in " ".join(m.get("content", "") for m in current)
        assert not any("Referência fornecida pelo backend" in m.get("content", "") for m in current)
        other = backend.create_session(owner)
        await backend.chat(owner, other, AgentRequest(message=reply))
        other_messages = provider.requests[-2]
        assert question not in json.dumps(other_messages, ensure_ascii=False)

    asyncio.run(scenario())

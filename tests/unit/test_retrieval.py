"""Fragmentos sintéticos testam ranking, excertos, abstenção e definição da métrica."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.retrieval.document_loader import DocumentLoadError
from app.retrieval.evaluation import PolicyCase, evaluate_retrieval, recall_at_k
from app.retrieval.models import (
    ChunkMetadata,
    DocumentPage,
    DocumentTable,
    PolicyChunk,
    PolicyDocument,
    PolicySearch,
    PolicySection,
)
from app.retrieval.retriever import LexicalRetriever, tokenize
from app.services.policy_service import PolicyService


def make_document() -> PolicyDocument:
    chunks = []
    for number, (section, title, text) in enumerate(
        [
            ("1", "Pagamento", "Metodo: PIX | Condicao: Desconto inteiramente sintetico"),
            ("1.1", "Parcelamento", "Parcelas de teste, sem juros sinteticos."),
            ("1.1", "Parcelamento", "Outra condicao de parcelas para teste."),
            ("2", "Garantia Legal", "Cobertura inteiramente sintetica."),
            ("3", "Prazo de entrega", "Estimativa de teste."),
        ]
    ):
        metadata = ChunkMetadata(
            source_name="synthetic.pdf",
            source_sha256="0" * 64,
            version="0.1",
            section_id=section,
            section_title=title,
            section_path=(title,),
            pages=(1,),
            section_pages=(1,),
        )
        table = (
            DocumentTable(
                page=1,
                headers=("Metodo", "Condicao"),
                rows=(("PIX", "Desconto inteiramente sintetico"),),
            )
            if number == 0
            else None
        )
        chunks.append(
            PolicyChunk(
                chunk_id=f"synthetic:{number}",
                metadata=metadata,
                kind="table" if table else "paragraph",
                text=text,
                table=table,
            )
        )
    sections = {
        chunk.metadata.section_id: PolicySection(
            section_id=chunk.metadata.section_id,
            title=chunk.metadata.section_title,
            pages=(1,),
        )
        for chunk in chunks
    }
    return PolicyDocument(
        source_name="synthetic.pdf",
        source_sha256="0" * 64,
        version="0.1",
        pages=(DocumentPage(number=1, printed_label=None, text="Texto sintetico privado"),),
        sections=tuple(sections.values()),
        chunks=tuple(chunks),
    )


def test_internal_text_is_not_exported_by_default_serialization() -> None:
    document = make_document()
    exported = document.model_dump_json()
    assert "Texto sintetico privado" not in exported
    assert "Desconto inteiramente sintetico" not in exported
    assert "Desconto inteiramente sintetico" not in document.chunks[0].model_dump_json()


def test_unicode_inflections_and_stopwords() -> None:
    assert tokenize("Devoluções e parcelas até 12x") == {"devol", "parcel", "12x"}
    assert tokenize("R$ 500,00") == {"500"}


def test_table_excerpt_and_complete_source_metadata() -> None:
    response = PolicyService(LexicalRetriever(make_document())).search(PolicySearch(query="PIX"))
    assert response.status == "matched"
    hit = response.hits[0]
    assert "Metodo: PIX | Condicao:" in hit.excerpt
    assert hit.metadata.source_name == "synthetic.pdf"
    assert hit.metadata.version == "0.1"
    assert hit.metadata.pages == (1,)
    assert hit.score > 0
    assert hit.lexical_coverage == 1
    assert not hit.excerpt_truncated
    assert "Texto sintetico privado" not in response.model_dump_json()


@pytest.mark.parametrize(
    "query", [" ", "o que e", "astronomia interplanetaria", "prazo do teletransporte interestelar"]
)
def test_no_evidence_or_weak_match_returns_empty(query: str) -> None:
    result = LexicalRetriever(make_document()).search(PolicySearch(query=query))
    assert result.status == "no_evidence"
    assert result.hits == ()


def test_title_anchor_preserves_specific_section_with_unknown_query_word() -> None:
    response = LexicalRetriever(make_document()).search(
        PolicySearch(
            query="Qual o prazo da garantia legal e de quando começa?",
        )
    )
    assert response.hits[0].metadata.section_id == "2"


def test_deterministic_ranking_and_section_diversity() -> None:
    retriever = LexicalRetriever(make_document())
    request = PolicySearch(query="parcelamento", top_k=3)
    first = retriever.search(request)
    assert first == retriever.search(request)
    assert len(first.hits) == 1
    assert first.hits[0].metadata.section_id == "1.1"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": ""},
        {"query": "x" * 501},
        {"query": "pix", "top_k": 0},
        {"query": "pix", "top_k": 6},
    ],
)
def test_query_limits(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        PolicySearch(**kwargs)


def test_excerpt_is_bounded_and_marks_truncation() -> None:
    document = make_document()
    long_chunk = document.chunks[1].model_copy(update={"text": "Parcelas de teste. " * 100})
    document = document.model_copy(update={"chunks": (long_chunk,)})
    hit = LexicalRetriever(document).search(PolicySearch(query="parcelas")).hits[0]
    assert len(hit.excerpt) <= 420
    assert hit.excerpt_truncated


def test_related_bullets_are_preserved_in_one_brief_excerpt() -> None:
    document = make_document()
    chunk = document.chunks[1].model_copy(
        update={
            "text": "• Embalagem sintetica. • Reembolso de teste. • Frete sintetico.",
        }
    )
    document = document.model_copy(update={"chunks": (chunk,)})
    hit = LexicalRetriever(document).search(PolicySearch(query="frete e reembolso")).hits[0]
    assert "Reembolso de teste" in hit.excerpt
    assert "Frete sintetico" in hit.excerpt


def test_multiple_relevant_table_rows_remain_labelled() -> None:
    document = make_document()
    chunk = document.chunks[0].model_copy(
        update={
            "text": "Metodo: PIX | Condicao: Teste\nMetodo: Boleto | Condicao: Outro teste",
        }
    )
    document = document.model_copy(update={"chunks": (chunk,)})
    hit = LexicalRetriever(document).search(PolicySearch(query="PIX e boleto")).hits[0]
    assert "Metodo: PIX" in hit.excerpt
    assert "Metodo: Boleto" in hit.excerpt


def test_recall_counts_all_relevant_sections_not_just_a_hit() -> None:
    assert recall_at_k({"4.2", "8.1"}, ["4.2", "8.2", "8.3"]) == 0.5
    assert recall_at_k({"4.2", "8.1"}, ["4.2", "8.1"]) == 1
    assert recall_at_k(set(), []) is None
    assert recall_at_k({"8.1"}, ["1", "2", "3", "8.1"]) == 0


def test_evaluation_denominators_and_no_internal_text_exported() -> None:
    cases = [
        PolicyCase(
            case_id="a",
            topic="test",
            question="PIX",
            relevant_sections=("1", "2"),
            answer_key="Dois alvos",
        ),
        PolicyCase(
            case_id="b",
            topic="test",
            question="garantia legal",
            relevant_sections=("2",),
            answer_key="Um alvo",
        ),
        PolicyCase(
            case_id="c",
            topic="absence",
            question="astronomia",
            relevant_sections=(),
            answer_key="Ausente",
        ),
    ]
    result = evaluate_retrieval(LexicalRetriever(make_document()), cases)
    assert result["positive_cases"] == 2
    assert result["negative_cases"] == 1
    assert result["macro_recall_at_3"] == 0.75
    assert result["hit_rate_at_3"] == 1
    assert result["negative_abstention_rate"] == 1
    assert "excerpt" not in str(result)
    with pytest.raises(ValueError, match="duplicate_case_id"):
        evaluate_retrieval(LexicalRetriever(make_document()), [cases[0], cases[0]])
    unknown = cases[0].model_copy(update={"relevant_sections": ("99",)})
    with pytest.raises(ValueError, match="unknown_gold_section"):
        evaluate_retrieval(LexicalRetriever(make_document()), [unknown])


def test_missing_document_is_failure_not_a_successful_empty_answer(tmp_path: Path) -> None:
    with pytest.raises(DocumentLoadError):
        PolicyService.from_pdf(tmp_path / "absent.pdf")

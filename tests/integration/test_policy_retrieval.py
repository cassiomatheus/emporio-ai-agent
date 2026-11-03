"""Aceite do manual privado: somente metadados e assertivas breves, sem exportação integral."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.retrieval.document_loader import load_policy_document
from app.retrieval.evaluation import CASES_ADAPTER, PolicyCase, evaluate_retrieval
from app.retrieval.models import PolicyDocument, PolicySearch
from app.retrieval.retriever import LexicalRetriever

PROJECT = Path(__file__).resolve().parents[2]
PDF = PROJECT / "data" / "raw" / "políticas_da_loja.pdf"
CASES_PATH = PROJECT / "tests" / "evaluations" / "policy_cases.json"
CASES = CASES_ADAPTER.validate_json(CASES_PATH.read_bytes())
pytestmark = pytest.mark.local_data


@pytest.fixture(scope="module")
def document() -> PolicyDocument:
    if not PDF.is_file():
        pytest.skip(
            "Manual privado ausente; extração/ranking continuam testados com fontes sintéticas."
        )
    return load_policy_document(PDF)


def test_original_document_structure_and_tables(document: PolicyDocument) -> None:
    assert len(document.pages) == 8
    assert len(document.sections) == 28
    assert len(document.chunks) == 30
    assert document.version == "2.1"
    tables = [chunk for chunk in document.chunks if chunk.kind == "table"]
    assert [(table.table.page, len(table.table.headers)) for table in tables] == [
        (2, 2),
        (2, 2),
        (3, 3),
        (5, 4),
    ]
    payment = next(chunk for chunk in tables if chunk.metadata.section_id == "3")
    pix = next(row for row in payment.table.rows if row[0] == "PIX")
    assert "5%" in pix[2]
    assert "tabela" in pix[2]
    shipping = next(chunk for chunk in tables if chunk.metadata.section_id == "5.2")
    assert shipping.metadata.pages == (5,)
    assert shipping.metadata.section_pages == (4, 5)
    assert [row[1] for row in shipping.table.rows] == [
        "5 a 12 dias úteis",
        "2 a 5 dias úteis",
        "3 a 8 dias úteis",
    ]
    assert {section.section_id: section.pages for section in document.sections}["7.2"] == (6, 7)
    defect = " ".join(chunk.text for chunk in document.chunks if chunk.metadata.section_id == "4.2")
    legal = " ".join(chunk.text for chunk in document.chunks if chunk.metadata.section_id == "8.1")
    assert "30" in defect and "90" not in defect and "compra" in defect
    assert "90" in legal and "recebimento" in legal and "30" not in legal
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == document.source_sha256


def test_excerpts_include_requested_conditions_and_table_rows(document: PolicyDocument) -> None:
    retriever = LexicalRetriever(document)
    refunds = retriever.search(
        PolicySearch(
            query="Quem paga o frete da devolução por arrependimento e quando ocorre o reembolso?"
        )
    )
    excerpt = next(hit.excerpt for hit in refunds.hits if hit.metadata.section_id == "4.1")
    assert "10 dias úteis" in excerpt
    assert "frete" in excerpt.casefold()
    shipping = retriever.search(
        PolicySearch(query="Quais os prazos de PAC, SEDEX e Jadlog para outras cidades?")
    )
    excerpt = next(hit.excerpt for hit in shipping.hits if hit.metadata.section_id == "5.2")
    assert all(carrier in excerpt for carrier in ("PAC", "SEDEX", "Jadlog"))
    boundary = retriever.search(
        PolicySearch(query="Quanto é o frete para pedido de exatamente R$ 500?")
    )
    excerpt = next(hit.excerpt for hit in boundary.hits if hit.metadata.section_id == "5.1")
    assert "acima" in excerpt and "abaixo" in excerpt
    assert set(boundary.model_dump()) == {"status", "hits"}  # Não gera tarifa ou elegibilidade.


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_reference_question_retrieval(document: PolicyDocument, case: PolicyCase) -> None:
    response = LexicalRetriever(document).search(PolicySearch(query=case.question))
    actual = {hit.metadata.section_id for hit in response.hits}
    if case.relevant_sections:
        assert set(case.relevant_sections) <= actual, case.case_id
        assert all(hit.metadata.version == "2.1" and hit.metadata.pages for hit in response.hits)
    else:
        assert response.status == "no_evidence", case.case_id
        assert not response.hits


def test_metric_reproducibility_without_source_export(document: PolicyDocument) -> None:
    first = evaluate_retrieval(LexicalRetriever(document), CASES)
    assert first == evaluate_retrieval(LexicalRetriever(document), CASES)
    assert first["positive_cases"] == 20
    assert first["negative_cases"] == 6
    assert first["macro_recall_at_3"] == 1
    assert first["negative_abstention_rate"] == 1
    assert "excerpt" not in json.dumps(first)


def test_evaluation_script(document: PolicyDocument, tmp_path: Path) -> None:
    output = tmp_path / "results.json"
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT / "scripts" / "evaluate_retrieval.py"),
            "--pdf",
            str(PDF),
            "--cases",
            str(CASES_PATH),
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert json.loads(result.stdout) == report
    assert report["source_sha256"] == document.source_sha256
    assert report["macro_recall_at_3"] == 1

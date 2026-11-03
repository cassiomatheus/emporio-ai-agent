"""PDFs temporários inteiramente sintéticos exercitam extração sem os anexos."""

import hashlib
from pathlib import Path

import pymupdf
import pytest

from app.retrieval.document_loader import DocumentLoadError, load_policy_document


@pytest.fixture
def synthetic_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.pdf"
    with pymupdf.open() as document:
        cover = document.new_page()
        cover.insert_text((72, 80), "Documento sintetico de teste")
        cover.insert_text((72, 110), "Versao 0.1")
        page = document.new_page()
        page.insert_text((72, 80), "1. Politicas sinteticas", fontname="hebo", fontsize=14)
        page.insert_text((72, 120), "1.1 Pagamento de teste", fontname="hebo", fontsize=12)
        page.insert_text((72, 150), "Paragrafo sintetico.")
        page.draw_rect(pymupdf.Rect(72, 180, 500, 250))
        page.draw_line((240, 180), (240, 250))
        page.draw_line((72, 215), (500, 215))
        page.insert_text((80, 200), "Metodo")
        page.insert_text((250, 200), "Condicao")
        page.insert_text((80, 235), "PIX")
        page.insert_text((250, 235), "Informacao sintetica")
        page.insert_text((72, 300), "1.2 Continuacao de teste", fontname="hebo", fontsize=12)
        page.insert_text((72, 330), "Primeiro trecho.")
        page.insert_text((260, 800), "Página 2", fontsize=9)
        page = document.new_page()
        page.insert_text(
            (72, 40), "Empório da Música Manual de Políticas e Procedimentos", fontsize=9
        )
        page.insert_text((72, 90), "Segundo trecho.")
        page.insert_text((72, 120), "1. Item numerado, nao e secao", fontsize=10)
        page.insert_text((72, 180), "2. Encerramento", fontname="hebo", fontsize=14)
        page.insert_text((72, 210), "Fim do teste.")
        document.save(path)
    return path


def test_page_section_table_and_continuation(synthetic_pdf: Path) -> None:
    before = hashlib.sha256(synthetic_pdf.read_bytes()).hexdigest()
    document = load_policy_document(synthetic_pdf)
    assert document.version == "0.1"
    assert len(document.pages) == 3
    assert document.pages[1].printed_label == "2"
    assert [section.section_id for section in document.sections] == ["1", "1.1", "1.2", "2"]
    section = next(section for section in document.sections if section.section_id == "1.2")
    assert section.pages == (2, 3)
    continuation = [chunk for chunk in document.chunks if chunk.metadata.section_id == "1.2"]
    assert "Primeiro trecho" in continuation[0].text
    assert "Segundo trecho" in continuation[0].text
    assert "Item numerado" in continuation[0].text
    assert "Manual de Políticas" not in continuation[0].text
    table = next(chunk for chunk in document.chunks if chunk.kind == "table")
    assert table.metadata.section_id == "1.1"
    assert table.table.headers == ("Metodo", "Condicao")
    assert table.table.rows == (("PIX", "Informacao sintetica"),)
    assert "Metodo: PIX | Condicao: Informacao sintetica" in table.text
    assert table.metadata.pages == (2,)
    assert document.source_sha256 == before
    assert hashlib.sha256(synthetic_pdf.read_bytes()).hexdigest() == before
    assert load_policy_document(synthetic_pdf) == document


def test_missing_or_corrupt_pdf_has_safe_error(tmp_path: Path) -> None:
    for name in ("missing.pdf", "private-path.pdf"):
        path = tmp_path / name
        if name == "private-path.pdf":
            path.write_bytes(b"private raw text, not a PDF")
        with pytest.raises(DocumentLoadError, match="^document_unavailable$"):
            load_policy_document(path)


@pytest.mark.parametrize(
    "content,code", [("", "no_extractable_text"), ("Texto sem secoes", "no_policy_sections")]
)
def test_no_text_or_sections_is_not_fabricated(tmp_path: Path, content: str, code: str) -> None:
    path = tmp_path / "unsupported.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        if content:
            page.insert_text((72, 80), content)
        document.save(path)
    with pytest.raises(DocumentLoadError, match=code):
        load_policy_document(path)


def test_missing_version_remains_unknown(tmp_path: Path) -> None:
    path = tmp_path / "unversioned.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 80), "1. Secao sintetica", fontname="hebo", fontsize=14)
        page.insert_text((72, 110), "Texto sintetico sem versao.")
        document.save(path)
    document = load_policy_document(path)
    assert document.version is None
    assert document.chunks[0].metadata.version is None


def test_duplicate_sections_and_conflicting_versions_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 80), "1. Primeira", fontname="hebo", fontsize=14)
        page.insert_text((72, 110), "Texto sintetico.")
        page.insert_text((72, 140), "1. Outra", fontname="hebo", fontsize=14)
        document.save(path)
    with pytest.raises(DocumentLoadError, match="duplicate_section"):
        load_policy_document(path)
    path = tmp_path / "versions.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 80), "1. Unica", fontname="hebo", fontsize=14)
        page.insert_text((72, 110), "Versao 0.1 e Versao 0.2")
        document.save(path)
    with pytest.raises(DocumentLoadError, match="conflicting_document_versions"):
        load_policy_document(path)

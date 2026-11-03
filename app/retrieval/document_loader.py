"""Extração de PDF textual com seções, continuidade entre páginas e tabelas."""

import hashlib
import re
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.retrieval.models import (
    ChunkMetadata,
    DocumentPage,
    DocumentTable,
    PolicyChunk,
    PolicyDocument,
    PolicySection,
)

HEADING = re.compile(r"^(\d+(?:\.\d+)?)\.?\s+(.+)$")
VERSION = re.compile(r"Vers[aã]o\s+(\d+(?:\.\d+)+)", re.IGNORECASE)


class DocumentLoadError(ValueError):
    """Código seguro: nunca inclui texto interno ou detalhes do caminho."""


@dataclass
class _Element:
    page: int
    y: float
    kind: str
    text: str
    heading: tuple[str, str] | None = None
    table: DocumentTable | None = None


def _clean(text: str) -> str:
    return " ".join(text.replace("\u200b", "").split())


def _boilerplate(text: str) -> bool:
    return bool(re.fullmatch(r"Página\s+\d+", text)) or text.startswith(
        (
            "Empório da Música Manual de Políticas",
            "Empório da Música — Sua música",
            "Última atualização:",
        )
    )


def _table_text(table: DocumentTable) -> str:
    return "\n".join(
        " | ".join(f"{header}: {cell}" for header, cell in zip(table.headers, row, strict=True))
        for row in table.rows
    )


def _flush_paragraph(elements: list[_Element], page: int, y: float, lines: list[str]) -> None:
    if lines:
        elements.append(_Element(page, y, "paragraph", " ".join(lines)))
        lines.clear()


def _page_elements(page: pymupdf.Page) -> list[_Element]:
    elements = []
    boxes = []
    # A biblioteca pode emitir aviso de layout no stdout; não misturá-lo ao JSON dos scripts.
    with redirect_stdout(sys.stderr):
        detected_tables = page.find_tables().tables
    for detected in detected_tables:
        cells = detected.extract()
        if not cells or len(cells) < 2:
            raise DocumentLoadError("invalid_table")
        headers = tuple(_clean(cell or "") for cell in cells[0])
        rows = tuple(tuple(_clean(cell or "") for cell in row) for row in cells[1:])
        if not all(headers) or any(len(row) != len(headers) for row in rows):
            raise DocumentLoadError("invalid_table")
        table = DocumentTable(page=page.number + 1, headers=headers, rows=rows)
        box = pymupdf.Rect(detected.bbox)
        boxes.append(box)
        elements.append(_Element(page.number + 1, box.y0, "table", _table_text(table), table=table))
    for block in page.get_text("dict", sort=True)["blocks"]:
        buffered: list[str] = []
        y = 0.0

        for line in block.get("lines", []):
            text = _clean("".join(span["text"] for span in line["spans"]))
            rect = pymupdf.Rect(line["bbox"])
            center = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
            if not text or _boilerplate(text) or any(center in box for box in boxes):
                continue
            match = HEADING.match(text)
            is_heading = match and any(
                span["flags"] & 16 and span["size"] >= 11.5 for span in line["spans"]
            )
            if is_heading:
                _flush_paragraph(elements, page.number + 1, y, buffered)
                elements.append(
                    _Element(
                        page.number + 1,
                        rect.y0,
                        "heading",
                        text,
                        heading=(match[1], match[2]),
                    )
                )
            else:
                if not buffered:
                    y = rect.y0
                buffered.append(text)
        _flush_paragraph(elements, page.number + 1, y, buffered)
    return sorted(elements, key=lambda element: element.y)


def _chunks(
    source: str,
    digest: str,
    version: str | None,
    sections: list[PolicySection],
    units: dict[str, list[_Element]],
) -> tuple[PolicyChunk, ...]:
    titles = {section.section_id: section.title for section in sections}
    result = []
    for section in sections:
        parent = section.section_id.split(".")[0]
        path = (
            [f"{parent}. {titles[parent]}"]
            if "." in section.section_id and parent in titles
            else []
        )
        path.append(f"{section.section_id} {section.title}")
        groups: list[list[_Element]] = []
        for unit in units[section.section_id]:
            if (
                unit.kind == "paragraph"
                and groups
                and groups[-1][0].kind == "paragraph"
                and sum(len(item.text) for item in groups[-1]) + len(unit.text) <= 1000
            ):
                groups[-1].append(unit)
            else:
                groups.append([unit])
        for number, group in enumerate(groups, start=1):
            result.append(
                PolicyChunk(
                    chunk_id=f"{digest[:12]}:{section.section_id}:{number}",
                    metadata=ChunkMetadata(
                        source_name=source,
                        source_sha256=digest,
                        version=version,
                        section_id=section.section_id,
                        section_title=section.title,
                        section_path=tuple(path),
                        pages=tuple(sorted({item.page for item in group})),
                        section_pages=section.pages,
                    ),
                    kind=group[0].kind,
                    text="\n\n".join(item.text for item in group),
                    table=group[0].table,
                )
            )
    return tuple(result)


def load_policy_document(path: Path) -> PolicyDocument:
    """Não grava extração ou índice no disco; documentos sem texto falham seguros."""
    try:
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            if pdf.needs_pass or not pdf.page_count:
                raise DocumentLoadError("document_unreadable")
            pages = []
            headings: list[tuple[str, str]] = []
            section_pages: dict[str, set[int]] = defaultdict(set)
            units: dict[str, list[_Element]] = defaultdict(list)
            current = None
            for page in pdf:
                text = page.get_text()
                label = re.search(r"Página\s+(\d+)", text)
                pages.append(
                    DocumentPage(
                        number=page.number + 1,
                        printed_label=label[1] if label else None,
                        text=text,
                    )
                )
                for element in _page_elements(page):
                    if element.heading:
                        section_id, title = element.heading
                        if any(key == section_id for key, _ in headings):
                            raise DocumentLoadError("duplicate_section")
                        headings.append((section_id, title))
                        current = section_id
                    if current is not None:
                        section_pages[current].add(element.page)
                        if element.kind != "heading":
                            units[current].append(element)
            if not any(page.text.strip() for page in pages):
                raise DocumentLoadError("no_extractable_text")
            versions = {match[1] for page in pages for match in VERSION.finditer(page.text)}
            if len(versions) > 1:
                raise DocumentLoadError("conflicting_document_versions")
            version = next(iter(versions), None)
            sections = [
                PolicySection(section_id=key, title=title, pages=tuple(sorted(section_pages[key])))
                for key, title in headings
            ]
            chunks = _chunks(path.name, digest, version, sections, units)
            if not chunks:
                raise DocumentLoadError("no_policy_sections")
            return PolicyDocument(
                source_name=path.name,
                source_sha256=digest,
                version=version,
                pages=tuple(pages),
                sections=tuple(sections),
                chunks=chunks,
            )
    except DocumentLoadError:
        raise
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise DocumentLoadError("document_unavailable") from exc

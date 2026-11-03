"""Texto interno separado de metadados e excertos breves de recuperação."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class RetrievalModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class DocumentPage(RetrievalModel):
    number: int
    printed_label: str | None
    text: str = Field(repr=False, exclude=True)


class DocumentTable(RetrievalModel):
    page: int
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...] = Field(repr=False, exclude=True)


class ChunkMetadata(RetrievalModel):
    source_name: str
    source_sha256: str
    version: str | None
    section_id: str
    section_title: str
    section_path: tuple[str, ...]
    pages: tuple[int, ...]
    section_pages: tuple[int, ...]


class PolicyChunk(RetrievalModel):
    chunk_id: str
    metadata: ChunkMetadata
    kind: Literal["paragraph", "table"]
    text: str = Field(repr=False, exclude=True)
    table: DocumentTable | None = Field(default=None, repr=False, exclude=True)


class PolicySection(RetrievalModel):
    section_id: str
    title: str
    pages: tuple[int, ...]


class PolicyDocument(RetrievalModel):
    source_name: str
    source_sha256: str
    version: str | None
    pages: tuple[DocumentPage, ...] = Field(repr=False, exclude=True)
    sections: tuple[PolicySection, ...]
    chunks: tuple[PolicyChunk, ...] = Field(repr=False, exclude=True)


class PolicySearch(RetrievalModel):
    query: Annotated[str, Field(min_length=1, max_length=500)]
    top_k: Annotated[int, Field(strict=True, ge=1, le=5)] = 3


class PolicyHit(RetrievalModel):
    chunk_id: str
    metadata: ChunkMetadata
    excerpt: Annotated[str, Field(max_length=600)]
    excerpt_truncated: bool
    score: float
    lexical_coverage: float
    match_grade: Literal["strong", "partial"]


class PolicySearchResult(RetrievalModel):
    status: Literal["matched", "no_evidence"]
    hits: tuple[PolicyHit, ...]

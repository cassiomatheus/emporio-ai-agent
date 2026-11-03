"""Recupera fontes breves; não decide elegibilidade nem gera resposta de política."""

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from app.retrieval.document_loader import load_policy_document
from app.retrieval.models import PolicyChunk, PolicySearch, PolicySearchResult, RetrievalModel
from app.retrieval.retriever import LexicalRetriever
from app.services.product_service import normalize_text


class StoreInfoSource(RetrievalModel):
    source_name: str
    source_sha256: str
    version: str | None
    section_id: str | None
    pages: tuple[int, ...]


class StoreInfoEntry(RetrievalModel):
    label: Annotated[str, Field(min_length=1, max_length=80)]
    value: Annotated[str, Field(min_length=1, max_length=300)]
    source: StoreInfoSource


class StoreInfo(RetrievalModel):
    subject: Literal["address", "hours", "contacts"]
    entries: Annotated[tuple[StoreInfoEntry, ...], Field(max_length=8)]
    cautions: tuple[str, ...]


PHONE = re.compile(r"\(\d{2}\)\s*\d{4,5}-\d{4}")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[\w-]+", re.UNICODE)


class PolicyService:
    def __init__(self, retriever: LexicalRetriever) -> None:
        self.retriever = retriever

    @classmethod
    def from_pdf(cls, path: Path) -> "PolicyService":
        return cls(LexicalRetriever(load_policy_document(path)))

    def search(self, request: PolicySearch) -> PolicySearchResult:
        return self.retriever.search(request)

    def get_store_info(self, subject: Literal["address", "hours", "contacts"]) -> StoreInfo:
        """Seleciona somente informação pública de seções conhecidas do manual."""
        document = self.retriever.document
        entries = []
        cautions = []

        def citation(chunk: PolicyChunk) -> StoreInfoSource:
            return StoreInfoSource(
                source_name=document.source_name,
                source_sha256=document.source_sha256,
                version=document.version,
                section_id=chunk.metadata.section_id,
                pages=chunk.metadata.pages,
            )

        for chunk in document.chunks:
            section = chunk.metadata.section_id
            if chunk.table and (
                (subject in ("address", "contacts") and section == "1.2")
                or (subject == "hours" and section == "2")
            ):
                for row in chunk.table.rows:
                    if len(row) != 2:
                        continue
                    label = normalize_text(row[0])
                    allowed = (
                        subject == "hours"
                        or (subject == "address" and label == "endereco")
                        or (subject == "contacts" and label in ("telefone / whatsapp", "e-mail"))
                    )
                    if allowed and row[1]:
                        entries.append(
                            StoreInfoEntry(label=row[0], value=row[1], source=citation(chunk))
                        )
            elif subject == "contacts" and section == "7":
                entries.extend(
                    StoreInfoEntry(label="WhatsApp", value=match[0], source=citation(chunk))
                    for match in PHONE.finditer(chunk.text)
                )
        if subject == "contacts" and document.pages:
            cover = document.pages[0]
            source = StoreInfoSource(
                source_name=document.source_name,
                source_sha256=document.source_sha256,
                version=document.version,
                section_id=None,
                pages=(cover.number,),
            )
            for label, pattern in (("Telefone / WhatsApp", PHONE), ("E-mail", EMAIL)):
                entries.extend(
                    StoreInfoEntry(label=label, value=match[0], source=source)
                    for match in pattern.finditer(cover.text)
                )
            phones = {entry.value for entry in entries if normalize_text(entry.label) != "e-mail"}
            emails = {entry.value for entry in entries if normalize_text(entry.label) == "e-mail"}
            if len(phones) > 1:
                cautions.append("conflicting_phone_numbers")
            if len(emails) > 1:
                cautions.append("conflicting_emails")
            if cautions:
                cautions.append("confirm_contacts_with_store")
        if subject == "hours":
            cautions.extend(("special_hours_may_vary", "not_an_open_now_check"))
        # Não cortar fatos silenciosamente se um novo layout exceder o contrato.
        return StoreInfo(subject=subject, entries=tuple(entries), cautions=tuple(cautions))

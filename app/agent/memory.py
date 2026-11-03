"""Memória efêmera e limitada; referências contêm IDs, nunca preços em cache."""

from collections import deque
from dataclasses import dataclass, field

from pydantic import Field

from app.agent.models import AgentModel, SearchPage


class ProductReference(AgentModel):
    product_ids: tuple[int, ...] = Field(default=(), max_length=20)


class ConversationContext(AgentModel):
    history: tuple[tuple[str, str], ...] = Field(default=(), repr=False, exclude=True)
    reference: ProductReference = Field(default_factory=ProductReference)
    search_page: SearchPage | None = Field(default=None, repr=False, exclude=True)


@dataclass(repr=False)
class ConversationMemory:
    max_turns: int
    max_characters: int
    _turns: deque[tuple[str, str]] = field(default_factory=deque, init=False)
    _reference: ProductReference = field(default_factory=ProductReference, init=False)
    _search_page: SearchPage | None = field(default=None, init=False)

    def context(self) -> ConversationContext:
        return ConversationContext(
            history=tuple(self._turns), reference=self._reference, search_page=self._search_page
        )

    def append(
        self,
        message: str,
        reply: str,
        reference: ProductReference | None = None,
        *,
        search_page: SearchPage | None = None,
    ) -> None:
        self._turns.append((message, reply))
        while (
            len(self._turns) > self.max_turns
            or sum(len(user) + len(assistant) for user, assistant in self._turns)
            > self.max_characters
        ):
            self._turns.popleft()
        if reference is not None:
            self._reference = reference
        self._search_page = search_page
        # Se nem o último par couber, não manter uma referência sem contexto.
        if not self._turns:
            self._reference = ProductReference()
            self._search_page = None

    def clear(self) -> None:
        self._turns.clear()
        self._reference = ProductReference()
        self._search_page = None

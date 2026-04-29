from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..models import Chunk, DocumentAST


class TokenizerProtocol(Protocol):
    """Abstraction for counting text units."""

    def encode(self, text: str) -> list[int]: ...

    def count(self, text: str) -> int: ...


class MarkdownParserProtocol(Protocol):
    """Turn markdown text into the internal document model."""

    def parse(
        self,
        text: str,
        *,
        document_title: str = "document.md",
        document_metadata: dict[str, object] | None = None,
    ) -> DocumentAST: ...


class SplitterProtocol(Protocol):
    """Split a parsed document into chunks."""

    def split(self, document: DocumentAST) -> list[Chunk]: ...

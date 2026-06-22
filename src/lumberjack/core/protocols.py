from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from .models import Chunk, DocumentAST


class TokenizerProtocol(Protocol):
    """Abstraction for counting text units."""

    def encode(self, text: str, *, cache=False) -> tuple[int, ...]: ...

    def count(self, text: str, *, cache=False) -> int: ...


ParserInput = TypeVar("ParserInput", str, bytes)


class ParserProtocol(Protocol[ParserInput]):
    """Turn a raw document (Markdown / HTML text or DOCX bytes) into the shared DocumentAST.

    Each format-specific parser (MarkdownItParser, HTMLParser, DocxParser)
    implements this protocol so the rest of the pipeline (``lumber()``,
    splitters) can treat them uniformly. The ``data`` argument is ``str`` for
    text formats and ``bytes`` for binary formats (DOCX); parsers raise
    :class:`TypeError` at runtime when ``data`` does not match the expected
    type.
    """

    block_kinds: frozenset[str]

    def parse(
        self,
        data: ParserInput,
        *,
        document_title: str | None = None,
        document_metadata: dict[str, object] | None = None,
        max_heading_level: int | None = None,
    ) -> DocumentAST: ...


class SplitterProtocol(Protocol):
    """Split a parsed document into chunks."""

    def split(self, document: DocumentAST) -> list[Chunk]: ...

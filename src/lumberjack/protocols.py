from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from .models import Chunk, DocumentAST


class TokenizerProtocol(Protocol):
    """Abstraction for counting text units in manual parser/splitter pipelines.

    Tokenizers only encode and count text. Exact or incremental measurement is
    selected by the splitter implementation; either mode can use any tokenizer.
    """

    def encode(self, text: str, *, cache=False) -> tuple[int, ...]: ...

    def count(self, text: str, *, cache=False) -> int: ...


ParserInput = TypeVar("ParserInput", str, bytes)


class ParserProtocol(Protocol[ParserInput]):
    """Turn a raw document (Markdown / HTML text or DOCX bytes) into the shared DocumentAST.

    Each format-specific parser (MarkdownItParser, HTMLParser, DocxParser)
    implements this protocol so splitters can treat them uniformly. The
    ``data`` argument is ``str`` for text formats and ``bytes`` for binary
    formats (DOCX); parsers raise :class:`TypeError` at runtime when ``data``
    does not match the expected type. Custom parsers are used by composing a
    manual ``parse -> split`` pipeline instead of passing them to ``lumber()``.
    """

    block_kinds: frozenset[str]

    def parse(
        self,
        data: ParserInput,
        *,
        document_title: str | None = None,
        metadata_overrides: Mapping[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocumentAST: ...


class SplitterProtocol(Protocol):
    """Split a parsed document into chunks in a manual pipeline."""

    def split(self, document: DocumentAST) -> list[Chunk]: ...

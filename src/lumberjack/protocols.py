from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .models import ChunkDraft, DocTree, Document, ExtractionResult


class TokenizerProtocol(Protocol):
    """Measure text units used by splitters and finalizers."""

    def encode(self, text: str, *, cache=False) -> tuple[int, ...]: ...

    def count(self, text: str, *, cache=False) -> int: ...


class ParserProtocol(Protocol):
    """Parse a raw document into the shared structured representation."""

    block_kinds: frozenset[str]

    def parse(self, document: Document) -> DocTree: ...


@runtime_checkable
class ExtractionParserProtocol(Protocol):
    """Optional parser capability for exposing an upstream extraction view."""

    def extract(self, document: Document) -> ExtractionResult | None: ...


class SplitterProtocol(Protocol):
    """Split a structured document into unfinished drafts."""

    @property
    def tokenizer(self) -> TokenizerProtocol: ...

    def split(self, document: DocTree) -> list[ChunkDraft]: ...


class TextNormalizerProtocol(Protocol):
    """Stabilize rendered draft text before transformation."""

    def normalize(self, text: str) -> str: ...


class TextTransformerProtocol(Protocol):
    """Normalize or simplify text before final chunk creation."""

    def transform(self, text: str) -> str: ...

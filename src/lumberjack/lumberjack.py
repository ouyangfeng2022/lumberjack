from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ._internal.pipeline import build_pipeline
from .models import Document, InputFormat, SplitResult
from .protocols import (
    ParserProtocol,
    SplitterProtocol,
    TextNormalizerProtocol,
    TextTransformerProtocol,
    TokenizerProtocol,
)


class Lumberjack:
    """Orchestrate the complete document-to-chunks pipeline."""

    def __init__(
        self,
        *,
        tokenizer: TokenizerProtocol | None = None,
        parser: ParserProtocol | None = None,
        splitter: SplitterProtocol | None = None,
        normalizer: TextNormalizerProtocol | None = None,
        transformer: TextTransformerProtocol | None = None,
        max_tokens: int = 1200,
        skip_empty_sections: bool = True,
    ) -> None:
        self._pipeline = build_pipeline(
            tokenizer=tokenizer,
            parser=parser,
            splitter=splitter,
            normalizer=normalizer,
            transformer=transformer,
            max_tokens=max_tokens,
            skip_empty_sections=skip_empty_sections,
        )
        self.tokenizer = self._pipeline.tokenizer
        self.parser = self._pipeline.parser
        self.splitter = self._pipeline.splitter
        self.finalizer = self._pipeline.finalizer

    def saw(
        self,
        document: Document | str | bytes | Path,
        *,
        format: InputFormat = "auto",
        document_title: str | None = None,
        metadata_overrides: Mapping[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> SplitResult:
        """Parse, split, and finalize one raw document into final chunks."""
        if not isinstance(document, Document):
            document = Document(
                source=document,
                format=format,
                document_title=document_title,
                metadata_overrides=dict(metadata_overrides or {}),
                source_path=source_path,
            )
        return self._pipeline.run(document)


__all__ = ["Lumberjack"]

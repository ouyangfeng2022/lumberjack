from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

from ._internal.pipeline import build_pipeline
from .models import Document, DocumentResult, InputFormat, PipelineTrace, SplitResult
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

    def trace(
        self,
        document: Document | str | bytes | Path,
        *,
        format: InputFormat = "auto",
        document_title: str | None = None,
        metadata_overrides: Mapping[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> PipelineTrace:
        """Run one document and return explicit parser, splitter, and finalizer views."""
        if not isinstance(document, Document):
            document = Document(
                source=document,
                format=format,
                document_title=document_title,
                metadata_overrides=dict(metadata_overrides or {}),
                source_path=source_path,
            )
        return self._pipeline.run_trace(document)

    def saw_many(
        self, inputs: Iterable[Document], *, fail_fast: bool = False
    ) -> Iterator[DocumentResult]:
        """Stream per-document outcomes without preloading inputs into memory.

        Results preserve input order. Components are reused sequentially; this is
        deliberate because optional tokenizer implementations are not thread-safe.
        Set ``fail_fast`` to re-raise the first document failure.
        """
        for index, document in enumerate(inputs):
            input_id = str(document.source_path or document.document_title or index)
            try:
                yield DocumentResult(input_id=input_id, result=self.saw(document))
            except Exception as error:
                if fail_fast:
                    raise
                yield DocumentResult(
                    input_id=input_id, error=f"{type(error).__name__}: {error}"
                )


__all__ = ["Lumberjack"]

"""Private pipeline assembly shared by Python, CLI, and Web interfaces."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from ..block import BlockOption
from ..finalizer import ChunkFinalizer
from ..models import Document, InputFormat, PipelineTrace, SplitResult
from ..normalizer import TextNormalizer
from ..parser import AutoParser
from ..protocols import (
    ExtractionParserProtocol,
    ParserProtocol,
    SplitterProtocol,
    TextNormalizerProtocol,
    TextTransformerProtocol,
    TokenizerProtocol,
)
from ..splitter import (
    ExactSectionSplitter,
    ExactSiblingSplitter,
    ExactSubtreeSplitter,
    RecordSplitter,
    SectionSplitter,
    SiblingSplitter,
    SubtreeSplitter,
)
from ..tokenizer import (
    ApproxByteTokenizer,
    TiktokenTokenizer,
    TransformersTokenizer,
)
from ..transformer import TextTransformer

_SPLITTERS = {
    "sibling": SiblingSplitter,
    "incremental-sibling": SiblingSplitter,
    "exact-sibling": ExactSiblingSplitter,
    "subtree": SubtreeSplitter,
    "incremental-subtree": SubtreeSplitter,
    "exact-subtree": ExactSubtreeSplitter,
    "section": SectionSplitter,
    "incremental-section": SectionSplitter,
    "exact-section": ExactSectionSplitter,
    "record": RecordSplitter,
}


class TokenizerRegistry:
    """Reuse expensive tokenizer backends while keeping text caches isolated."""

    def __init__(self) -> None:
        self._templates: dict[str, TiktokenTokenizer | TransformersTokenizer] = {}
        self._lock = Lock()

    def create(self, name: str) -> TokenizerProtocol:
        normalized = name.strip().lower()
        if normalized == "approx":
            return ApproxByteTokenizer()
        if normalized not in {"tiktoken", "transformers"}:
            raise ValueError(f"Unsupported tokenizer: {name}")

        with self._lock:
            template = self._templates.get(normalized)
            if template is None:
                template = (
                    TiktokenTokenizer()
                    if normalized == "tiktoken"
                    else TransformersTokenizer()
                )
                self._templates[normalized] = template
        return template.with_fresh_cache()


def _tokenizer(selection: TokenizerProtocol | str | None) -> TokenizerProtocol:
    if selection is None:
        return ApproxByteTokenizer()
    if not isinstance(selection, str):
        return selection
    normalized = selection.strip().lower()
    if normalized == "approx":
        return ApproxByteTokenizer()
    if normalized == "tiktoken":
        return TiktokenTokenizer()
    if normalized == "transformers":
        return TransformersTokenizer()
    raise ValueError(f"Unsupported tokenizer: {selection}")


@dataclass(slots=True)
class Pipeline:
    """Resolved components for one reusable document pipeline."""

    tokenizer: TokenizerProtocol
    parser: ParserProtocol
    splitter: SplitterProtocol
    finalizer: ChunkFinalizer

    def run(self, document: Document) -> SplitResult:
        trace = self.run_trace(document)
        return SplitResult(document=trace.document, chunks=list(trace.chunks))

    def run_trace(self, document: Document) -> PipelineTrace:
        """Run all stages and retain their public intermediate representations."""
        # Every document splits from a zero text cache, matching the web path
        # (per-request fresh cache) and the CLI (per-file pipeline).  Optional
        # guard: custom tokenizers may not expose a clearable cache.
        clear_cache = getattr(self.tokenizer, "clear_cache", None)
        if callable(clear_cache):
            clear_cache()
        extraction = (
            self.parser.extract(document)
            if isinstance(self.parser, ExtractionParserProtocol)
            else None
        )
        doc_tree = self.parser.parse(document)
        drafts = self.splitter.split(doc_tree)
        chunks = self.finalizer.finalize(doc_tree, drafts)
        return PipelineTrace(
            input=document,
            extraction=extraction,
            document=doc_tree,
            drafts=tuple(drafts),
            chunks=tuple(chunks),
        )


def build_pipeline(
    *,
    tokenizer: TokenizerProtocol | str | None = None,
    parser: ParserProtocol | None = None,
    splitter: SplitterProtocol | str | None = None,
    normalizer: TextNormalizerProtocol | None = None,
    transformer: TextTransformerProtocol | None = None,
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_ratio: float = 0.125,
    skip_empty_sections: bool = True,
    heading_sensitive: bool = True,
    max_heading_level: int | None = None,
    block_options: Iterable[BlockOption] | None = None,
) -> Pipeline:
    """Validate selections and assemble the canonical component pipeline."""
    if tokenizer is None and splitter is not None and not isinstance(splitter, str):
        tokenizer_impl = splitter.tokenizer
    else:
        tokenizer_impl = _tokenizer(tokenizer)

    if splitter is None:
        splitter_name = "section"
    elif isinstance(splitter, str):
        splitter_name = splitter.strip().lower()
    else:
        splitter_name = None

    if splitter_name is not None:
        splitter_class = _SPLITTERS.get(splitter_name)
        if splitter_class is None:
            raise ValueError(f"Unsupported splitter: {splitter}")
        if splitter_class is RecordSplitter:
            splitter_impl = splitter_class(
                tokenizer_impl,
                max_tokens=max_tokens,
                ideal_max_tokens_ratio=ideal_max_tokens_ratio,
                skip_empty_sections=skip_empty_sections,
                block_options=block_options,
            )
        else:
            splitter_impl = splitter_class(
                tokenizer_impl,
                max_tokens=max_tokens,
                ideal_max_tokens_ratio=ideal_max_tokens_ratio,
                merge_below_ratio=merge_below_ratio,
                skip_empty_sections=skip_empty_sections,
                heading_sensitive=heading_sensitive,
                max_heading_level=max_heading_level,
                block_options=block_options,
            )
    else:
        assert splitter is not None and not isinstance(splitter, str)
        splitter_impl = splitter
        if splitter_impl.tokenizer is not tokenizer_impl:
            raise ValueError(
                "splitter and finalizer must share the same tokenizer instance"
            )

    return Pipeline(
        tokenizer=tokenizer_impl,
        parser=parser if parser is not None else AutoParser(),
        splitter=splitter_impl,
        finalizer=ChunkFinalizer(
            tokenizer_impl,
            normalizer=normalizer if normalizer is not None else TextNormalizer(),
            transformer=(transformer if transformer is not None else TextTransformer()),
            skip_empty_sections=skip_empty_sections,
        ),
    )


def split_source(
    source: str | bytes | Path,
    *,
    format: InputFormat = "auto",
    document_title: str | None = None,
    metadata_overrides: Mapping[str, object] | None = None,
    source_path: str | Path | None = None,
    tokenizer: TokenizerProtocol | str = "approx",
    splitter: SplitterProtocol | str = "section",
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_ratio: float = 0.125,
    skip_empty_sections: bool = True,
    heading_sensitive: bool = True,
    max_heading_level: int | None = None,
    block_options: Iterable[BlockOption] | None = None,
) -> SplitResult:
    """Run the configurable built-in pipeline for non-Python interfaces."""
    pipeline = build_pipeline(
        tokenizer=tokenizer,
        splitter=splitter,
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_ratio=merge_below_ratio,
        skip_empty_sections=skip_empty_sections,
        heading_sensitive=heading_sensitive,
        max_heading_level=max_heading_level,
        block_options=block_options,
    )
    return pipeline.run(
        Document(
            source=source,
            format=format,
            document_title=document_title,
            metadata_overrides=dict(metadata_overrides or {}),
            source_path=source_path,
        )
    )


def trace_source(
    source: str | bytes | Path,
    *,
    format: InputFormat = "auto",
    document_title: str | None = None,
    metadata_overrides: Mapping[str, object] | None = None,
    source_path: str | Path | None = None,
    tokenizer: TokenizerProtocol | str = "approx",
    splitter: SplitterProtocol | str = "section",
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_ratio: float = 0.125,
    skip_empty_sections: bool = True,
    heading_sensitive: bool = True,
    max_heading_level: int | None = None,
    block_options: Iterable[BlockOption] | None = None,
) -> PipelineTrace:
    """Run the configurable pipeline and retain public intermediate stages."""
    pipeline = build_pipeline(
        tokenizer=tokenizer,
        splitter=splitter,
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_ratio=merge_below_ratio,
        skip_empty_sections=skip_empty_sections,
        heading_sensitive=heading_sensitive,
        max_heading_level=max_heading_level,
        block_options=block_options,
    )
    return pipeline.run_trace(
        Document(
            source=source,
            format=format,
            document_title=document_title,
            metadata_overrides=dict(metadata_overrides or {}),
            source_path=source_path,
        )
    )


BUILTIN_SPLITTER_NAMES = tuple(_SPLITTERS)

__all__ = [
    "BUILTIN_SPLITTER_NAMES",
    "Pipeline",
    "TokenizerRegistry",
    "build_pipeline",
    "split_source",
    "trace_source",
]

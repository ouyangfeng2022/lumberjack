"""Private adapter shared by the CLI and Web API."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from ..block import BlockOption
from ..models import Chunk
from ..parser import AutoParser, InputFormat
from ..splitter import (
    ExactSectionSplitter,
    ExactSiblingSplitter,
    ExactSubtreeSplitter,
    SectionSplitter,
    SiblingSplitter,
    SubtreeSplitter,
)
from ..tokenizer import (
    ApproxCharTokenizer,
    TiktokenTokenizer,
    TransformersTokenizer,
)

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
}


def _tokenizer(name: str):
    normalized = name.strip().lower()
    if normalized == "approx":
        return ApproxCharTokenizer()
    if normalized == "tiktoken":
        return TiktokenTokenizer()
    if normalized == "transformers":
        return TransformersTokenizer()
    raise ValueError(f"Unsupported tokenizer: {name}")


def split_source(
    source: str | bytes | Path,
    *,
    format: InputFormat = "auto",
    document_title: str | None = None,
    metadata_overrides: Mapping[str, object] | None = None,
    source_path: str | Path | None = None,
    tokenizer: str = "approx",
    splitter: str = "sibling",
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_ratio: float = 0.125,
    skip_empty_sections: bool = True,
    render_headings: bool = True,
    max_heading_level: int | None = None,
    block_options: Iterable[BlockOption] | None = None,
) -> list[Chunk]:
    """Run the configurable built-in pipeline for non-Python interfaces."""
    parser_impl = AutoParser(format=format)
    document = parser_impl.parse(
        source,
        document_title=document_title,
        metadata_overrides=metadata_overrides,
        source_path=source_path,
    )
    tokenizer_impl = _tokenizer(tokenizer)
    normalized_splitter = splitter.strip().lower()
    if normalized_splitter not in _SPLITTERS:
        raise ValueError(f"Unsupported splitter: {splitter}")
    common = {
        "max_tokens": max_tokens,
        "ideal_max_tokens_ratio": ideal_max_tokens_ratio,
        "skip_empty_sections": skip_empty_sections,
        "render_headings": render_headings,
        "max_heading_level": max_heading_level,
        "block_options": block_options,
    }
    if normalized_splitter in {"sibling", "incremental-sibling"}:
        splitter_impl = SiblingSplitter(
            tokenizer_impl, merge_below_ratio=merge_below_ratio, **common
        )
    elif normalized_splitter == "exact-sibling":
        splitter_impl = ExactSiblingSplitter(
            tokenizer_impl, merge_below_ratio=merge_below_ratio, **common
        )
    elif normalized_splitter in {"subtree", "incremental-subtree"}:
        splitter_impl = SubtreeSplitter(
            tokenizer_impl, merge_below_ratio=merge_below_ratio, **common
        )
    elif normalized_splitter == "exact-subtree":
        splitter_impl = ExactSubtreeSplitter(
            tokenizer_impl, merge_below_ratio=merge_below_ratio, **common
        )
    elif normalized_splitter in {"section", "incremental-section"}:
        splitter_impl = SectionSplitter(tokenizer_impl, **common)
    else:
        splitter_impl = ExactSectionSplitter(tokenizer_impl, **common)
    return splitter_impl.split(document)


BUILTIN_SPLITTER_NAMES = tuple(_SPLITTERS)

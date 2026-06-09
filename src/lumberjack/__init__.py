from __future__ import annotations

from typing import TYPE_CHECKING

from .core import create_parser, create_splitter, create_tokenizer
from .core.models import BlockHandling, Chunk, SplitOptions

if TYPE_CHECKING:
    from .core.protocols import (
        MarkdownParserProtocol,
        SplitterProtocol,
        TokenizerProtocol,
    )


def _normalize_block_handling(
    raw: dict[str, BlockHandling | str] | None,
) -> dict[str, BlockHandling]:
    """Convert a dict with str/BlockHandling values to a pure BlockHandling dict."""
    if raw is None:
        return {}
    result: dict[str, BlockHandling] = {}
    for key, value in raw.items():
        if isinstance(value, BlockHandling):
            result[key] = value
        else:
            result[key] = BlockHandling(value)
    return result


def _normalize_nosplit_kinds(
    raw: frozenset[str] | set[str] | list[str] | None,
) -> frozenset[str]:
    """Normalize nosplit_kinds to a frozenset of lowercase kind strings."""
    if raw is None:
        return frozenset()
    return frozenset(k.strip().lower() for k in raw if k.strip())


def lumber(
    text: str,
    *,
    document_title: str | None = None,
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_tokens: int = 50,
    overlap_tokens: int = 0,
    merge_small_chunks: bool = True,
    skip_empty_sections: bool = True,
    recursive_split: bool = False,
    block_handling: dict[str, BlockHandling | str] | None = None,
    nosplit_kinds: frozenset[str] | set[str] | list[str] | None = None,
    block_max_tokens: dict[str, int] | None = None,
    disable_lheading: bool = False,
    tokenizer: str | TokenizerProtocol = "simple",
    parser: str | MarkdownParserProtocol = "default",
    splitter: str | SplitterProtocol = "recursive",
    document_metadata: dict[str, object] | None = None,
) -> list[Chunk]:
    """Split markdown text into chunks recursively."""
    tokenizer_impl = (
        create_tokenizer(tokenizer) if isinstance(tokenizer, str) else tokenizer
    )
    parser_impl = (
        create_parser(parser, disable_lheading=disable_lheading)
        if isinstance(parser, str)
        else parser
    )
    document = parser_impl.parse(
        text,
        document_title=document_title,
        document_metadata=document_metadata,
    )
    normalized_handling = _normalize_block_handling(block_handling)
    normalized_nosplit = _normalize_nosplit_kinds(nosplit_kinds)
    options = SplitOptions(
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_tokens=merge_below_tokens,
        overlap_tokens=overlap_tokens,
        merge_small_chunks=merge_small_chunks,
        skip_empty_sections=skip_empty_sections,
        recursive_split=recursive_split,
        block_handling=normalized_handling,
        nosplit_kinds=normalized_nosplit,
        block_max_tokens=block_max_tokens or {},
        block_kinds=parser_impl.block_kinds,
    )
    splitter_impl = (
        create_splitter(splitter, tokenizer=tokenizer_impl, options=options)
        if isinstance(splitter, str)
        else splitter
    )
    return splitter_impl.split(document)


__all__ = ["lumber"]

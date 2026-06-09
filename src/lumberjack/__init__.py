from __future__ import annotations

from typing import TYPE_CHECKING

from .core import create_parser, create_splitter, create_tokenizer
from .core.models import BlockConfig, Chunk, SplitOptions

if TYPE_CHECKING:
    from .core.protocols import (
        MarkdownParserProtocol,
        SplitterProtocol,
        TokenizerProtocol,
    )


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
    block_options: dict[str, BlockConfig | dict] | None = None,
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
    # Build block_options: start from parser defaults, then merge user overrides.
    resolved = dict.fromkeys(sorted(parser_impl.block_kinds), BlockConfig())
    if block_options:
        for key, value in block_options.items():
            if isinstance(value, BlockConfig):
                resolved[key] = value
            elif isinstance(value, dict):
                resolved[key] = BlockConfig(**value)
            else:
                msg = f"block_options[{key!r}] must be BlockConfig or dict, got {type(value).__name__}"
                raise TypeError(msg)
    options = SplitOptions(
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_tokens=merge_below_tokens,
        overlap_tokens=overlap_tokens,
        merge_small_chunks=merge_small_chunks,
        skip_empty_sections=skip_empty_sections,
        recursive_split=recursive_split,
        block_options=resolved,
    )
    splitter_impl = (
        create_splitter(splitter, tokenizer=tokenizer_impl, options=options)
        if isinstance(splitter, str)
        else splitter
    )
    return splitter_impl.split(document)


__all__ = ["lumber"]

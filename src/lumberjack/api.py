from __future__ import annotations

from typing import TYPE_CHECKING

from .core import MarkdownSplitter, create_parser, create_tokenizer
from .models import Chunk, SplitOptions

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .base.interfaces import MarkdownParserProtocol, TokenizerProtocol


def lumber(
    text: str,
    *,
    document_title: str | None = None,
    max_tokens: int = 1200,
    merge_below_tokens: int = 50,
    overlap_tokens: int = 0,
    retain_headings: bool = True,
    include_common_headings: bool = True,
    merge_small_chunks: bool = True,
    isolate_front_matter: bool = True,
    split_oversized_blocks: Iterable[str] = frozenset(
        {
            "paragraph",
            "blockquote",
            "html_block",
        }
    ),
    disable_lheading: bool = False,
    tokenizer: str | TokenizerProtocol = "simple",
    parser: str | MarkdownParserProtocol = "default",
    document_metadata: dict[str, object] | None = None,
) -> list[Chunk]:
    """Split markdown text into semantic chunks."""
    tokenizer_impl = create_tokenizer(tokenizer) if isinstance(tokenizer, str) else tokenizer
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
    splitter = MarkdownSplitter(
        tokenizer=tokenizer_impl,
        options=SplitOptions(
            max_tokens=max_tokens,
            merge_below_tokens=merge_below_tokens,
            overlap_tokens=overlap_tokens,
            retain_headings=retain_headings,
            include_common_headings=include_common_headings,
            merge_small_chunks=merge_small_chunks,
            isolate_front_matter=isolate_front_matter,
            split_oversized_blocks=frozenset(split_oversized_blocks),
        ),
    )
    return splitter.split(document)


__all__ = ["lumber"]

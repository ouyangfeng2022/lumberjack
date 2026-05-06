from __future__ import annotations

from typing import TYPE_CHECKING

from .core import MarkdownSplitter, create_parser, create_tokenizer
from .models import Chunk, DocumentAST, SplitOptions

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .base.interfaces import MarkdownParserProtocol, TokenizerProtocol


def _parse_markdown(
    text: str,
    *,
    document_title: str = "document.md",
    parser: str | MarkdownParserProtocol = "default",
    document_metadata: dict[str, object] | None = None,
) -> DocumentAST:
    """Parse markdown text into the internal document model."""
    parser_impl = _resolve_parser(parser)
    return parser_impl.parse(
        text,
        document_title=document_title,
        document_metadata=document_metadata,
    )


def lumber(
    text: str,
    *,
    document_title: str = "document.md",
    max_tokens: int = 1200,
    min_tokens: int = 50,
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
    tokenizer: str | TokenizerProtocol = "simple",
    parser: str | MarkdownParserProtocol = "default",
    document_metadata: dict[str, object] | None = None,
) -> list[Chunk]:
    """Split markdown text into semantic chunks."""
    tokenizer_impl = _resolve_tokenizer(tokenizer)
    document = _parse_markdown(
        text,
        document_title=document_title,
        parser=parser,
        document_metadata=document_metadata,
    )
    splitter = MarkdownSplitter(
        tokenizer=tokenizer_impl,
        options=SplitOptions(
            max_tokens=max_tokens,
            min_tokens=min_tokens,
            overlap_tokens=overlap_tokens,
            retain_headings=retain_headings,
            include_common_headings=include_common_headings,
            merge_small_chunks=merge_small_chunks,
            isolate_front_matter=isolate_front_matter,
            split_oversized_blocks=frozenset(split_oversized_blocks),
        ),
    )
    return splitter.split(document)


def _resolve_tokenizer(tokenizer: str | TokenizerProtocol) -> TokenizerProtocol:
    if isinstance(tokenizer, str):
        return create_tokenizer(tokenizer)
    return tokenizer


def _resolve_parser(parser: str | MarkdownParserProtocol) -> MarkdownParserProtocol:
    if isinstance(parser, str):
        return create_parser(parser)
    return parser


__all__ = ["lumber"]

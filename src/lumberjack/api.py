from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .core import MarkdownSplitter, create_parser, create_tokenizer
from .models import Chunk, DocumentAST, SplitOptions

if TYPE_CHECKING:
    from .base.interfaces import MarkdownParserProtocol, TokenizerProtocol


def parse_markdown(
    text: str,
    *,
    document_title: str = "document.md",
    parser: str | MarkdownParserProtocol = "default",
    document_metadata: dict[str, object] | None = None,
) -> DocumentAST:
    """Parse markdown text into the internal AST."""
    parser_impl = _resolve_parser(parser)
    return parser_impl.parse(
        text,
        document_title=document_title,
        document_metadata=document_metadata,
    )


def split_markdown_text(
    text: str,
    *,
    document_title: str = "document.md",
    max_tokens: int = 1200,
    min_tokens: int = 50,
    overlap_tokens: int = 0,
    retain_headings: bool = True,
    merge_small_chunks: bool = True,
    tokenizer: str | TokenizerProtocol = "simple",
    parser: str | MarkdownParserProtocol = "default",
    document_metadata: dict[str, object] | None = None,
) -> list[Chunk]:
    """Split markdown text into semantic chunks."""
    tokenizer_impl = _resolve_tokenizer(tokenizer)
    document = parse_markdown(
        text,
        document_title=document_title,
        parser=parser,
        document_metadata=document_metadata,
    )
    splitter = MarkdownSplitter(tokenizer=tokenizer_impl)
    options = SplitOptions(
        max_tokens=max_tokens,
        min_tokens=min_tokens,
        overlap_tokens=overlap_tokens,
        retain_headings=retain_headings,
        merge_small_chunks=merge_small_chunks,
    )
    return splitter.split(document, options)


def split_markdown_file(
    path: str | Path,
    *,
    max_tokens: int = 1200,
    min_tokens: int = 50,
    overlap_tokens: int = 0,
    retain_headings: bool = True,
    merge_small_chunks: bool = True,
    tokenizer: str | TokenizerProtocol = "simple",
    parser: str | MarkdownParserProtocol = "default",
) -> list[Chunk]:
    """Read a markdown file from disk and split it into semantic chunks."""
    input_path = Path(path)
    text = input_path.read_text(encoding="utf-8")
    return split_markdown_text(
        text,
        document_title=input_path.name,
        max_tokens=max_tokens,
        min_tokens=min_tokens,
        overlap_tokens=overlap_tokens,
        retain_headings=retain_headings,
        merge_small_chunks=merge_small_chunks,
        tokenizer=tokenizer,
        parser=parser,
        document_metadata={"path": str(input_path.resolve())},
    )


def _resolve_tokenizer(tokenizer: str | TokenizerProtocol) -> TokenizerProtocol:
    if isinstance(tokenizer, str):
        return create_tokenizer(tokenizer)
    return tokenizer


def _resolve_parser(parser: str | MarkdownParserProtocol) -> MarkdownParserProtocol:
    if isinstance(parser, str):
        return create_parser(parser)
    return parser

"""Format-specific parsers: raw input (Markdown / DOCX / HTML) -> DocumentAST.

Each subpackage wraps one input format and produces the shared
:class:`lumberjack.core.models.DocumentAST`, so every splitter works with
any of them.
"""

from __future__ import annotations

from typing import Literal, overload

from ..protocols import ParserProtocol
from .docx import DocxParser
from .html import HTMLParser
from .markdown import MarkdownItParser, MarkdownParser

__all__ = [
    "DocxParser",
    "HTMLParser",
    "MarkdownItParser",
    "MarkdownParser",
    "create_parser",
]


@overload
def create_parser(format: Literal["markdown", "html"]) -> ParserProtocol[str]: ...


@overload
def create_parser(format: Literal["docx"]) -> ParserProtocol[bytes]: ...


@overload
def create_parser(format: str) -> ParserProtocol[str] | ParserProtocol[bytes]: ...


def create_parser(format: str) -> ParserProtocol[str] | ParserProtocol[bytes]:
    """Return the built-in parser for the resolved input format."""
    if format == "docx":
        return DocxParser()
    if format == "html":
        return HTMLParser()
    if format == "markdown":
        return MarkdownItParser()

    msg = f"Unsupported input format: {format}"
    raise ValueError(msg)

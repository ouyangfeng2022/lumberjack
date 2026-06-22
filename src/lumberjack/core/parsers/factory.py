from __future__ import annotations

from typing import Literal, overload

from ..protocols import ParserProtocol
from .markdown import MarkdownItParser


@overload
def create_parser(format: Literal["markdown", "html"]) -> ParserProtocol[str]: ...


@overload
def create_parser(format: Literal["docx"]) -> ParserProtocol[bytes]: ...


@overload
def create_parser(format: str) -> ParserProtocol[str] | ParserProtocol[bytes]: ...


def create_parser(format: str) -> ParserProtocol[str] | ParserProtocol[bytes]:
    """Return the built-in parser for the resolved input format."""
    if format == "docx":
        from .docx import DocxParser

        return DocxParser()
    if format == "html":
        from .html import HTMLParser

        return HTMLParser()
    if format == "markdown":
        return MarkdownItParser()

    msg = f"Unsupported input format: {format}"
    raise ValueError(msg)

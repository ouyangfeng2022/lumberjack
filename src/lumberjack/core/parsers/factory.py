from __future__ import annotations

from typing import TYPE_CHECKING

from .markdown import MarkdownItParser

if TYPE_CHECKING:
    from ..protocols import ParserProtocol


def create_parser(
    format: str,
    parser: ParserProtocol[str] | ParserProtocol[bytes] | None = None,
) -> ParserProtocol[str] | ParserProtocol[bytes]:
    """Return a parser for the resolved input format, honoring explicit parser overrides."""
    if parser is not None:
        return parser

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

"""Public parsers and automatic parser selection."""

from .auto import AutoParser, InputFormat
from .docx import DocxParser
from .html import HTMLParser
from .markdown import (
    MarkdownBlockContext,
    MarkdownBlockHandler,
    MarkdownBlockSpec,
    MarkdownItParser,
    MarkdownParser,
)

__all__ = [
    "AutoParser",
    "DocxParser",
    "HTMLParser",
    "InputFormat",
    "MarkdownBlockContext",
    "MarkdownBlockHandler",
    "MarkdownBlockSpec",
    "MarkdownItParser",
    "MarkdownParser",
]

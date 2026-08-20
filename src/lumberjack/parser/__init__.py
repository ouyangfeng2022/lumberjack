"""Public parsers and automatic parser selection."""

from .auto import AutoParser, InputFormat
from .builder import DocTreeBuilder
from .docx import DocxParser
from .flat import DelimitedTextParser, JSONLinesParser, LogParser, TextParser
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
    "DelimitedTextParser",
    "DocTreeBuilder",
    "DocxParser",
    "HTMLParser",
    "InputFormat",
    "JSONLinesParser",
    "LogParser",
    "MarkdownBlockContext",
    "MarkdownBlockHandler",
    "MarkdownBlockSpec",
    "MarkdownItParser",
    "MarkdownParser",
    "TextParser",
]

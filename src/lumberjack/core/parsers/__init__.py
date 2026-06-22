"""Format-specific parsers: raw input (Markdown / DOCX / HTML) -> DocumentAST.

Each subpackage wraps one input format and produces the shared
:class:`lumberjack.core.models.DocumentAST`, so every splitter works with
any of them.
"""

from .docx import DocxParser
from .html import HTMLParser
from .markdown import MarkdownItParser, MarkdownParser

__all__ = [
    "DocxParser",
    "HTMLParser",
    "MarkdownItParser",
    "MarkdownParser",
]

"""Public fellers and automatic feller selection."""

from .auto import AutoFeller, InputFormat
from .docx import DocxFeller
from .html import HTMLFeller
from .markdown import (
    MarkdownBlockContext,
    MarkdownBlockHandler,
    MarkdownBlockSpec,
    MarkdownFeller,
    MarkdownItFeller,
)

__all__ = [
    "AutoFeller",
    "DocxFeller",
    "HTMLFeller",
    "InputFormat",
    "MarkdownBlockContext",
    "MarkdownBlockHandler",
    "MarkdownBlockSpec",
    "MarkdownFeller",
    "MarkdownItFeller",
]

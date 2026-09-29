"""Public parsers and automatic parser selection."""

from .auto import AutoParser, InputFormat
from .builder import DocTreeBuilder
from .code import NotebookParser, SourceCodeParser, SQLParser
from .docx import DocxParser
from .email import EmlParser, MboxParser, MsgParser
from .epub import EpubParser
from .html import HTMLParser
from .markdown import (
    MarkdownBlockContext,
    MarkdownBlockHandler,
    MarkdownBlockSpec,
    MarkdownItParser,
    MarkdownParser,
)
from .pdf import PdfParser
from .presentation import OdpParser, PptParser, PptxParser
from .records import (
    DelimitedTextParser,
    JSONLinesParser,
    JSONParser,
    LogParser,
    TextParser,
    TOMLParser,
    XMLParser,
    YAMLParser,
)
from .sqlite import SQLiteParser
from .xlsx import XlsxParser

__all__ = [
    "AutoParser",
    "DelimitedTextParser",
    "DocTreeBuilder",
    "DocxParser",
    "EmlParser",
    "EpubParser",
    "HTMLParser",
    "InputFormat",
    "JSONLinesParser",
    "JSONParser",
    "LogParser",
    "MarkdownBlockContext",
    "MarkdownBlockHandler",
    "MarkdownBlockSpec",
    "MarkdownItParser",
    "MarkdownParser",
    "MboxParser",
    "MsgParser",
    "NotebookParser",
    "OdpParser",
    "PdfParser",
    "PptParser",
    "PptxParser",
    "SQLParser",
    "SQLiteParser",
    "SourceCodeParser",
    "TOMLParser",
    "TextParser",
    "XMLParser",
    "XlsxParser",
    "YAMLParser",
]

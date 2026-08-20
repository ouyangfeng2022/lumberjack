"""Public document parsers and automatic format selection."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile

from ..models import DocTree, Document, InputFormat
from .code import NotebookParser, SourceCodeParser, SQLParser
from .docx import DocxParser
from .html import HTMLParser
from .markdown import MarkdownParser
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

DetectedFormat = Literal[
    "markdown",
    "html",
    "docx",
    "text",
    "log",
    "csv",
    "tsv",
    "json",
    "jsonl",
    "xml",
    "yaml",
    "xlsx",
    "toml",
    "sqlite",
    "sql",
    "python",
    "javascript",
    "typescript",
    "notebook",
]
_VALID_FORMATS = frozenset(
    {
        "auto",
        "markdown",
        "html",
        "docx",
        "text",
        "log",
        "csv",
        "tsv",
        "json",
        "jsonl",
        "xml",
        "yaml",
        "xlsx",
        "toml",
        "sqlite",
        "sql",
        "python",
        "javascript",
        "typescript",
        "notebook",
    }
)
_HTML_START_RE = re.compile(
    r"^\s*(?:<!doctype\s+html\b|<(?:html|head|body|main|article|section|div|"
    r"h[1-6]|p|table|ul|ol|blockquote|pre)\b)",
    re.IGNORECASE,
)


def _format_from_suffix(path: str | Path | None) -> DetectedFormat | None:
    if path is None:
        return None
    suffix = Path(path).suffix.lower()
    if suffix == ".docx":
        return "docx"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".txt", ".text"}:
        return "text"
    if suffix == ".log":
        return "log"
    if suffix == ".csv":
        return "csv"
    if suffix == ".tsv":
        return "tsv"
    if suffix in {".jsonl", ".ndjson"}:
        return "jsonl"
    if suffix == ".json":
        return "json"
    if suffix == ".xml":
        return "xml"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".xlsx":
        return "xlsx"
    if suffix == ".toml":
        return "toml"
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        return "sqlite"
    if suffix == ".sql":
        return "sql"
    if suffix == ".py":
        return "python"
    if suffix in {".js", ".mjs", ".cjs"}:
        return "javascript"
    if suffix in {".ts", ".tsx"}:
        return "typescript"
    if suffix == ".ipynb":
        return "notebook"
    return None


def _is_docx(data: bytes) -> bool:
    if not data.startswith(b"PK"):
        return False
    try:
        with ZipFile(BytesIO(data)) as archive:
            names = frozenset(archive.namelist())
    except BadZipFile:
        return False
    return "[Content_Types].xml" in names and "word/document.xml" in names


class AutoParser:
    """Select a built-in parser from document provenance or content."""

    block_kinds = frozenset()

    def parse(
        self,
        document: Document | str | bytes | Path,
        *,
        format: InputFormat = "auto",
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        if not isinstance(document, Document):
            document = Document(
                source=document,
                format=format,
                document_title=document_title,
                metadata_overrides=dict(metadata_overrides or {}),
                source_path=source_path,
            )
        source = document.source
        source_path = document.source_path
        if document.format not in _VALID_FORMATS:
            raise ValueError(f"Unsupported input format: {document.format}")
        resolved_source_path = Path(source) if isinstance(source, Path) else source_path
        data = source.read_bytes() if isinstance(source, Path) else source
        format = self._detect_format(data, resolved_source_path, document.format)
        normalized_path = (
            str(resolved_source_path) if resolved_source_path is not None else None
        )
        parsed_tree = Document(
            source=data,
            format=format,
            document_title=document.document_title,
            metadata_overrides=dict(document.metadata_overrides),
            source_path=normalized_path,
        )

        if format == "docx":
            if isinstance(data, str):
                raise TypeError("DOCX input must be bytes or a pathlib.Path")
            return DocxParser().parse(parsed_tree)

        if format == "xlsx":
            if isinstance(data, str):
                raise TypeError("XLSX input must be bytes or a pathlib.Path")
            return XlsxParser().parse(parsed_tree)

        if format == "sqlite":
            if isinstance(data, str):
                raise TypeError("SQLite input must be bytes or a pathlib.Path")
            return SQLiteParser().parse(parsed_tree)

        if isinstance(data, bytes):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    "Non-DOCX bytes must contain valid UTF-8 text"
                ) from exc
        else:
            text = data
        parser = {
            "html": HTMLParser(),
            "markdown": MarkdownParser(),
            "text": TextParser(),
            "log": LogParser(),
            "csv": DelimitedTextParser(delimiter=","),
            "tsv": DelimitedTextParser(delimiter="\t"),
            "json": JSONParser(),
            "jsonl": JSONLinesParser(),
            "xml": XMLParser(),
            "yaml": YAMLParser(),
            "toml": TOMLParser(),
            "sql": SQLParser(),
            "python": SourceCodeParser(language="python"),
            "javascript": SourceCodeParser(language="javascript"),
            "typescript": SourceCodeParser(language="typescript"),
            "notebook": NotebookParser(),
        }[format]
        return parser.parse(
            Document(
                source=text,
                format=format,
                document_title=document.document_title,
                metadata_overrides=dict(document.metadata_overrides),
                source_path=normalized_path,
            )
        )

    def _detect_format(
        self,
        data: str | bytes,
        source_path: str | Path | None,
        requested_format: InputFormat,
    ) -> DetectedFormat:
        if requested_format != "auto":
            return requested_format
        suffix_format = _format_from_suffix(source_path)
        if suffix_format is not None:
            return suffix_format
        if isinstance(data, bytes) and _is_docx(data):
            return "docx"
        if isinstance(data, bytes):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    "Unable to infer format from non-DOCX binary input"
                ) from exc
        else:
            text = data
        return "html" if _HTML_START_RE.match(text) else "markdown"


__all__ = ["AutoParser", "InputFormat"]

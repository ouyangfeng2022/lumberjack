"""Public document fellers and automatic format selection."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile

from ..models import InputFormat, Log, Tree
from .docx import DocxFeller
from .html import HTMLFeller
from .markdown import MarkdownFeller

DetectedFormat = Literal["markdown", "html", "docx"]
_VALID_FORMATS = frozenset({"auto", "markdown", "html", "docx"})
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


class AutoFeller:
    """Select a built-in feller from tree provenance or content."""

    block_kinds = frozenset()

    def fell(
        self,
        tree: Tree | str | bytes | Path,
        *,
        format: InputFormat = "auto",
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> Log:
        if not isinstance(tree, Tree):
            tree = Tree(
                source=tree,
                format=format,
                document_title=document_title,
                metadata_overrides=dict(metadata_overrides or {}),
                source_path=source_path,
            )
        source = tree.source
        source_path = tree.source_path
        if tree.format not in _VALID_FORMATS:
            raise ValueError(f"Unsupported input format: {tree.format}")
        resolved_source_path = Path(source) if isinstance(source, Path) else source_path
        data = source.read_bytes() if isinstance(source, Path) else source
        format = self._detect_format(data, resolved_source_path, tree.format)
        normalized_path = (
            str(resolved_source_path) if resolved_source_path is not None else None
        )
        felled_tree = Tree(
            source=data,
            format=format,
            document_title=tree.document_title,
            metadata_overrides=dict(tree.metadata_overrides),
            source_path=normalized_path,
        )

        if format == "docx":
            if isinstance(data, str):
                raise TypeError("DOCX input must be bytes or a pathlib.Path")
            return DocxFeller().fell(felled_tree)

        if isinstance(data, bytes):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    "Non-DOCX bytes must contain valid UTF-8 Markdown or HTML text"
                ) from exc
        else:
            text = data
        feller = HTMLFeller() if format == "html" else MarkdownFeller()
        return feller.fell(
            Tree(
                source=text,
                format=format,
                document_title=tree.document_title,
                metadata_overrides=dict(tree.metadata_overrides),
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


__all__ = ["AutoFeller", "InputFormat"]

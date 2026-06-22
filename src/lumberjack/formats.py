from __future__ import annotations

from pathlib import Path

InputFormat = str
SUPPORTED_FORMATS = frozenset({"auto", "markdown", "html", "docx"})
TEXT_FORMATS = frozenset({"markdown", "html"})


def detect_format(source: str | bytes | Path, format: str) -> str:
    """Resolve the input format from an explicit hint and source shape."""
    if format not in SUPPORTED_FORMATS:
        msg = f"Unsupported input format: {format}"
        raise ValueError(msg)

    if format != "auto":
        return format

    if isinstance(source, bytes):
        return "docx"

    if isinstance(source, Path):
        return detect_format_from_filename(source.name)

    return "markdown"


def detect_format_from_filename(filename: str) -> str:
    """Detect an input format from a filename extension."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return "docx"
    if suffix in {".html", ".htm"}:
        return "html"
    return "markdown"


def read_text_input(source: str | bytes | Path) -> str:
    """Read Markdown or HTML text from any supported source shape."""
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8")
    if isinstance(source, bytes):
        return source.decode("utf-8")
    return source


def read_docx_input(source: str | bytes | Path) -> bytes:
    """Read DOCX binary content from any supported source shape."""
    if isinstance(source, Path):
        return source.read_bytes()
    if isinstance(source, str):
        raise TypeError(
            "Expected bytes or a .docx file path for DOCX format, got a text string. "
            "Pass a Path or bytes instead."
        )
    return source

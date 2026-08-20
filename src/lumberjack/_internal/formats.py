from __future__ import annotations

from pathlib import Path

SUPPORTED_FORMATS = frozenset(
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
TEXT_FORMATS = frozenset(
    {"markdown", "html", "text", "log", "csv", "tsv", "json", "jsonl", "xml", "yaml"}
)


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
    if suffix in {".txt", ".text"}:
        return "text"
    return "markdown"


def read_text_input(source: str | bytes | Path) -> str:
    """Read a UTF-8 textual input from any supported source shape."""
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

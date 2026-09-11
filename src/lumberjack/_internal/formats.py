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
        "bash",
        "c",
        "cpp",
        "csharp",
        "go",
        "java",
        "kotlin",
        "lua",
        "php",
        "ruby",
        "rust",
        "swift",
        "zig",
        "notebook",
    }
)
TEXT_FORMATS = frozenset(
    {
        "markdown",
        "html",
        "text",
        "log",
        "csv",
        "tsv",
        "json",
        "jsonl",
        "xml",
        "yaml",
        "toml",
        "sql",
        "python",
        "javascript",
        "typescript",
        "bash",
        "c",
        "cpp",
        "csharp",
        "go",
        "java",
        "kotlin",
        "lua",
        "php",
        "ruby",
        "rust",
        "swift",
        "zig",
        "notebook",
    }
)


def detect_format(source: str | bytes | Path, format: str) -> str:
    """Resolve the input format from an explicit hint and source shape."""
    if format not in SUPPORTED_FORMATS:
        msg = f"Unsupported input format: {format}"
        raise ValueError(msg)

    if format != "auto":
        return format

    if isinstance(source, bytes):
        if source.startswith(b"SQLite format 3\x00"):
            return "sqlite"
        if source.startswith(b"PK\x03\x04") and b"xl/" in source[:2000]:
            return "xlsx"
        return "docx"

    if isinstance(source, Path):
        return detect_format_from_filename(source.name)

    return "markdown"


_SUFFIX_FORMATS: dict[str, str] = {
    ".docx": "docx",
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".text": "text",
    ".log": "log",
    ".csv": "csv",
    ".tsv": "tsv",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".json": "json",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xlsx": "xlsx",
    ".toml": "toml",
    ".sqlite": "sqlite",
    ".sqlite3": "sqlite",
    ".db": "sqlite",
    ".sql": "sql",
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".sh": "bash",
    ".bash": "bash",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".lua": "lua",
    ".php": "php",
    ".rb": "ruby",
    ".rs": "rust",
    ".swift": "swift",
    ".zig": "zig",
    ".ipynb": "notebook",
}


def has_known_suffix(filename: str) -> bool:
    """True when the filename's suffix maps to a supported input format."""
    return Path(filename).suffix.lower() in _SUFFIX_FORMATS


def detect_format_from_filename(filename: str) -> str:
    """Detect an input format from a filename extension.

    Unknown suffixes fall back to ``markdown`` so a bare or oddly named text
    file still parses; use :func:`has_known_suffix` to distinguish them.
    """
    return _SUFFIX_FORMATS.get(Path(filename).suffix.lower(), "markdown")


def read_text_input(source: str | bytes | Path) -> str:
    """Read a UTF-8 textual input from any supported source shape."""
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8-sig")
    if isinstance(source, bytes):
        return source.decode("utf-8-sig")
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

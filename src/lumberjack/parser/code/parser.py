"""Standard-library parsers for SQL, source code, and Jupyter notebooks."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import ClassVar

from ...models import DocTree, Document, InputFormat, SourceLocation
from ..builder import DocTreeBuilder
from .tree_sitter import CodeLanguage, extract_top_level_symbols


def _document(
    value: Document | str,
    *,
    format: InputFormat,
    document_title: str | None = None,
    metadata_overrides: dict[str, object] | None = None,
    source_path: str | Path | None = None,
) -> Document:
    return (
        value
        if isinstance(value, Document)
        else Document(
            value,
            format=format,
            document_title=document_title,
            metadata_overrides=dict(metadata_overrides or {}),
            source_path=source_path,
        )
    )  # type: ignore[arg-type]


def _text(document: Document) -> str:
    if not isinstance(document.source, str):
        raise TypeError(f"{document.format} input must be UTF-8 text")
    return document.source


def _builder(document: Document) -> DocTreeBuilder:
    title = document.document_title or (
        Path(document.source_path).stem
        if document.source_path is not None
        else "Anonymous"
    )
    return DocTreeBuilder(
        title=title or "Anonymous",
        source=_text(document),
        source_path=document.source_path,
        metadata=document.metadata_overrides,
        block_kinds={"record"},
        topology="records",
    )


class SQLParser:
    """Parse semicolon-delimited SQL statements as ordered atomic records."""

    block_kinds: ClassVar[frozenset[str]] = frozenset({"record"})

    def parse(
        self,
        document: Document | str,
        *,
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        source_document = _document(
            document,
            format="sql",
            document_title=document_title,
            metadata_overrides=metadata_overrides,
            source_path=source_path,
        )
        builder = _builder(source_document)
        start_line = 1
        for index, statement in enumerate(_text(source_document).split(";")):
            normalized = statement.strip()
            statement_lines = statement.count("\n") + 1
            if normalized:
                builder.add_record(
                    normalized + ";",
                    locations=(
                        SourceLocation(
                            source=str(source_document.source_path)
                            if source_document.source_path
                            else None,
                            line_start=start_line,
                            line_end=start_line + statement_lines - 1,
                            element_id=f"statement:{index}",
                        ),
                    ),
                    attrs={"statement_index": index},
                )
            start_line += statement_lines
        return builder.build()


_SYMBOL_RE = re.compile(
    r"^(?:export\s+)?(?:async\s+)?(?:class|function|interface|type|const|let|var)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


class SourceCodeParser:
    """Parse source files into symbol-aware records without treating code as prose.

    When the ``code-parsing`` extra is installed, Tree-sitter selects top-level
    declarations and retains valid results from malformed source. Otherwise,
    Python uses ``ast`` and JavaScript/TypeScript use the built-in fallback.
    """

    block_kinds: ClassVar[frozenset[str]] = frozenset({"record"})

    def __init__(self, *, language: CodeLanguage) -> None:
        self.language = language

    def parse(
        self,
        document: Document | str,
        *,
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        source_document = _document(
            document,
            format=self.language,
            document_title=document_title,
            metadata_overrides=metadata_overrides,
            source_path=source_path,
        )
        source = _text(source_document)
        builder = _builder(source_document)
        syntax_symbols = extract_top_level_symbols(source, self.language)
        if syntax_symbols is not None:
            for index, symbol in enumerate(syntax_symbols):
                builder.add_record(
                    symbol.text,
                    locations=(
                        SourceLocation(
                            source=str(source_document.source_path)
                            if source_document.source_path
                            else None,
                            byte_start=symbol.start_byte,
                            byte_end=symbol.end_byte,
                            line_start=symbol.line_start,
                            line_end=symbol.line_end,
                            element_id=f"symbol:{symbol.name}",
                        ),
                    ),
                    attrs={
                        "symbol": symbol.name,
                        "symbol_type": symbol.kind,
                        "language": self.language,
                        "symbol_index": index,
                        "syntax_parser": "tree-sitter",
                        "has_syntax_error": symbol.has_syntax_error,
                    },
                )
        elif self.language == "python":
            try:
                tree = ast.parse(source)
            except SyntaxError as exc:
                raise ValueError(
                    f"Invalid Python source: {exc.msg} at line {exc.lineno}"
                ) from exc
            lines = source.splitlines()
            symbols = [
                node
                for node in tree.body
                if isinstance(
                    node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
                )
            ]
            for index, node in enumerate(symbols):
                start = node.lineno
                end = getattr(node, "end_lineno", start)
                builder.add_record(
                    "\n".join(lines[start - 1 : end]),
                    locations=(
                        SourceLocation(
                            source=str(source_document.source_path)
                            if source_document.source_path
                            else None,
                            line_start=start,
                            line_end=end,
                            element_id=f"symbol:{node.name}",
                        ),
                    ),
                    attrs={
                        "symbol": node.name,
                        "symbol_type": type(node).__name__,
                        "language": self.language,
                        "symbol_index": index,
                    },
                )
        else:
            matches = list(_SYMBOL_RE.finditer(source))
            lines = source.splitlines()
            for index, match in enumerate(matches):
                start = source[: match.start()].count("\n") + 1
                end = (
                    source[: matches[index + 1].start()].count("\n")
                    if index + 1 < len(matches)
                    else len(lines)
                )
                builder.add_record(
                    "\n".join(lines[start - 1 : end]),
                    locations=(
                        SourceLocation(
                            source=str(source_document.source_path)
                            if source_document.source_path
                            else None,
                            line_start=start,
                            line_end=end,
                            element_id=f"symbol:{match.group(1)}",
                        ),
                    ),
                    attrs={
                        "symbol": match.group(1),
                        "language": self.language,
                        "symbol_index": index,
                    },
                )
        if not builder.current_section.blocks and source:
            builder.add_record(
                source,
                locations=(
                    SourceLocation(
                        source=str(source_document.source_path)
                        if source_document.source_path
                        else None,
                        line_start=1,
                        line_end=max(1, source.count("\n") + 1),
                        element_id="module",
                    ),
                ),
                attrs={"language": self.language},
            )
        return builder.build()


class NotebookParser:
    """Parse Jupyter cells as ordered, language-aware atomic records."""

    block_kinds: ClassVar[frozenset[str]] = frozenset({"record"})

    def parse(
        self,
        document: Document | str,
        *,
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        source_document = _document(
            document,
            format="notebook",
            document_title=document_title,
            metadata_overrides=metadata_overrides,
            source_path=source_path,
        )
        try:
            notebook = json.loads(_text(source_document))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid notebook JSON: {exc.msg}") from exc
        if not isinstance(notebook, dict) or not isinstance(
            notebook.get("cells"), list
        ):
            raise ValueError("Invalid notebook: expected a cells array")
        language = notebook.get("metadata", {}).get("kernelspec", {}).get("language")
        builder = _builder(source_document)
        for index, cell in enumerate(notebook["cells"]):
            if not isinstance(cell, dict):
                continue
            source = cell.get("source", [])
            text = "".join(source) if isinstance(source, list) else str(source)
            if not text:
                continue
            builder.add_record(
                text,
                locations=(
                    SourceLocation(
                        source=str(source_document.source_path)
                        if source_document.source_path
                        else None,
                        json_path=f'$["cells"][{index}]',
                        element_id=f"cell:{index}",
                    ),
                ),
                attrs={
                    "cell_index": index,
                    "cell_type": cell.get("cell_type"),
                    "language": language,
                },
            )
        return builder.build()


__all__ = ["NotebookParser", "SQLParser", "SourceCodeParser"]

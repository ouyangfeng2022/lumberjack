"""Parsers for UTF-8 text and flat record formats without synthetic headings."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar, Literal

from ..models import DocTree, Document, InputFormat, SourceLocation
from .builder import DocTreeBuilder


def _document(
    value: Document | str,
    *,
    format: InputFormat,
    document_title: str | None = None,
    metadata_overrides: dict[str, object] | None = None,
    source_path: str | Path | None = None,
) -> Document:
    if isinstance(value, Document):
        return value
    return Document(
        value,
        format=format,
        document_title=document_title,
        metadata_overrides=dict(metadata_overrides or {}),
        source_path=source_path,
    )


def _text(document: Document) -> str:
    if not isinstance(document.source, str):
        raise TypeError(f"{document.format} input must be UTF-8 text")
    return document.source


def _source_path(document: Document) -> str | None:
    return str(document.source_path) if document.source_path is not None else None


def _title(document: Document) -> str:
    if document.document_title:
        return document.document_title
    if document.source_path is not None:
        return Path(document.source_path).stem or "Anonymous"
    return "Anonymous"


def _builder(
    document: Document,
    *,
    topology: Literal["hierarchical", "records"],
    kinds: Iterable[str],
) -> DocTreeBuilder:
    return DocTreeBuilder(
        title=_title(document),
        source=_text(document),
        source_path=_source_path(document),
        metadata=document.metadata_overrides,
        block_kinds=kinds,
        topology=topology,
    )


class TextParser:
    """Parse plain text as root-level paragraph or line blocks."""

    default_block_kinds: ClassVar[frozenset[str]] = frozenset({"paragraph"})

    def __init__(self, *, boundary: Literal["paragraph", "line"] = "paragraph") -> None:
        self.boundary = boundary

    @property
    def block_kinds(self) -> frozenset[str]:
        return self.default_block_kinds

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
            format="text",
            document_title=document_title,
            metadata_overrides=dict(metadata_overrides or {}),
            source_path=source_path,
        )
        builder = _builder(
            source_document, topology="hierarchical", kinds=self.block_kinds
        )
        lines = _text(source_document).splitlines()
        if self.boundary == "line":
            for number, line in enumerate(lines, start=1):
                if line:
                    builder.add_block(
                        "paragraph",
                        line,
                        locations=(
                            SourceLocation(
                                source=_source_path(source_document),
                                line_start=number,
                                line_end=number,
                            ),
                        ),
                    )
            return builder.build()

        paragraph: list[str] = []
        start_line: int | None = None
        for number, line in enumerate(lines, start=1):
            if line.strip():
                if start_line is None:
                    start_line = number
                paragraph.append(line)
                continue
            if paragraph:
                builder.add_block(
                    "paragraph",
                    "\n".join(paragraph),
                    locations=(
                        SourceLocation(
                            source=_source_path(source_document),
                            line_start=start_line,
                            line_end=number - 1,
                        ),
                    ),
                )
                paragraph = []
                start_line = None
        if paragraph:
            builder.add_block(
                "paragraph",
                "\n".join(paragraph),
                locations=(
                    SourceLocation(
                        source=_source_path(source_document),
                        line_start=start_line,
                        line_end=len(lines),
                    ),
                ),
            )
        return builder.build()


class LogParser:
    """Parse each non-empty log line as one atomic, ordered record."""

    default_block_kinds: ClassVar[frozenset[str]] = frozenset({"record"})

    @property
    def block_kinds(self) -> frozenset[str]:
        return self.default_block_kinds

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
            format="log",
            document_title=document_title,
            metadata_overrides=metadata_overrides,
            source_path=source_path,
        )
        builder = _builder(source_document, topology="records", kinds=self.block_kinds)
        for number, line in enumerate(_text(source_document).splitlines(), start=1):
            if line:
                builder.add_record(
                    line,
                    locations=(
                        SourceLocation(
                            source=_source_path(source_document),
                            line_start=number,
                            line_end=number,
                            element_id=f"line:{number}",
                        ),
                    ),
                    attrs={"line": number},
                )
        return builder.build()


class DelimitedTextParser:
    """Parse CSV or TSV as atomic rows, keeping header schema in row metadata."""

    default_block_kinds: ClassVar[frozenset[str]] = frozenset({"tabular_row"})

    def __init__(self, *, delimiter: Literal[",", "\t"] = ",") -> None:
        self.delimiter = delimiter

    @property
    def block_kinds(self) -> frozenset[str]:
        return self.default_block_kinds

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
            format="csv",
            document_title=document_title,
            metadata_overrides=metadata_overrides,
            source_path=source_path,
        )
        reader = csv.reader(
            _text(source_document).splitlines(), delimiter=self.delimiter
        )
        try:
            header = next(reader)
        except StopIteration:
            header = []
        normalized_header = tuple(
            name.strip() or f"column_{index}"
            for index, name in enumerate(header, start=1)
        )
        builder = _builder(source_document, topology="records", kinds=self.block_kinds)
        for row_number, row in enumerate(reader, start=2):
            values = tuple(row)
            fields = tuple(
                f"{name}: {value}"
                for name, value in zip(normalized_header, values, strict=False)
            )
            if len(values) > len(normalized_header):
                fields += tuple(
                    f"column_{index}: {value}"
                    for index, value in enumerate(
                        values[len(normalized_header) :],
                        start=len(normalized_header) + 1,
                    )
                )
            builder.add_record(
                "\n".join(fields),
                kind="tabular_row",
                locations=(
                    SourceLocation(
                        source=_source_path(source_document),
                        row_start=row_number,
                        row_end=row_number,
                        column_start=1,
                        column_end=max(1, len(values)),
                    ),
                ),
                attrs={
                    "header": normalized_header,
                    "values": values,
                    "delimiter": self.delimiter,
                },
            )
        return builder.build()


class JSONLinesParser:
    """Parse JSON Lines as one canonical JSON value per atomic record."""

    default_block_kinds: ClassVar[frozenset[str]] = frozenset({"record"})

    @property
    def block_kinds(self) -> frozenset[str]:
        return self.default_block_kinds

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
            format="jsonl",
            document_title=document_title,
            metadata_overrides=metadata_overrides,
            source_path=source_path,
        )
        builder = _builder(source_document, topology="records", kinds=self.block_kinds)
        record_index = 0
        for line_number, line in enumerate(
            _text(source_document).splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL record at line {line_number}: {exc.msg}"
                ) from exc
            builder.add_record(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(", ", ": "),
                ),
                locations=(
                    SourceLocation(
                        source=_source_path(source_document),
                        line_start=line_number,
                        line_end=line_number,
                        json_path=f"$[{record_index}]",
                    ),
                ),
                attrs={"record_index": record_index},
            )
            record_index += 1
        return builder.build()


__all__ = ["DelimitedTextParser", "JSONLinesParser", "LogParser", "TextParser"]

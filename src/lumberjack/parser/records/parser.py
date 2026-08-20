"""Parsers for UTF-8 text and flat record formats without synthetic headings."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from importlib import import_module
from pathlib import Path
from typing import ClassVar, Literal
from xml.etree import ElementTree

import yaml

from ...models import DocTree, Document, InputFormat, SourceLocation
from ..builder import DocTreeBuilder


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


def _json_path(path: str, key: object) -> str:
    return f"{path}[{json.dumps(str(key), ensure_ascii=False)}]"


def _scalar_records(value: object, path: str = "$") -> Iterable[tuple[str, object]]:
    if isinstance(value, Mapping):
        if not value:
            yield path, value
        for key, child in value.items():
            yield from _scalar_records(child, _json_path(path, key))
        return
    if isinstance(value, list):
        if not value:
            yield path, value
        for index, child in enumerate(value):
            yield from _scalar_records(child, f"{path}[{index}]")
        return
    yield path, value


def _value_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


class _StructuredDataParser:
    """Base parser that emits scalar values as ordered, path-aware records."""

    format: ClassVar[Literal["json", "toml", "yaml"]]
    default_block_kinds: ClassVar[frozenset[str]] = frozenset({"record"})

    @property
    def block_kinds(self) -> frozenset[str]:
        return self.default_block_kinds

    def load(self, source: str) -> object:
        raise NotImplementedError

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
            format=self.format,
            document_title=document_title,
            metadata_overrides=metadata_overrides,
            source_path=source_path,
        )
        try:
            value = self.load(_text(source_document))
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise ValueError(f"Invalid {self.format.upper()} input: {exc}") from exc
        builder = _builder(source_document, topology="records", kinds=self.block_kinds)
        for index, (path, scalar) in enumerate(_scalar_records(value)):
            rendered = json.dumps(
                scalar,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
                separators=(", ", ": "),
            )
            builder.add_record(
                f"{path}: {rendered}",
                locations=(
                    SourceLocation(
                        source=_source_path(source_document),
                        json_path=path,
                    ),
                ),
                attrs={
                    "record_index": index,
                    "path": path,
                    "value": scalar,
                    "value_type": _value_type(scalar),
                },
            )
        return builder.build()


class JSONParser(_StructuredDataParser):
    """Parse JSON into scalar records with JSON-path provenance."""

    format: ClassVar[Literal["json"]] = "json"

    def load(self, source: str) -> object:
        return json.loads(source)


class YAMLParser(_StructuredDataParser):
    """Parse YAML into scalar records with key-path provenance."""

    format: ClassVar[Literal["yaml"]] = "yaml"

    def load(self, source: str) -> object:
        return yaml.safe_load(source)


class TOMLParser(_StructuredDataParser):
    """Parse TOML into scalar records with key-path provenance."""

    format: ClassVar[Literal["toml"]] = "toml"

    def load(self, source: str) -> object:
        try:
            tomllib = import_module("tomllib")
        except ModuleNotFoundError:
            try:
                tomllib = import_module("tomli")
            except ModuleNotFoundError as exc:
                raise ImportError(
                    "TOML support on Python 3.10 requires 'tomli'. "
                    "Install lumberjack-py[toml]."
                ) from exc
        return tomllib.loads(source)


def _tag_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


class XMLParser:
    """Parse XML leaf elements as ordered records with element-path provenance."""

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
            format="xml",
            document_title=document_title,
            metadata_overrides=metadata_overrides,
            source_path=source_path,
        )
        try:
            root = ElementTree.fromstring(_text(source_document))
        except ElementTree.ParseError as exc:
            raise ValueError(f"Invalid XML input: {exc}") from exc

        builder = _builder(source_document, topology="records", kinds=self.block_kinds)
        record_index = 0

        def visit(element: ElementTree.Element, path: str) -> None:
            nonlocal record_index
            children = list(element)
            if children:
                counts: dict[str, int] = {}
                for child in children:
                    name = _tag_name(child.tag)
                    counts[name] = counts.get(name, 0) + 1
                    visit(child, f"{path}/{name}[{counts[name]}]")
                return
            text = (element.text or "").strip()
            builder.add_record(
                f"{path}: {text}",
                locations=(
                    SourceLocation(
                        source=_source_path(source_document), element_id=path
                    ),
                ),
                attrs={
                    "record_index": record_index,
                    "path": path,
                    "tag": _tag_name(element.tag),
                    "attributes": dict(element.attrib),
                    "value_type": "string",
                },
            )
            record_index += 1

        visit(root, f"/{_tag_name(root.tag)}[1]")
        return builder.build()


__all__ = [
    "DelimitedTextParser",
    "JSONLinesParser",
    "JSONParser",
    "LogParser",
    "TOMLParser",
    "TextParser",
    "XMLParser",
    "YAMLParser",
]

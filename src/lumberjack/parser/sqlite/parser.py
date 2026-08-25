"""SQLite parser using the standard library with table/row provenance.

The connection is inspected with fixed SQL statements only; table names and
row values come from ``Connection.iterdump()`` text, which SQLite generates
with deterministic literal quoting, so document-supplied identifiers never
need to be interpolated into a query.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import ClassVar

from ...models import DocTree, Document, SourceLocation
from ..builder import DocTreeBuilder


def _parse_quoted_identifier(text: str, start: int) -> tuple[str, int]:
    """Parse a double-quoted identifier with ``""`` doubling.

    *start* points at the opening quote; returns the unescaped value and the
    index just past the closing quote.  Dump output quotes identifiers this
    way, so hostile names cannot break out of the identifier.
    """
    parts: list[str] = []
    index = start + 1
    while True:
        closing = text.find('"', index)
        if closing == -1:
            raise ValueError("unterminated quoted identifier in dump output")
        if closing + 1 < len(text) and text[closing + 1] == '"':
            parts.append(text[index : closing + 1])
            index = closing + 2
        else:
            parts.append(text[index:closing])
            return "".join(parts), closing + 1


def _column_name(definition: str) -> str:
    """First token of a column definition, honoring quoted identifiers."""
    stripped = definition.strip()
    if stripped.startswith('"'):
        value, _ = _parse_quoted_identifier(stripped, 0)
        return value
    return stripped.split(maxsplit=1)[0].split("(")[0].strip()


def _create_table_columns(line: str) -> tuple[str, list[str]] | None:
    """Return ``(table, column names)`` from a dump ``CREATE TABLE`` line.

    Dump output quotes identifiers only when needed, so the table name may
    be a bareword.  The column list is walked with quote/string/paren
    awareness so DEFAULT literals containing commas and types such as
    ``VARCHAR(10)`` do not break the split.
    """
    prefix = "CREATE TABLE "
    if not line.startswith(prefix):
        return None
    index = len(prefix)
    if line[index] == '"':
        table, index = _parse_quoted_identifier(line, index)
    else:
        open_paren = line.find("(", index)
        if open_paren == -1:
            raise ValueError("CREATE TABLE without column list in dump output")
        table = line[index:open_paren].strip()
        index = open_paren
    open_paren = line.find("(", index)
    if open_paren == -1:
        raise ValueError("CREATE TABLE without column list in dump output")
    depth = 0
    in_string = False
    names: list[str] = []
    segment_start = open_paren + 1
    index = open_paren + 1
    while index < len(line):
        char = line[index]
        if in_string:
            if char == "'":
                if index + 1 < len(line) and line[index + 1] == "'":
                    index += 2
                    continue
                in_string = False
        elif char == "'":
            in_string = True
        elif char == '"':
            _, index = _parse_quoted_identifier(line, index)
            index -= 1
        elif char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                names.append(_column_name(line[segment_start:index]))
                return table, names
            depth -= 1
        elif char == "," and depth == 0:
            names.append(_column_name(line[segment_start:index]))
            segment_start = index + 1
        index += 1
    raise ValueError("unterminated column list in dump output")


def _insert_values(line: str) -> tuple[str, tuple[object, ...]] | None:
    """Parse a dump ``INSERT INTO "table" VALUES(...);`` line.

    Values are SQL literals: ``''``-doubled strings, ``NULL``, ``X'..'``
    blobs, and numeric text.  Returns ``(table, values)`` or ``None`` for
    any other dump statement.
    """
    prefix = 'INSERT INTO "'
    if not line.startswith(prefix):
        return None
    table, index = _parse_quoted_identifier(line, len(prefix) - 1)
    if line.startswith(" VALUES(", index):
        index += len(" VALUES(")
    elif line.startswith(" DEFAULT VALUES;", index):
        return table, ()
    else:
        raise ValueError("unexpected INSERT shape in dump output")
    values: list[object] = []
    while True:
        char = line[index]
        if char == ")":
            if line[index : index + 2] == ");":
                return table, tuple(values)
            raise ValueError("malformed VALUES list in dump output")
        if char == "'":
            parts: list[str] = []
            index += 1
            while True:
                closing = line.find("'", index)
                if closing == -1:
                    raise ValueError("unterminated string in dump output")
                if closing + 1 < len(line) and line[closing + 1] == "'":
                    parts.append(line[index : closing + 1])
                    index = closing + 2
                else:
                    parts.append(line[index:closing])
                    index = closing + 1
                    break
            values.append("".join(parts))
        elif line.startswith("NULL", index):
            values.append(None)
            index += 4
        elif char in "xX" and index + 1 < len(line) and line[index + 1] == "'":
            closing = line.find("'", index + 2)
            if closing == -1:
                raise ValueError("unterminated blob in dump output")
            values.append(bytes.fromhex(line[index + 2 : closing]))
            index = closing + 1
        else:
            end = index
            while end < len(line) and line[end] not in ",)":
                end += 1
            values.append(line[index:end])
            index = end
        if line[index] == ",":
            index += 1
            continue
        if line[index] != ")":
            raise ValueError("malformed VALUES list in dump output")
        # otherwise the top of the loop handles the closing ");"


class SQLiteParser:
    """Parse SQLite table rows as atomic records.

    Byte inputs require Python 3.11's ``sqlite3.Connection.deserialize``;
    callers on older Python versions should pass a temporary extraction through
    an application-specific adapter instead of mutating the input database.
    """

    default_block_kinds: ClassVar[frozenset[str]] = frozenset({"tabular_row"})

    @property
    def block_kinds(self) -> frozenset[str]:
        return self.default_block_kinds

    def parse(
        self,
        document: Document | bytes,
        *,
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        if not isinstance(document, Document):
            document = Document(
                document,
                format="sqlite",
                document_title=document_title,
                metadata_overrides=dict(metadata_overrides or {}),
                source_path=source_path,
            )
        if not isinstance(document.source, bytes | bytearray):
            raise TypeError("SQLiteParser.parse expects Document[bytes]")
        connection = sqlite3.connect(":memory:")
        try:
            deserialize = getattr(connection, "deserialize", None)
            if deserialize is None:
                raise ImportError("SQLite byte parsing requires Python 3.11 or later")
            deserialize(bytes(document.source))
            title = document.document_title or (
                Path(document.source_path).stem if document.source_path else "Anonymous"
            )
            builder = DocTreeBuilder(
                title=title,
                source="",
                source_path=document.source_path,
                metadata=document.metadata_overrides,
                block_kinds=self.block_kinds,
                topology="records",
            )
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            table_names = [row[0] for row in tables]
            columns_by_table: dict[str, list[str]] = {}
            rows_by_table: dict[str, list[tuple[object, ...]]] = {
                name: [] for name in table_names
            }
            for line in connection.iterdump():
                if line.startswith("CREATE TABLE "):
                    parsed_table = _create_table_columns(line)
                    if parsed_table is None:
                        continue
                    name, columns = parsed_table
                    if name in rows_by_table:
                        columns_by_table[name] = columns
                    continue
                parsed = _insert_values(line)
                if parsed is None:
                    continue
                name, values = parsed
                if name in rows_by_table:
                    rows_by_table[name].append(values)
            for table in table_names:
                header = columns_by_table.get(table, [])
                for row_number, values in enumerate(rows_by_table[table], start=1):
                    normalized = tuple(
                        "" if value is None else str(value) for value in values
                    )
                    builder.add_record(
                        "\n".join(
                            f"{name}: {value}"
                            for name, value in zip(header, normalized, strict=False)
                        ),
                        kind="tabular_row",
                        locations=(
                            SourceLocation(
                                source=str(document.source_path)
                                if document.source_path
                                else None,
                                sheet=table,
                                row_start=row_number,
                                row_end=row_number,
                                column_start=1,
                                column_end=max(1, len(normalized)),
                            ),
                        ),
                        attrs={
                            "table": table,
                            "header": header,
                            "values": normalized,
                        },
                    )
            return builder.build()
        finally:
            connection.close()

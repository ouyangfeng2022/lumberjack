"""SQLite parser using the standard library with table/row provenance."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import ClassVar

from ...models import DocTree, Document, SourceLocation
from ..builder import DocTreeBuilder


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


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
            for (table,) in tables:
                header = tuple(
                    row[1]
                    for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
                )
                rows = connection.execute(f"SELECT * FROM {_quote(table)}")
                for row_number, row in enumerate(rows, start=1):
                    values = tuple("" if value is None else str(value) for value in row)
                    builder.add_record(
                        "\n".join(
                            f"{name}: {value}"
                            for name, value in zip(header, values, strict=False)
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
                                column_end=max(1, len(values)),
                            ),
                        ),
                        attrs={"table": table, "header": header, "values": values},
                    )
            return builder.build()
        finally:
            connection.close()


__all__ = ["SQLiteParser"]

from __future__ import annotations

import sqlite3

from lumberjack.parser import SQLiteParser


def test_sqlite_parser_preserves_table_rows_and_columns() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE people (name TEXT, age INTEGER)")
    connection.execute("INSERT INTO people VALUES ('Ada', 36)")
    serialize = getattr(connection, "serialize")  # noqa: B009
    payload = serialize()
    connection.close()

    tree = SQLiteParser().parse(payload, source_path="people.sqlite")

    block = tree.root.blocks[0]
    assert tree.topology == "records"
    assert block.text == "name: Ada\nage: 36"
    assert block.attrs["table"] == "people"
    assert block.source_locations[0].sheet == "people"
    assert block.source_locations[0].row_start == 1

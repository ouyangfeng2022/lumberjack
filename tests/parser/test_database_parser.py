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


def test_sqlite_parser_round_trips_null_blob_and_embedded_quotes() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE things (label TEXT, note TEXT, blob_data BLOB, score REAL)"
    )
    connection.execute(
        "INSERT INTO things VALUES (?, ?, ?, ?)",
        ('it\'s "quoted"', None, b"\xab\xcd", -3.5),
    )
    connection.execute("INSERT INTO things VALUES ('plain', '', X'00FF', 1e4)")
    serialize = getattr(connection, "serialize")  # noqa: B009
    payload = serialize()
    connection.close()

    tree = SQLiteParser().parse(payload, document_title="things.db")

    blocks = tree.root.blocks
    assert len(blocks) == 2
    assert (
        blocks[0].text
        == "label: it's \"quoted\"\nnote: \nblob_data: b'\\xab\\xcd'\nscore: -3.5"
    )
    assert blocks[0].attrs["header"] == ["label", "note", "blob_data", "score"]
    assert blocks[0].attrs["values"] == (
        'it\'s "quoted"',
        "",
        "b'\\xab\\xcd'",
        "-3.5",
    )
    assert blocks[1].attrs["values"] == ("plain", "", "b'\\x00\\xff'", "10000.0")
    assert blocks[1].source_locations[0].row_start == 2


def test_sqlite_parser_supports_varchar_parens_in_column_types() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE catalog (code VARCHAR(10), amount DECIMAL(8,2))")
    connection.execute("INSERT INTO catalog VALUES ('ABC', 12.5)")
    serialize = getattr(connection, "serialize")  # noqa: B009
    payload = serialize()
    connection.close()

    tree = SQLiteParser().parse(payload, document_title="catalog.db")

    block = tree.root.blocks[0]
    assert block.attrs["header"] == ["code", "amount"]
    assert block.text == "code: ABC\namount: 12.5"

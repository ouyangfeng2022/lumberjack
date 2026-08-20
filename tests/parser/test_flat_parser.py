from __future__ import annotations

import pytest

from lumberjack._internal.pipeline import split_source
from lumberjack.parser import (
    AutoParser,
    DelimitedTextParser,
    JSONLinesParser,
    LogParser,
    TextParser,
)


def test_text_parser_preserves_paragraph_line_ranges() -> None:
    tree = TextParser().parse(
        "First line\nsecond line\n\nThird line", source_path="notes.txt"
    )

    assert tree.topology == "hierarchical"
    assert [block.text for block in tree.root.blocks] == [
        "First line\nsecond line",
        "Third line",
    ]
    assert [block.source_locations[0].line_start for block in tree.root.blocks] == [
        1,
        4,
    ]
    assert tree.source_path == "notes.txt"


def test_csv_parser_preserves_schema_and_row_column_provenance() -> None:
    tree = DelimitedTextParser().parse(
        "name,age\nAda,36\nGrace,", source_path="people.csv"
    )

    assert tree.topology == "records"
    assert [block.text for block in tree.root.blocks] == [
        "name: Ada\nage: 36",
        "name: Grace\nage: ",
    ]
    first = tree.root.blocks[0]
    assert first.attrs["header"] == ("name", "age")
    assert first.source_locations[0].row_start == 2
    assert first.source_locations[0].column_end == 2


def test_jsonl_parser_preserves_line_and_json_path() -> None:
    tree = JSONLinesParser().parse(
        '{"name":"Ada"}\n\n[1, 2]', source_path="records.jsonl"
    )

    assert tree.topology == "records"
    assert [block.text for block in tree.root.blocks] == ['{"name": "Ada"}', "[1, 2]"]
    assert [block.source_locations[0].json_path for block in tree.root.blocks] == [
        "$[0]",
        "$[1]",
    ]
    assert [block.source_locations[0].line_start for block in tree.root.blocks] == [
        1,
        3,
    ]


def test_jsonl_parser_reports_the_invalid_line() -> None:
    with pytest.raises(ValueError, match="line 2"):
        JSONLinesParser().parse('{"ok": true}\nnot json')


def test_log_and_auto_parser_create_record_topology() -> None:
    tree = AutoParser().parse("one\n\ntwo", format="auto", source_path="app.log")

    assert isinstance(LogParser(), LogParser)
    assert tree.topology == "records"
    assert [block.source_locations[0].element_id for block in tree.root.blocks] == [
        "line:1",
        "line:3",
    ]


def test_record_pipeline_requires_the_explicit_record_splitter() -> None:
    result = split_source(
        "name\nAda\nGrace",
        format="csv",
        splitter="record",
        max_tokens=100,
    )

    assert result.chunks[0].chunk_type == "record"
    assert [location.row_start for location in result.chunks[0].source_locations] == [
        2,
        3,
    ]
    with pytest.raises(ValueError, match="supports only hierarchical topology"):
        split_source("name\nAda", format="csv", splitter="section")

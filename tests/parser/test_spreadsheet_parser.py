from __future__ import annotations

from io import BytesIO

import pytest

from lumberjack._internal.pipeline import split_source
from lumberjack.parser import AutoParser, XlsxParser

openpyxl = pytest.importorskip("openpyxl")


def _workbook_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    people = workbook.active
    people.title = "People"
    people.append(["name", "age"])
    people.append(["Ada", 36])
    metrics = workbook.create_sheet("Metrics")
    metrics.append(["name", "score"])
    metrics.append(["quality", 1.0])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_xlsx_parser_preserves_sheet_row_and_column_provenance() -> None:
    tree = XlsxParser().parse(_workbook_bytes(), source_path="report.xlsx")

    assert tree.topology == "records"
    assert [block.text for block in tree.root.blocks] == [
        "name: Ada\nage: 36",
        "name: quality\nscore: 1",
    ]
    assert [block.source_locations[0].sheet for block in tree.root.blocks] == [
        "People",
        "Metrics",
    ]
    assert tree.root.blocks[0].source_locations[0].row_start == 2
    assert tree.root.blocks[0].source_locations[0].column_end == 2


def test_xlsx_auto_detection_uses_record_splitter() -> None:
    result = split_source(
        _workbook_bytes(),
        format="xlsx",
        source_path="report.xlsx",
        splitter="record",
        max_tokens=100,
    )

    assert result.chunks[0].chunk_type == "record"
    assert [location.sheet for location in result.chunks[0].source_locations] == [
        "People",
        "Metrics",
    ]
    assert (
        AutoParser().parse(_workbook_bytes(), source_path="report.xlsx").topology
        == "records"
    )

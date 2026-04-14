from __future__ import annotations

import os
import shutil
from pathlib import Path

from lumberjack import (
    Chunk,
    chunk_to_dict,
    parse_markdown,
    split_markdown_file,
    split_markdown_text,
)
from lumberjack.utils import join_markdown, render_heading_path

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "markdown" / "sample.md"
FIXTURE = FIXTURE_PATH.read_text(encoding="utf-8")
MERGED_SECTION_FIXTURE = """# Development Guide

## Current Scope

Scope body.

## Milestones

### M0

M0 body.

### M1

M1 body.
"""


def test_parse_markdown_uses_document_title() -> None:
    document = parse_markdown(
        FIXTURE,
        document_title="guide.md",
        document_metadata={"path": "/tmp/guide.md"},
    )

    assert document.title == "guide.md"
    assert document.root.title == "guide.md"
    assert document.metadata == {"path": "/tmp/guide.md"}


def test_split_markdown_text_matches_file_api() -> None:
    chunks_from_text = split_markdown_text(FIXTURE, document_title="sample.md", max_tokens=180)
    chunks_from_file = split_markdown_file(FIXTURE_PATH, max_tokens=180)

    assert [chunk.text for chunk in chunks_from_text] == [chunk.text for chunk in chunks_from_file]
    assert [chunk.token_count for chunk in chunks_from_text] == [
        chunk.token_count for chunk in chunks_from_file
    ]


def test_chunk_to_dict_serializes_heading_path() -> None:
    chunk = split_markdown_text(FIXTURE, document_title="sample.md", max_tokens=180)[-1]

    payload = chunk_to_dict(chunk)

    assert payload["chunk_id"] == "chunk-0005"
    assert payload["text"] == chunk.text
    assert payload["body"] == chunk.body
    assert payload["token_count"] == chunk.token_count
    assert payload["headings"] == [[1, "Overview"], [2, "Details"], [3, "Notes"]]
    assert payload["section_level"] == 3
    assert payload["document_title"] == "sample.md"
    assert payload["document_path"] is None
    assert payload["start_line"] == 19
    assert payload["end_line"] == 19


def test_chunk_to_dict_supports_chunks_constructed_with_legacy_signature() -> None:
    chunk = Chunk(
        "chunk-0001",
        "Body text",
        9,
        ((1, "Overview"),),
        1,
        "sample.md",
    )

    payload = chunk_to_dict(chunk)

    assert chunk.body == ""
    assert payload["body"] == ""
    assert payload["headings"] == [[1, "Overview"]]


def test_split_markdown_file_populates_chunk_metadata() -> None:
    chunk = split_markdown_file(FIXTURE_PATH, max_tokens=180)[0]

    assert chunk.chunk_id == "chunk-0001"
    assert chunk.document_title == "sample.md"
    assert chunk.document_path == str(FIXTURE_PATH.resolve())
    assert chunk.start_line == 1
    assert chunk.end_line == 1


def test_chunk_to_dict_uses_common_heading_path_for_merged_sections() -> None:
    chunk = split_markdown_text(
        MERGED_SECTION_FIXTURE,
        document_title="development.md",
        max_tokens=1000,
    )[0]

    payload = chunk_to_dict(chunk)

    assert payload["headings"] == [[1, "Development Guide"]]
    assert payload["section_level"] == 1


def test_parse_markdown_and_split_preserve_line_ranges_with_single_parser() -> None:
    document = parse_markdown(FIXTURE, document_title="sample.md")

    root = document.root
    assert root.title == "sample.md"
    assert root.blocks[0].start_line == 1
    assert root.blocks[0].end_line == 1
    assert root.children[0].start_line == 3

    chunks = split_markdown_text(
        FIXTURE,
        document_title="sample.md",
        max_tokens=200,
        document_metadata={"path": "/tmp/sample.md"},
    )

    assert len(chunks) == 5
    assert chunks[0].document_path == "/tmp/sample.md"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 1
    assert chunks[-1].headings == ((1, "Overview"), (2, "Details"), (3, "Notes"))
    assert chunks[-1].body == "Final notes live here."
    assert (
        join_markdown([render_heading_path(chunks[-1].headings), chunks[-1].body])
        == chunks[-1].text
    )
    assert chunks[-1].start_line == 19
    assert chunks[-1].end_line == 19


def test_split_markdown_text_does_not_write_debug_document_dump() -> None:
    tmp_path = Path(__file__).resolve().parent / "_tmp_no_dump"
    shutil.rmtree(tmp_path, ignore_errors=True)
    tmp_path.mkdir()
    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        split_markdown_text(FIXTURE, document_title="sample.md", max_tokens=200)
        assert not (tmp_path / "document.json").exists()
    finally:
        os.chdir(previous_cwd)
        shutil.rmtree(tmp_path, ignore_errors=True)

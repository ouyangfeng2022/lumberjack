from __future__ import annotations

from pathlib import Path

from lumberjack import chunk_to_dict, parse_markdown, split_markdown_file, split_markdown_text

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
    assert payload["token_count"] == chunk.token_count
    assert payload["headings"] == [[1, "Overview"], [2, "Details"], [3, "Notes"]]
    assert payload["section_level"] == 3
    assert payload["document_title"] == "sample.md"
    assert payload["document_path"] is None
    assert payload["start_line"] == 19
    assert payload["end_line"] == 19


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

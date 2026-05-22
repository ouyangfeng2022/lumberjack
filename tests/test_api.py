from __future__ import annotations

import os
import shutil
from dataclasses import asdict
from pathlib import Path

from mdit_py_plugins.tasklists import tasklists_plugin

import lumberjack
from lumberjack import lumber
from lumberjack.core.parser import MarkdownItParser, create_parser

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


def test_package_exports_lumber_as_only_top_level_api() -> None:
    assert lumberjack.__all__ == ["lumber"]
    assert lumberjack.lumber is lumber
    assert not hasattr(lumberjack, "split_markdown_file")
    assert not hasattr(lumberjack, "split_markdown_text")
    assert not hasattr(lumberjack, "parse_markdown")


def test_parser_uses_document_title() -> None:
    document = create_parser("default").parse(
        FIXTURE,
        document_title="guide.md",
        document_metadata={"path": "/tmp/guide.md"},
    )

    assert document.title == "guide.md"
    assert document.root.title == "guide.md"
    assert document.metadata == {"path": "/tmp/guide.md"}


def test_lumber_uses_string_input_and_document_metadata() -> None:
    chunks = lumber(
        FIXTURE,
        document_title="sample.md",
        max_tokens=180,
        document_metadata={"path": str(FIXTURE_PATH.resolve())},
    )

    assert chunks[0].document_title == "sample.md"
    assert chunks[0].document_path == str(FIXTURE_PATH.resolve())
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 1


def test_lumber_accepts_overlap_options() -> None:
    chunks = lumber(
        FIXTURE,
        document_title="sample.md",
        max_tokens=120,
        merge_below_tokens=0,
        overlap_tokens=12,
        merge_small_chunks=False,
    )

    assert chunks
    assert all(chunk.document_title == "sample.md" for chunk in chunks)


def test_lumber_accepts_section_splitter() -> None:
    chunks = lumber(
        MERGED_SECTION_FIXTURE,
        document_title="development.md",
        splitter="section",
        max_tokens=1000,
        skip_empty_sections=False,
    )

    assert [chunk.headings for chunk in chunks] == [
        ((1, "Development Guide"),),
        ((1, "Development Guide"), (2, "Current Scope")),
        ((1, "Development Guide"), (2, "Milestones")),
        ((1, "Development Guide"), (2, "Milestones"), (3, "M0")),
        ((1, "Development Guide"), (2, "Milestones"), (3, "M1")),
    ]


def test_lumber_recursive_splitter_matches_default() -> None:
    default_chunks = lumber(
        MERGED_SECTION_FIXTURE,
        document_title="development.md",
        max_tokens=1000,
    )
    recursive_chunks = lumber(
        MERGED_SECTION_FIXTURE,
        document_title="development.md",
        splitter="recursive",
        max_tokens=1000,
    )

    assert [asdict(chunk) for chunk in recursive_chunks] == [
        asdict(chunk) for chunk in default_chunks
    ]


def test_lumber_rejects_unknown_splitter() -> None:
    try:
        lumber(FIXTURE, splitter="unknown")
    except ValueError as e:
        assert str(e) == "Unsupported splitter: unknown"
    else:
        raise AssertionError("Expected unsupported splitter to raise ValueError")


def test_lumber_can_disable_setext_headings() -> None:
    chunks = lumber(
        "Title\n=====\n\nbody",
        document_title="setext.md",
        max_tokens=500,
        retain_headings=False,
        disable_lheading=True,
    )

    assert len(chunks) == 1
    assert chunks[0].body == "Title\n=====\n\nbody"
    assert chunks[0].headings == ()


def test_chunk_to_dict_serializes_heading_path() -> None:
    chunk = lumber(
        FIXTURE,
        document_title="sample.md",
        max_tokens=180,
        standalone_blocks=frozenset(),
    )[-1]

    payload = asdict(chunk)

    assert payload["chunk_id"] == "chunk-0005"
    assert payload["chunk_type"] == "paragraph"
    assert payload["body"] == chunk.body
    assert payload["token_count"] == chunk.token_count
    assert payload["estimated_token_count"] == chunk.estimated_token_count
    assert payload["headings"] == ((1, "Overview"), (2, "Details"), (3, "Notes"))
    assert payload["section_level"] == 3
    assert payload["document_title"] == "sample.md"
    assert payload["document_path"] is None
    assert payload["start_line"] == 19
    assert payload["end_line"] == 19


def test_chunk_to_dict_uses_common_heading_path_for_merged_sections() -> None:
    chunk = lumber(
        MERGED_SECTION_FIXTURE,
        document_title="development.md",
        max_tokens=1000,
    )[0]

    payload = asdict(chunk)

    assert payload["headings"] == ((1, "Development Guide"),)
    assert payload["section_level"] == 1


def test_parse_markdown_and_split_preserve_line_ranges_with_single_parser() -> None:
    document = create_parser("default").parse(FIXTURE, document_title="sample.md")

    root = document.root
    assert root.title == "sample.md"
    assert root.blocks[0].start_line == 1
    assert root.blocks[0].end_line == 1
    assert root.children[0].start_line == 3

    chunks = lumber(
        FIXTURE,
        document_title="sample.md",
        max_tokens=200,
        document_metadata={"path": "/tmp/sample.md"},
        standalone_blocks=frozenset(),
    )

    assert len(chunks) == 5
    assert chunks[0].document_path == "/tmp/sample.md"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 1
    assert chunks[-1].headings == ((1, "Overview"), (2, "Details"), (3, "Notes"))
    assert (
        chunks[-1].body
        == "# Overview\n\n## Details\n\n### Notes\n\nFinal notes live here."
    )
    assert chunks[-1].start_line == 19
    assert chunks[-1].end_line == 19


def test_lumber_does_not_write_debug_document_dump() -> None:
    tmp_path = Path(__file__).resolve().parent / "_tmp_no_dump"
    shutil.rmtree(tmp_path, ignore_errors=True)
    tmp_path.mkdir()
    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        lumber(FIXTURE, document_title="sample.md", max_tokens=200)
        assert not (tmp_path / "document.json").exists()
    finally:
        os.chdir(previous_cwd)
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_lumber_accepts_markdown_it_parser_with_plugins() -> None:
    parser = MarkdownItParser(plugins=(tasklists_plugin,))
    markdown = "- [x] done\n- [ ] todo"

    chunks = lumber(
        markdown,
        document_title="tasks.md",
        max_tokens=500,
        parser=parser,
        retain_headings=False,
    )

    assert len(chunks) == 1
    assert chunks[0].body == markdown

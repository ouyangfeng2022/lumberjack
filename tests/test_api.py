from __future__ import annotations

import os
import shutil
from dataclasses import asdict
from inspect import signature
from pathlib import Path
from typing import Any

import pytest
from mdit_py_plugins.tasklists import tasklists_plugin

import lumberjack
from lumberjack import lumber
from lumberjack.core.models import Chunk, SplitOptions, TableBlockParams
from lumberjack.core.options import parse_cli_block_configs, resolve_block_options
from lumberjack.core.parsers.markdown.parser import MarkdownItParser
from lumberjack.core.splitters import RecursiveSplitter
from lumberjack.core.tokenizers import SimpleCharTokenizer
from lumberjack.lumber import lumber as module_lumber

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
    assert lumberjack.__all__ == ["AstVisitor", "lumber"]
    assert lumberjack.lumber is lumber
    assert module_lumber is lumber
    assert not hasattr(lumberjack, "HTMLParser")
    assert not hasattr(lumberjack, "split_markdown_file")
    assert not hasattr(lumberjack, "split_markdown_text")
    assert not hasattr(lumberjack, "parse_markdown")


def test_lumber_api_no_longer_exposes_render_common_headings_option() -> None:
    assert "render_common_headings" not in signature(lumber).parameters


def test_lumber_api_no_longer_exposes_isolate_front_matter_option() -> None:
    assert "isolate_front_matter" not in signature(lumber).parameters


def test_lumber_api_no_longer_exposes_parser_override() -> None:
    assert "parser" not in signature(lumber).parameters


def test_parser_uses_document_title() -> None:
    document = MarkdownItParser().parse(
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


def test_lumber_accepts_html_format() -> None:
    chunks = lumber(
        "<html><body><h1>Guide</h1><p>Intro <strong>bold</strong>.</p></body></html>",
        format="html",
        max_tokens=500,
    )

    assert len(chunks) == 1
    assert chunks[0].document_title == "Guide"
    assert chunks[0].body == "# Guide\n\nIntro bold."


def test_lumber_accepts_table_block_params_mapping() -> None:
    chunks = lumber(
        """| Name | Value |
| ---- | ----- |
| Alpha | 100 |
| Beta | 200 |
| Gamma | 300 |
| Delta | 400 |
""",
        max_tokens=28,
        ideal_max_tokens_ratio=1,
        merge_below_tokens=-1,
        block_options={"table": {"repeat_header": False}},
    )

    assert len(chunks) == 4
    assert isinstance(chunks[0].body, str)
    assert "| Name | Value |" in chunks[0].body
    assert all("| Name | Value |" not in chunk.body for chunk in chunks[1:])


def test_parse_cli_block_configs_json_overrides_short_config() -> None:
    block_options = parse_cli_block_configs(
        ["table:isolated:500"],
        json_config='{"table": {"repeat_header": false}}',
    )

    table = block_options["table"]
    assert table.isolated is False
    assert table.max_tokens is None
    assert table == TableBlockParams(repeat_header=False)


def test_lumber_auto_detects_html_path(tmp_path: Path) -> None:
    html_path = tmp_path / "guide.html"
    html_path.write_text("<h1>Guide</h1><p>Body</p>", encoding="utf-8")

    chunks = lumber(html_path, max_tokens=500)

    assert chunks[0].document_title == "Guide"
    assert chunks[0].body == "# Guide\n\nBody"


def test_lumber_accepts_ideal_max_tokens_ratio() -> None:
    chunks = lumber(
        "# A\n\nalpha1\n\nbravo2",
        document_title="ideal.md",
        max_tokens=30,
        ideal_max_tokens_ratio=0.5,
        merge_below_tokens=-1,
    )

    assert [chunk.body for chunk in chunks] == [
        "# A\n\nalpha1",
        "# A\n\nbravo2",
    ]


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


def test_lumber_body_always_renders_full_common_heading_path() -> None:
    chunks = lumber(
        MERGED_SECTION_FIXTURE,
        document_title="development.md",
        max_tokens=1000,
    )

    assert chunks[0].headings == ((1, "Development Guide"),)
    assert chunks[0].body == (
        "# Development Guide\n\n## Current Scope\n\nScope body.\n\n## Milestones\n\n"
        "### M0\n\nM0 body.\n\n### M1\n\nM1 body."
    )


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


def test_lumber_rejects_tokenizer_instances() -> None:
    tokenizer: Any = SimpleCharTokenizer()

    with pytest.raises(TypeError, match="tokenizer must be a string"):
        lumber(FIXTURE, tokenizer=tokenizer)


def test_lumber_rejects_splitter_instances() -> None:
    splitter: Any = RecursiveSplitter(tokenizer=SimpleCharTokenizer())

    with pytest.raises(TypeError, match="splitter must be a string"):
        lumber(FIXTURE, splitter=splitter)


def test_chunk_to_dict_serializes_heading_path() -> None:
    chunk = lumber(
        FIXTURE,
        document_title="sample.md",
        max_tokens=180,
        block_options={},
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
    document = MarkdownItParser().parse(FIXTURE, document_title="sample.md")

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
        block_options={},
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


def test_manual_pipeline_can_disable_setext_headings() -> None:
    parser = MarkdownItParser(disable_lheading=True)
    document = parser.parse("Title\n=====\n\nbody", document_title="setext.md")
    splitter = RecursiveSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            block_options=resolve_block_options(parser.block_kinds, None),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == "Title\n=====\n\nbody"
    assert chunks[0].headings == ()


def test_manual_pipeline_accepts_markdown_it_parser_with_plugins() -> None:
    parser = MarkdownItParser(plugins=(tasklists_plugin,))
    markdown = "- [x] done\n- [ ] todo"
    document = parser.parse(markdown, document_title="tasks.md")
    splitter = RecursiveSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            block_options=resolve_block_options(parser.block_kinds, None),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == markdown


class ConstantTokenizer:
    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return (1, 2, 3) if text else ()

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(self.encode(text))


def test_manual_pipeline_accepts_custom_tokenizer_instance() -> None:
    parser = MarkdownItParser()
    document = parser.parse("# Title\n\nBody", document_title="custom.md")
    splitter = RecursiveSplitter(
        tokenizer=ConstantTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            block_options=resolve_block_options(parser.block_kinds, None),
        ),
    )

    chunks = splitter.split(document)

    assert chunks[0].token_count == 3


class EchoSplitter:
    def split(self, document) -> list[Chunk]:
        return [
            Chunk(
                chunk_id="custom-0001",
                chunk_type="custom",
                body=document.title,
                token_count=1,
                estimated_token_count=1,
                document_title=document.title,
            )
        ]


def test_manual_pipeline_accepts_custom_splitter_instance() -> None:
    document = MarkdownItParser().parse("# Custom\n\nBody", document_title="custom.md")

    chunks = EchoSplitter().split(document)

    assert chunks == [
        Chunk(
            chunk_id="custom-0001",
            chunk_type="custom",
            body="custom.md",
            token_count=1,
            estimated_token_count=1,
            document_title="custom.md",
        )
    ]

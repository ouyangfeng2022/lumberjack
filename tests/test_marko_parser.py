from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lumberjack import create_parser, parse_markdown, split_markdown_text
from lumberjack.core.marko_parser import MarkoMarkdownParser

if TYPE_CHECKING:
    from lumberjack.models import SectionNode

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "markdown" / "sample.md"
FIXTURE = FIXTURE_PATH.read_text(encoding="utf-8")


def test_create_parser_supports_marko() -> None:
    parser = create_parser("marko")

    assert isinstance(parser, MarkoMarkdownParser)


def test_marko_parser_builds_internal_ast_with_line_ranges() -> None:
    document = MarkoMarkdownParser().parse(FIXTURE, document_title="sample.md")

    root = document.root
    assert root.title == "sample.md"
    assert root.blocks[0].text == "Intro paragraph before headings."
    assert root.blocks[0].start_line == 1
    assert root.blocks[0].end_line == 1

    overview = root.children[0]
    assert overview.title == "Overview"
    assert overview.start_line == 3

    details = overview.children[0]
    assert details.title == "Details"
    assert details.start_line == 7

    notes = details.children[0]
    assert notes.title == "Notes"
    assert notes.start_line == 17

    details_blocks = details.blocks
    assert details_blocks[0].kind == "paragraph"
    assert details_blocks[0].start_line == 9
    assert details_blocks[0].end_line == 10
    assert details_blocks[1].kind == "code_fence"
    assert details_blocks[1].text.startswith("```python")
    assert details_blocks[1].start_line == 12
    assert details_blocks[1].end_line == 15


def test_split_markdown_text_accepts_marko_parser() -> None:
    chunks = split_markdown_text(
        FIXTURE,
        document_title="sample.md",
        parser="marko",
        max_tokens=200,
        document_metadata={"path": "/tmp/sample.md"},
    )

    assert len(chunks) == 5
    assert chunks[0].chunk_id == "chunk-0001"
    assert chunks[-1].chunk_id == "chunk-0005"
    assert chunks[0].document_path == "/tmp/sample.md"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 1
    assert chunks[-1].headings == ((1, "Overview"), (2, "Details"), (3, "Notes"))
    assert chunks[-1].start_line == 19
    assert chunks[-1].end_line == 19
    assert "# Overview" in chunks[1].text


def test_marko_parser_matches_simple_parser_structure() -> None:
    simple_document = parse_markdown(FIXTURE, document_title="sample.md", parser="simple")
    marko_document = parse_markdown(FIXTURE, document_title="sample.md", parser="marko")

    assert _section_signature(simple_document.root) == _section_signature(marko_document.root)


def test_marko_parser_matches_simple_parser_chunks() -> None:
    simple_chunks = split_markdown_text(
        FIXTURE, document_title="sample.md", parser="simple", max_tokens=140
    )
    marko_chunks = split_markdown_text(
        FIXTURE, document_title="sample.md", parser="marko", max_tokens=140
    )

    assert [chunk.text for chunk in simple_chunks] == [chunk.text for chunk in marko_chunks]
    assert [chunk.headings for chunk in simple_chunks] == [chunk.headings for chunk in marko_chunks]
    assert [(chunk.start_line, chunk.end_line) for chunk in simple_chunks] == [
        (chunk.start_line, chunk.end_line) for chunk in marko_chunks
    ]


def _section_signature(section: SectionNode) -> tuple[object, ...]:
    return (
        section.level,
        section.title,
        section.start_line,
        [(block.kind, block.text, block.start_line, block.end_line) for block in section.blocks],
        [_section_signature(child) for child in section.children],
    )

from __future__ import annotations

import sys
import types
from pathlib import Path

from lumberjack import create_parser, parse_markdown, split_markdown_text
from lumberjack.core.marko_parser import MarkoMarkdownParser
from lumberjack.models import SectionNode

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "markdown" / "sample.md"
FIXTURE = FIXTURE_PATH.read_text(encoding="utf-8")


def _sample_ast() -> dict[str, object]:
    return {
        "element": "document",
        "children": [
            {
                "element": "paragraph",
                "children": [{"element": "raw_text", "children": "Intro paragraph before headings."}],
            },
            {
                "element": "heading",
                "level": 1,
                "children": [{"element": "raw_text", "children": "Overview"}],
            },
            {
                "element": "paragraph",
                "children": [{"element": "raw_text", "children": "This is the overview section."}],
            },
            {
                "element": "heading",
                "level": 2,
                "children": [{"element": "raw_text", "children": "Details"}],
            },
            {
                "element": "paragraph",
                "children": [
                    {
                        "element": "raw_text",
                        "children": (
                            "These details are intentionally long enough to require multiple chunks when the\n"
                            "token budget is set very low."
                        ),
                    }
                ],
            },
            {
                "element": "fenced_code",
                "lang": "python",
                "children": (
                    '# This heading-looking line should stay inside the code fence.\n'
                    'print("hello")\n'
                ),
            },
            {
                "element": "heading",
                "level": 3,
                "children": [{"element": "raw_text", "children": "Notes"}],
            },
            {
                "element": "paragraph",
                "children": [{"element": "raw_text", "children": "Final notes live here."}],
            },
        ],
    }


def _install_fake_marko(ast: dict[str, object]) -> None:
    marko_module = types.ModuleType("marko")
    ast_renderer_module = types.ModuleType("marko.ast_renderer")

    class FakeMarkdown:
        def __init__(self, *, renderer):
            self.renderer = renderer

        def convert(self, text: str) -> dict[str, object]:
            return ast

    class FakeASTRenderer:
        pass

    marko_module.Markdown = FakeMarkdown
    ast_renderer_module.ASTRenderer = FakeASTRenderer
    sys.modules["marko"] = marko_module
    sys.modules["marko.ast_renderer"] = ast_renderer_module


def _remove_fake_marko() -> None:
    sys.modules.pop("marko", None)
    sys.modules.pop("marko.ast_renderer", None)


def test_create_parser_supports_marko() -> None:
    parser = create_parser("marko")

    assert isinstance(parser, MarkoMarkdownParser)


def test_marko_parser_builds_internal_ast_with_line_ranges() -> None:
    _install_fake_marko(_sample_ast())
    try:
        document = MarkoMarkdownParser().parse(FIXTURE, document_title="sample.md")
    finally:
        _remove_fake_marko()

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
    _install_fake_marko(_sample_ast())
    try:
        chunks = split_markdown_text(
            FIXTURE,
            document_title="sample.md",
            parser="marko",
            max_tokens=200,
            document_metadata={"path": "/tmp/sample.md"},
        )
    finally:
        _remove_fake_marko()

    assert len(chunks) == 4
    assert chunks[0].chunk_id == "chunk-0001"
    assert chunks[-1].chunk_id == "chunk-0004"
    assert chunks[0].document_path == "/tmp/sample.md"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 5
    assert chunks[-1].headings == ((1, "Overview"), (2, "Details"), (3, "Notes"))
    assert chunks[-1].start_line == 19
    assert chunks[-1].end_line == 19
    assert "# Overview" in chunks[0].text


def test_marko_parser_matches_simple_parser_structure() -> None:
    _install_fake_marko(_sample_ast())
    try:
        simple_document = parse_markdown(FIXTURE, document_title="sample.md", parser="simple")
        marko_document = parse_markdown(FIXTURE, document_title="sample.md", parser="marko")
    finally:
        _remove_fake_marko()

    assert _section_signature(simple_document.root) == _section_signature(marko_document.root)


def test_marko_parser_matches_simple_parser_chunks() -> None:
    _install_fake_marko(_sample_ast())
    try:
        simple_chunks = split_markdown_text(FIXTURE, document_title="sample.md", parser="simple", max_tokens=140)
        marko_chunks = split_markdown_text(FIXTURE, document_title="sample.md", parser="marko", max_tokens=140)
    finally:
        _remove_fake_marko()

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

from __future__ import annotations

from pathlib import Path

from lumberjack.core.parser import MarkdownParser

FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "markdown" / "sample.md").read_text(
    encoding="utf-8"
)


def test_parser_builds_heading_tree() -> None:
    """Test that parser builds correct heading tree structure."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    root = document.root

    assert root.title == "sample.md"
    assert len(root.blocks) == 1
    assert len(root.children) == 1
    assert root.children[0].title == "Overview"
    assert root.children[0].children[0].title == "Details"
    assert root.children[0].children[0].children[0].title == "Notes"


def test_parser_ignores_headings_inside_code_fence() -> None:
    """Test that headings inside fenced code blocks are ignored."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    details = document.root.children[0].children[0]
    code_blocks = [block for block in details.blocks if block.kind == "code_fence"]

    assert len(code_blocks) == 1
    assert "# This heading-looking line" in code_blocks[0].text
    assert len(details.children) == 1

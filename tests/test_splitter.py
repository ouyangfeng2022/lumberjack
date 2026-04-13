from __future__ import annotations

from pathlib import Path

from lumberjack.core.parser import MarkdownParser
from lumberjack.core.splitter import MarkdownSplitter
from lumberjack.core.tokenizers import SimpleCharTokenizer
from lumberjack.models import SplitOptions

FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "markdown" / "sample.md").read_text(
    encoding="utf-8"
)

MERGED_SECTION_FIXTURE = """# Development Guide

## Current Scope

Scope body.

## Milestones

### M0

M0 body.

### M1

M1 body.

## Suggested Workflow

Workflow body.
"""


def test_splitter_preserves_heading_context() -> None:
    """Test that splitter preserves heading hierarchy in chunks."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())
    chunks = splitter.split(document, SplitOptions(max_tokens=140, min_tokens=20))

    assert len(chunks) >= 2
    assert any("# Overview" in chunk.text for chunk in chunks)
    assert any("## Details" in chunk.text for chunk in chunks)


def test_splitter_respects_budget_except_unsplittable_code_fence() -> None:
    """Test that splitter respects token budget except for code fences."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())
    chunks = splitter.split(document, SplitOptions(max_tokens=180, min_tokens=20))

    oversized = [chunk for chunk in chunks if chunk.token_count > 180]
    if oversized:
        assert all("```" in chunk.text for chunk in oversized)


def test_splitter_deduplicates_shared_parent_heading_in_merged_chunk() -> None:
    document = MarkdownParser().parse(MERGED_SECTION_FIXTURE, document_title="development.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())
    chunks = splitter.split(document, SplitOptions(max_tokens=1000, min_tokens=20))

    assert len(chunks) == 1
    assert chunks[0].text.count("# Development Guide") == 1
    assert "## Current Scope" in chunks[0].text
    assert "## Milestones" in chunks[0].text
    assert "### M0" in chunks[0].text
    assert "### M1" in chunks[0].text
    assert "## Suggested Workflow" in chunks[0].text
    assert chunks[0].headings == ((1, "Development Guide"),)
    assert chunks[0].section_level == 1


def test_splitter_omits_headings_from_text_when_disabled() -> None:
    document = MarkdownParser().parse(MERGED_SECTION_FIXTURE, document_title="development.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())

    with_headings = splitter.split(
        document,
        SplitOptions(max_tokens=1000, min_tokens=20, retain_headings=True),
    )
    without_headings = splitter.split(
        document,
        SplitOptions(max_tokens=1000, min_tokens=20, retain_headings=False),
    )

    assert len(with_headings) == 1
    assert len(without_headings) == 1
    assert "# Development Guide" in with_headings[0].text
    assert "## Current Scope" in with_headings[0].text
    assert "# Development Guide" not in without_headings[0].text
    assert "## Current Scope" in without_headings[0].text
    assert "## Milestones" in without_headings[0].text
    assert "Scope body." in without_headings[0].text
    assert "M0 body." in without_headings[0].text
    assert without_headings[0].headings == ((1, "Development Guide"),)
    assert without_headings[0].token_count == len(without_headings[0].text)
    assert without_headings[0].token_count < with_headings[0].token_count

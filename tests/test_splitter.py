from __future__ import annotations

from pathlib import Path

from lumberjack.core.parser import MarkdownParser
from lumberjack.core.splitter import MarkdownSplitter
from lumberjack.core.tokenizers import SimpleCharTokenizer
from lumberjack.models import SplitOptions
from lumberjack.utils import join_markdown, render_heading_path

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

RECURSIVE_SECTION_FIXTURE = """# Alpha

Alpha summary.

# Beta

## Beta One

This subsection stays comfortably under the budget.

## Beta Two

This subsection also stays under the budget by itself.
"""

MULTI_ROOT_FIXTURE = """# First

First body.

# Second

Second body.
"""

GREEDY_SIBLING_FIXTURE = """# Parent

## One

One body.

## Two

Two body.

## Three

Three body is a little longer.
"""

THIRD_LEVEL_FIXTURE = """# Root

## Scope

### A

Alpha body.

### B

Beta body.
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
    assert without_headings[0].body == without_headings[0].text
    assert without_headings[0].headings == ((1, "Development Guide"),)
    assert without_headings[0].token_count == len(without_headings[0].text)
    assert without_headings[0].token_count < with_headings[0].token_count


def test_splitter_recursively_descends_heading_levels_when_section_is_oversized() -> None:
    document = MarkdownParser().parse(RECURSIVE_SECTION_FIXTURE, document_title="recursive.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())

    chunks = splitter.split(
        document,
        SplitOptions(max_tokens=90, min_tokens=80, retain_headings=True),
    )

    assert len(chunks) == 3
    assert chunks[0].text == "# Alpha\n\nAlpha summary."
    assert (
        chunks[1].text
        == "# Beta\n\n## Beta One\n\nThis subsection stays comfortably under the budget."
    )
    assert (
        chunks[2].text
        == "# Beta\n\n## Beta Two\n\nThis subsection also stays under the budget by itself."
    )
    assert all(chunk.token_count <= 90 for chunk in chunks)


def test_splitter_checks_whole_document_before_splitting_by_top_level_headings() -> None:
    document = MarkdownParser().parse(MULTI_ROOT_FIXTURE, document_title="multi-root.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())

    chunks = splitter.split(
        document,
        SplitOptions(max_tokens=200, min_tokens=20, retain_headings=True),
    )

    assert len(chunks) == 1
    assert chunks[0].text == "# First\n\nFirst body.\n\n# Second\n\nSecond body."


def test_splitter_greedily_merges_same_level_siblings_before_descending() -> None:
    document = MarkdownParser().parse(GREEDY_SIBLING_FIXTURE, document_title="siblings.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())

    chunks = splitter.split(
        document,
        SplitOptions(max_tokens=60, min_tokens=20, retain_headings=True),
    )

    assert len(chunks) == 2
    assert chunks[0].text == "# Parent\n\n## One\n\nOne body.\n\n## Two\n\nTwo body."
    assert chunks[1].text == "# Parent\n\n## Three\n\nThree body is a little longer."
    assert all(chunk.token_count <= 60 for chunk in chunks)


def test_splitter_exposes_body_without_common_headings_for_single_leaf_chunk() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())

    chunks = splitter.split(
        document,
        SplitOptions(max_tokens=35, min_tokens=0, retain_headings=True),
    )

    assert chunks[0].headings == ((1, "Root"), (2, "Scope"), (3, "A"))
    assert chunks[0].body == "Alpha body."
    assert (
        join_markdown([render_heading_path(chunks[0].headings), chunks[0].body]) == chunks[0].text
    )


def test_splitter_exposes_body_without_common_headings_for_multi_entry_chunk() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())

    chunks = splitter.split(
        document,
        SplitOptions(max_tokens=60, min_tokens=0, retain_headings=True),
    )

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Root"), (2, "Scope"))
    assert chunks[0].body == "### A\n\nAlpha body.\n\n### B\n\nBeta body."
    assert (
        join_markdown([render_heading_path(chunks[0].headings), chunks[0].body]) == chunks[0].text
    )


def test_splitter_body_matches_visible_text_when_headings_are_hidden() -> None:
    document = MarkdownParser().parse(MULTI_ROOT_FIXTURE, document_title="multi-root.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())

    chunks = splitter.split(
        document,
        SplitOptions(max_tokens=200, min_tokens=0, retain_headings=False),
    )

    assert len(chunks) == 1
    assert chunks[0].text == "First body.\n\nSecond body."
    assert chunks[0].body == chunks[0].text


def test_splitter_body_drops_only_visible_common_headings_when_headings_are_hidden() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())

    chunks = splitter.split(
        document,
        SplitOptions(max_tokens=60, min_tokens=0, retain_headings=False),
    )

    assert len(chunks) == 1
    assert chunks[0].text == "## Scope\n\n### A\n\nAlpha body.\n\n### B\n\nBeta body."
    assert chunks[0].body == "### A\n\nAlpha body.\n\n### B\n\nBeta body."


def test_splitter_adds_overlap_only_for_text_fallback_splits() -> None:
    document = MarkdownParser().parse(
        "alpha beta gamma delta epsilon zeta",
        document_title="overlap.md",
    )
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())

    chunks = splitter.split(
        document,
        SplitOptions(
            max_tokens=16,
            min_tokens=0,
            overlap_tokens=5,
            retain_headings=False,
            merge_small_chunks=False,
        ),
    )

    assert [chunk.body for chunk in chunks] == [
        "alpha beta gamma",
        "gamma delta",
        "delta epsilon",
        "zeta",
    ]
    assert [chunk.text for chunk in chunks] == [chunk.body for chunk in chunks]


def test_splitter_rejects_overlap_budget_that_consumes_the_whole_chunk() -> None:
    document = MarkdownParser().parse("alpha beta", document_title="invalid.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())

    try:
        splitter.split(
            document,
            SplitOptions(max_tokens=10, min_tokens=0, overlap_tokens=10),
        )
    except ValueError as exc:
        assert str(exc) == "overlap_tokens must be smaller than max_tokens"
    else:
        raise AssertionError("Expected overlap validation to fail")

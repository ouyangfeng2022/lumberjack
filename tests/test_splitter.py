from __future__ import annotations

from pathlib import Path

from lumberjack.api import lumber
from lumberjack.core.parser import MarkdownParser
from lumberjack.core.splitter import MarkdownSplitter, _ChunkDraft, _Entry, heading_path_token_count
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

LIST_FIXTURE = """- alpha alpha alpha alpha
- beta beta beta beta
- gamma gamma gamma gamma
"""

CODE_FENCE_FIXTURE = """```python
print("alpha")
print("beta")
print("gamma")
```"""

LONG_URL_FIXTURE = (
    "See https://example.com/really/long/path/that/should/not/be/split/in/chunks for details."
)


class RecordingTokenizer(SimpleCharTokenizer):
    def __init__(self) -> None:
        self.counted: list[str] = []

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        self.counted.append(text)
        return super().count(text)


def test_splitter_preserves_heading_context() -> None:
    """Test that splitter preserves heading hierarchy in chunks."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=140, merge_below_tokens=20),
    )
    chunks = splitter.split(document)

    assert len(chunks) >= 2
    assert any("# Overview" in chunk.body for chunk in chunks)
    assert any("## Details" in chunk.body for chunk in chunks)


def test_splitter_respects_budget_except_unsplittable_code_fence() -> None:
    """Test that splitter respects token budget except for code fences."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=180, merge_below_tokens=20),
    )
    chunks = splitter.split(document)

    oversized = [chunk for chunk in chunks if chunk.estimated_token_count > 180]
    if oversized:
        assert all("```" in chunk.body for chunk in oversized)


def test_splitter_deduplicates_shared_parent_heading_in_merged_chunk() -> None:
    document = MarkdownParser().parse(MERGED_SECTION_FIXTURE, document_title="development.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=20),
    )
    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body.count("# Development Guide") == 1
    assert "## Current Scope" in chunks[0].body
    assert "## Milestones" in chunks[0].body
    assert "### M0" in chunks[0].body
    assert "### M1" in chunks[0].body
    assert "## Suggested Workflow" in chunks[0].body
    assert chunks[0].headings == ((1, "Development Guide"),)
    assert chunks[0].section_level == 1


def test_splitter_omits_headings_from_body_when_disabled() -> None:
    document = MarkdownParser().parse(MERGED_SECTION_FIXTURE, document_title="development.md")

    with_headings = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=20, retain_headings=True),
    ).split(document)
    without_headings = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=20, retain_headings=False),
    ).split(document)

    assert len(with_headings) == 1
    assert len(without_headings) == 1
    assert "# Development Guide" in with_headings[0].body
    assert "## Current Scope" in with_headings[0].body
    assert "# Development Guide" not in without_headings[0].body
    assert "## Current Scope" not in without_headings[0].body
    assert "## Milestones" not in without_headings[0].body
    assert "Scope body." in without_headings[0].body
    assert "M0 body." in without_headings[0].body
    assert without_headings[0].headings == ((1, "Development Guide"),)
    assert without_headings[0].token_count == len(without_headings[0].body)
    assert without_headings[0].token_count < with_headings[0].token_count


def test_splitter_recursively_descends_heading_levels_when_section_is_oversized() -> None:
    document = MarkdownParser().parse(RECURSIVE_SECTION_FIXTURE, document_title="recursive.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=90, merge_below_tokens=80, retain_headings=True),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 3
    assert chunks[0].body == "# Alpha\n\nAlpha summary."
    assert (
        chunks[1].body
        == "# Beta\n\n## Beta One\n\nThis subsection stays comfortably under the budget."
    )
    assert (
        chunks[2].body
        == "# Beta\n\n## Beta Two\n\nThis subsection also stays under the budget by itself."
    )
    assert all(chunk.estimated_token_count <= 90 for chunk in chunks)


def test_splitter_checks_whole_document_before_splitting_by_top_level_headings() -> None:
    document = MarkdownParser().parse(MULTI_ROOT_FIXTURE, document_title="multi-root.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=200, merge_below_tokens=20, retain_headings=True),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == "# First\n\nFirst body.\n\n# Second\n\nSecond body."


def test_splitter_greedily_merges_same_level_siblings_before_descending() -> None:
    document = MarkdownParser().parse(GREEDY_SIBLING_FIXTURE, document_title="siblings.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=62, merge_below_tokens=20, retain_headings=True),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 2
    assert chunks[0].body == "# Parent\n\n## One\n\nOne body.\n\n## Two\n\nTwo body."
    assert chunks[1].body == "# Parent\n\n## Three\n\nThree body is a little longer."
    assert all(chunk.estimated_token_count <= 60 for chunk in chunks)


def test_splitter_exposes_body_without_common_headings_for_single_leaf_chunk() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=40, merge_below_tokens=0, retain_headings=True),
    )

    chunks = splitter.split(document)

    assert chunks[0].headings == ((1, "Root"), (2, "Scope"), (3, "A"))
    assert chunks[0].body == "# Root\n\n## Scope\n\n### A\n\nAlpha body."


def test_splitter_exposes_body_without_common_headings_for_multi_entry_chunk() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=110, merge_below_tokens=0, retain_headings=True),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Root"), (2, "Scope"))
    assert chunks[0].body == "# Root\n\n## Scope\n\n### A\n\nAlpha body.\n\n### B\n\nBeta body."


def test_splitter_exclude_common_headings_drops_shared_prefix() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=110,
            merge_below_tokens=0,
            retain_headings=True,
            include_common_headings=False,
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Root"), (2, "Scope"))
    assert chunks[0].body == "### A\n\nAlpha body.\n\n### B\n\nBeta body."


def test_splitter_exclude_common_headings_single_entry() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=22, merge_below_tokens=0, retain_headings=True, include_common_headings=False
        ),
    )

    chunks = splitter.split(document)

    assert chunks[0].headings == ((1, "Root"), (2, "Scope"), (3, "A"))
    assert chunks[0].body == "Alpha body."


def test_splitter_exclude_common_headings_ignored_when_retain_headings_false() -> None:
    document = MarkdownParser().parse(MULTI_ROOT_FIXTURE, document_title="multi-root.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=200,
            merge_below_tokens=0,
            retain_headings=False,
            include_common_headings=False,
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == "First body.\n\nSecond body."


def test_splitter_body_is_pure_content_when_headings_are_hidden() -> None:
    document = MarkdownParser().parse(MULTI_ROOT_FIXTURE, document_title="multi-root.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=200, merge_below_tokens=0, retain_headings=False),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == "First body.\n\nSecond body."


def test_splitter_body_drops_all_headings_when_headings_are_hidden() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=60, merge_below_tokens=0, retain_headings=False),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == "Alpha body.\n\nBeta body."


def test_splitter_measures_section_token_counts_bottom_up() -> None:
    document = MarkdownParser().parse("# A\n\nBody", document_title="tokens.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=7,
            merge_below_tokens=0,
            retain_headings=True,
            split_oversized_blocks=frozenset(),
        ),
    )

    measured_root = splitter._measure_section(document.root)
    chunks = splitter.split(document)

    measured_section = measured_root.children[0]
    assert measured_section.counts.body == len("Body\n\n")
    assert measured_section.counts.title == len("# A\n\n")
    assert measured_section.counts.subtree == (
        measured_section.counts.title + measured_section.counts.body
    )
    assert not hasattr(document.root.children[0], "body_token_count")
    assert not hasattr(document.root.children[0], "title_token_count")
    assert not hasattr(document.root.children[0], "subtree_token_count")
    assert len(chunks) == 1
    assert chunks[0].body == "# A\n\nBody"
    assert chunks[0].estimated_token_count == 11
    assert chunks[0].token_count == len("# A\n\nBody")


def test_splitter_uses_estimated_tokens_for_budget_decisions() -> None:
    document = MarkdownParser().parse("# A\n\nBody", document_title="estimated.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=7,
            merge_below_tokens=0,
            retain_headings=True,
            split_oversized_blocks=frozenset(),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].estimated_token_count == 11
    assert chunks[0].token_count == 9
    assert chunks[0].estimated_token_count > splitter.options.max_tokens


def test_heading_estimate_counts_title_once_and_marker_as_one_token() -> None:
    document = MarkdownParser().parse("### Cacheable Title\n\nBody", document_title="tokens.md")
    tokenizer = RecordingTokenizer()
    splitter = MarkdownSplitter(
        tokenizer=tokenizer,
        options=SplitOptions(max_tokens=100, merge_below_tokens=0, retain_headings=True),
    )

    measured_root = splitter._measure_section(document.root)

    measured_section = measured_root.children[0]
    assert measured_section.counts.title == len("### Cacheable Title\n\n")
    assert "### Cacheable Title\n\n" in tokenizer.counted


def test_estimated_tokens_follow_heading_visibility_options() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")

    with_headings = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=100, merge_below_tokens=0, retain_headings=True),
    ).split(document)
    without_headings = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=100, merge_below_tokens=0, retain_headings=False),
    ).split(document)
    without_common = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=100,
            merge_below_tokens=0,
            retain_headings=True,
            include_common_headings=False,
        ),
    ).split(document)

    assert with_headings[0].estimated_token_count > without_headings[0].estimated_token_count
    assert with_headings[0].estimated_token_count >= without_common[0].estimated_token_count
    assert without_headings[0].estimated_token_count == 25


def test_splitter_does_not_count_oversized_section_rendering_for_budget_trials() -> None:
    markdown = """# Parent

## One

One body.

## Two

Two body.

## Three

Three body.
"""
    document = MarkdownParser().parse(markdown, document_title="recording.md")
    tokenizer = RecordingTokenizer()
    splitter = MarkdownSplitter(
        tokenizer=tokenizer,
        options=SplitOptions(max_tokens=35, merge_below_tokens=0, retain_headings=True),
    )

    chunks = splitter.split(document)

    oversized_rendering = (
        "# Parent\n\n## One\n\nOne body.\n\n## Two\n\nTwo body.\n\n## Three\n\nThree body."
    )
    assert oversized_rendering not in tokenizer.counted
    assert all(chunk.estimated_token_count <= 35 for chunk in chunks)


def test_section_chunk_estimate_respects_hidden_common_headings_without_entries() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=100,
            merge_below_tokens=0,
            retain_headings=True,
            include_common_headings=False,
        ),
    )
    measured_root = splitter._measure_section(document.root)
    measured_scope = measured_root.children[0].children[0]
    chunk_token_count = measured_scope.counts.subtree - heading_path_token_count(
        splitter.tokenizer, measured_scope.node.path
    )

    assert chunk_token_count == 31


def test_section_chunk_estimate_respects_hidden_headings_without_entries() -> None:
    document = MarkdownParser().parse(THIRD_LEVEL_FIXTURE, document_title="third-level.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=100, merge_below_tokens=0, retain_headings=False),
    )
    measured_root = splitter._measure_section(document.root)
    measured_scope = measured_root.children[0].children[0]

    assert measured_scope.counts.subtree == 25


def test_splitter_adds_overlap_only_for_text_fallback_splits() -> None:
    document = MarkdownParser().parse(
        "alpha beta gamma delta epsilon zeta",
        document_title="overlap.md",
    )
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=16,
            merge_below_tokens=0,
            overlap_tokens=5,
            retain_headings=False,
            merge_small_chunks=False,
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.body for chunk in chunks] == [
        "alpha beta gamma",
        "gamma delta",
        "delta epsilon",
        "zeta",
    ]


def test_splitter_rejects_overlap_budget_that_consumes_the_whole_chunk() -> None:
    document = MarkdownParser().parse("alpha beta", document_title="invalid.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=10, merge_below_tokens=0, overlap_tokens=10),
    )

    try:
        splitter.split(document)
    except ValueError as exc:
        assert str(exc) == "overlap_tokens must be smaller than max_tokens"
    else:
        raise AssertionError("Expected overlap validation to fail")


def test_merge_below_tokens_does_not_merge_past_rendered_budget() -> None:
    document = MarkdownParser().parse(
        "# A\n\n" + "x " * 31 + "\n\ny",
        document_title="merge-budget.md",
    )
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=60,
            merge_below_tokens=10,
            retain_headings=False,
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.token_count for chunk in chunks] == [62, 1]
    assert chunks[1].body == "y"
    assert all(chunk.estimated_token_count <= 60 for chunk in chunks)


def test_merge_below_tokens_only_absorbs_fragment_or_text_piece_tails() -> None:
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=100, merge_below_tokens=10),
    )
    heading_path = ((1, "A"),)
    left = _ChunkDraft(
        entries=[
            _Entry(
                headings=heading_path,
                body="section body",
                start_line=1,
                end_line=1,
            )
        ],
        token_count=20,
        split_origin="section",
    )
    section_tail = _ChunkDraft(
        entries=[
            _Entry(
                headings=heading_path,
                body="tiny section",
                start_line=2,
                end_line=2,
            )
        ],
        token_count=5,
        split_origin="section",
    )
    fragment_tail = _ChunkDraft(
        entries=[
            _Entry(
                headings=heading_path,
                body="tiny fragment",
                start_line=3,
                end_line=3,
            )
        ],
        token_count=5,
        split_origin="fragment",
    )
    text_piece_tail = _ChunkDraft(
        entries=[
            _Entry(
                headings=heading_path,
                body="tiny text",
                start_line=4,
                end_line=4,
            )
        ],
        token_count=5,
        split_origin="text_piece",
    )

    assert splitter._merge_small_chunks([left, section_tail]) == [left, section_tail]
    assert len(splitter._merge_small_chunks([left, fragment_tail])[0].entries) == 2
    assert len(splitter._merge_small_chunks([left, text_piece_tail])[0].entries) == 2


def test_splitter_keeps_oversized_lists_intact_by_default() -> None:
    document = MarkdownParser().parse(LIST_FIXTURE, document_title="list.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=20, merge_below_tokens=0, retain_headings=False),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == LIST_FIXTURE.strip()
    assert chunks[0].token_count > 20


def test_splitter_can_split_oversized_lists_when_enabled() -> None:
    document = MarkdownParser().parse(LIST_FIXTURE, document_title="list.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=20,
            merge_below_tokens=0,
            retain_headings=False,
            merge_small_chunks=False,
            split_oversized_blocks=frozenset({"list"}),
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.body for chunk in chunks] == [
        "- alpha alpha alpha",
        "alpha",
        "- beta beta beta",
        "beta",
        "- gamma gamma gamma",
        "gamma",
    ]
    assert all(chunk.estimated_token_count <= 20 for chunk in chunks)


def test_splitter_can_split_oversized_code_fences_when_enabled() -> None:
    document = MarkdownParser().parse(CODE_FENCE_FIXTURE, document_title="code.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=28,
            merge_below_tokens=0,
            retain_headings=False,
            merge_small_chunks=False,
            split_oversized_blocks=frozenset({"code_fence"}),
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.body for chunk in chunks] == [
        '```python\nprint("alpha")\n```',
        '```python\nprint("beta")\n```',
        '```python\nprint("gamma")\n```',
    ]
    assert all(chunk.estimated_token_count <= 28 for chunk in chunks)


def test_splitter_never_splits_oversized_urls() -> None:
    document = MarkdownParser().parse(LONG_URL_FIXTURE, document_title="url.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            merge_below_tokens=0,
            retain_headings=False,
            merge_small_chunks=False,
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == LONG_URL_FIXTURE
    assert chunks[0].token_count > 30


FRONT_MATTER_FIXTURE = """---
title: Test Document
author: Alice
date: 2024-01-01
---

# Introduction

This is the introduction.

# Body

Body content here.
"""


def test_front_matter_isolated_as_first_chunk_by_default() -> None:
    document = MarkdownParser().parse(FRONT_MATTER_FIXTURE, document_title="doc.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            isolate_front_matter=True,
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) >= 2
    assert chunks[0].chunk_id == "chunk-0000"
    assert chunks[0].chunk_type == "front_matter"
    assert chunks[0].body == "---\ntitle: Test Document\nauthor: Alice\ndate: 2024-01-01\n---"
    assert chunks[0].headings == ()
    assert chunks[0].section_level == 0
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 5


def test_front_matter_included_normally_when_isolation_disabled() -> None:
    document = MarkdownParser().parse(FRONT_MATTER_FIXTURE, document_title="doc.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            isolate_front_matter=False,
        ),
    )

    chunks = splitter.split(document)

    assert chunks[0].chunk_id == "chunk-0001"
    assert chunks[0].chunk_id != "chunk-0000"
    assert chunks[0].chunk_type == "paragraph"


def test_no_front_matter_works_normally() -> None:
    document = MarkdownParser().parse("# Just a heading\n\nSome text.", document_title="doc.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            isolate_front_matter=True,
        ),
    )

    chunks = splitter.split(document)

    assert chunks[0].chunk_id == "chunk-0001"
    assert "Just a heading" in chunks[0].body


THEMATIC_BREAK_FIXTURE = """# Section

First paragraph.

---

Second paragraph.
"""


def test_thematic_break_never_appears_as_standalone_chunk() -> None:
    document = MarkdownParser().parse(THEMATIC_BREAK_FIXTURE, document_title="hr.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=500, merge_below_tokens=0, retain_headings=False),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert "---" in chunks[0].body
    assert "First paragraph." in chunks[0].body
    assert "Second paragraph." in chunks[0].body


def test_thematic_break_sticks_to_neighbor_at_chunk_boundary() -> None:
    """Even with a tight budget, the thematic_break is not emitted alone."""
    document = MarkdownParser().parse(THEMATIC_BREAK_FIXTURE, document_title="hr.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=40,
            merge_below_tokens=0,
            retain_headings=True,
            merge_small_chunks=False,
        ),
    )

    chunks = splitter.split(document)

    assert any("---" in chunk.body for chunk in chunks)
    assert all(chunk.body.strip() != "---" for chunk in chunks)


def test_thematic_break_at_document_start_stays_standalone() -> None:
    md = "---\n\nParagraph text."
    document = MarkdownParser().parse(md, document_title="hr-first.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=500, merge_below_tokens=0, retain_headings=False),
    )

    chunks = splitter.split(document)
    assert len(chunks) == 1
    assert "---" in chunks[0].body


def test_thematic_break_after_front_matter_stays_in_body_content() -> None:
    md = "---\ntitle: T\n---\n\n---\n\nBody"
    chunks = lumber(md, max_tokens=100, merge_below_tokens=0, retain_headings=False)

    assert chunks[0].chunk_type == "front_matter"
    assert chunks[0].body == "---\ntitle: T\n---"
    assert "---" in chunks[1].body
    assert "Body" in chunks[1].body


def test_thematic_break_after_split_list_is_preserved() -> None:
    md = f"- {'a' * 40}\n- {'b' * 40}\n\n---\n\nAfter"
    chunks = lumber(
        md,
        max_tokens=50,
        merge_below_tokens=0,
        retain_headings=False,
        split_oversized_blocks={"list", "paragraph"},
    )

    assert any("---" in chunk.body for chunk in chunks)
    assert all(chunk.body.strip() != "---" for chunk in chunks)


EMPTY_SECTION_FIXTURE = """# Getting Started

This guide walks you through the basics of using our platform.

## Installation

## Troubleshooting

If you encounter issues, check the following.
"""


def test_empty_section_discarded_when_retain_headings_false() -> None:
    """Heading-only chunks always discarded when retain_headings=False (0 tokens)."""
    document = MarkdownParser().parse(EMPTY_SECTION_FIXTURE, document_title="empty-section.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=500, merge_below_tokens=0, retain_headings=False),
    )

    chunks = splitter.split(document)

    assert all(chunk.body.strip() for chunk in chunks)
    assert "This guide walks you through the basics" in chunks[0].body
    assert "If you encounter issues" in chunks[0].body


def test_empty_section_discarded_by_default_with_retain_headings() -> None:
    """Heading-only chunks discarded by default (skip_empty_sections=True)."""
    document = MarkdownParser().parse(EMPTY_SECTION_FIXTURE, document_title="empty-section.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=50,
            merge_below_tokens=0,
            retain_headings=True,
            skip_empty_sections=True,
        ),
    )

    chunks = splitter.split(document)

    assert all(chunk.body.strip() for chunk in chunks)
    assert not any(
        chunk.headings == ((1, "Getting Started"), (2, "Installation")) for chunk in chunks
    )


def test_empty_section_kept_when_skip_empty_sections_false() -> None:
    """Heading-only chunks kept when skip_empty_sections=False and retain_headings=True."""
    document = MarkdownParser().parse(EMPTY_SECTION_FIXTURE, document_title="empty-section.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            retain_headings=True,
            skip_empty_sections=False,
        ),
    )

    chunks = splitter.split(document)

    assert any("## Installation" in chunk.body for chunk in chunks)


def test_empty_section_discarded_even_with_skip_false_when_retain_headings_false() -> None:
    """Zero-token chunks always discarded regardless of skip_empty_sections."""
    document = MarkdownParser().parse(EMPTY_SECTION_FIXTURE, document_title="empty-section.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            retain_headings=False,
            skip_empty_sections=False,
        ),
    )

    chunks = splitter.split(document)

    assert all(chunk.body.strip() for chunk in chunks)
    assert not any("Installation" in chunk.body for chunk in chunks)


def test_empty_section_between_non_empty_sections_is_skipped() -> None:
    document = MarkdownParser().parse(EMPTY_SECTION_FIXTURE, document_title="empty-section.md")
    splitter = MarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=50,
            merge_below_tokens=0,
            retain_headings=True,
        ),
    )

    chunks = splitter.split(document)

    assert all(chunk.body.strip() for chunk in chunks)

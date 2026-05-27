from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from lumberjack.api import lumber
from lumberjack.core.parser import MarkdownParser
from lumberjack.core.splitter import (
    RecursiveMarkdownSplitter,
    SectionMarkdownSplitter,
    _ChunkDraft,
    _Entry,
    create_splitter,
)
from lumberjack.core.tokenizers import SimpleCharTokenizer
from lumberjack.models import SplitOptions

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "markdown" / "sample.md"
).read_text(encoding="utf-8")

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

LONG_URL_FIXTURE = "See https://example.com/really/long/path/that/should/not/be/split/in/chunks for details."

HEADING_SPLITTER_FIXTURE = """# Parent

Parent intro.

## One

One body.

## Two

Two body.
"""

HEADING_OVERSIZED_FIXTURE = """# Long

Alpha bravo charlie delta echo foxtrot golf hotel india juliet.
"""


class RecordingTokenizer(SimpleCharTokenizer):
    def __init__(self) -> None:
        self.counted: list[str] = []

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        self.counted.append(text)
        return super().count(text)


def test_splitter_preserves_heading_context() -> None:
    """Test that splitter preserves heading hierarchy in chunks."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=140, merge_below_tokens=20),
    )
    chunks = splitter.split(document)

    assert len(chunks) >= 2
    assert any("# Overview" in chunk.body for chunk in chunks)
    assert any("## Details" in chunk.body for chunk in chunks)


def test_create_splitter_routes_semantic_default_and_heading() -> None:
    options = SplitOptions(max_tokens=100, merge_below_tokens=0)

    assert isinstance(
        create_splitter("recursive", SimpleCharTokenizer(), options),
        RecursiveMarkdownSplitter,
    )
    assert isinstance(
        create_splitter("default", SimpleCharTokenizer(), options),
        RecursiveMarkdownSplitter,
    )
    assert isinstance(
        create_splitter("section", SimpleCharTokenizer(), options),
        SectionMarkdownSplitter,
    )
    assert not issubclass(SectionMarkdownSplitter, RecursiveMarkdownSplitter)


def test_heading_splitter_keeps_sections_separate_without_repeating_children() -> None:
    document = MarkdownParser().parse(
        HEADING_SPLITTER_FIXTURE, document_title="heading.md"
    )
    splitter = SectionMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert [chunk.headings for chunk in chunks] == [
        ((1, "Parent"),),
        ((1, "Parent"), (2, "One")),
        ((1, "Parent"), (2, "Two")),
    ]
    assert chunks[0].body == "# Parent\n\nParent intro."
    assert chunks[1].body == "# Parent\n\n## One\n\nOne body."
    assert chunks[2].body == "# Parent\n\n## Two\n\nTwo body."
    assert "One body." not in chunks[0].body
    assert "Two body." not in chunks[0].body


def test_heading_splitter_keeps_oversized_section_intact_by_default() -> None:
    document = MarkdownParser().parse(
        HEADING_OVERSIZED_FIXTURE, document_title="heading.md"
    )
    splitter = SectionMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=25,
            merge_below_tokens=0,
            split_oversized_blocks=frozenset({"paragraph"}),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Long"),)
    assert chunks[0].estimated_token_count > splitter.options.max_tokens
    assert "Alpha bravo charlie" in chunks[0].body


def test_heading_splitter_recursively_splits_oversized_section_body() -> None:
    document = MarkdownParser().parse(
        HEADING_OVERSIZED_FIXTURE, document_title="heading.md"
    )
    splitter = SectionMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=35,
            merge_below_tokens=0,
            recursive_split=True,
            split_oversized_blocks=frozenset({"paragraph"}),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) > 1
    assert all(chunk.headings == ((1, "Long"),) for chunk in chunks)
    assert all(chunk.body.startswith("# Long\n\n") for chunk in chunks)
    assert "Alpha bravo" in chunks[0].body
    assert "juliet." in chunks[-1].body


def test_heading_splitter_respects_empty_section_options() -> None:
    document = MarkdownParser().parse("# Empty\n\n## Child\n\nChild body.")

    default_chunks = SectionMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    ).split(document)
    kept_chunks = SectionMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=0,
            skip_empty_sections=False,
        ),
    ).split(document)
    assert [chunk.headings for chunk in default_chunks] == [
        ((1, "Empty"), (2, "Child")),
    ]
    assert [chunk.headings for chunk in kept_chunks] == [
        ((1, "Empty"),),
        ((1, "Empty"), (2, "Child")),
    ]
    assert kept_chunks[0].body == "# Empty"


def test_splitter_respects_budget_except_unsplittable_code_fence() -> None:
    """Test that splitter respects token budget except for code fences."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=180, merge_below_tokens=20),
    )
    chunks = splitter.split(document)

    oversized = [chunk for chunk in chunks if chunk.estimated_token_count > 180]
    if oversized:
        assert all("```" in chunk.body for chunk in oversized)


def test_splitter_deduplicates_shared_parent_heading_in_merged_chunk() -> None:
    document = MarkdownParser().parse(
        MERGED_SECTION_FIXTURE, document_title="development.md"
    )
    splitter = RecursiveMarkdownSplitter(
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


def test_split_options_no_longer_exposes_render_common_headings() -> None:
    option_names = {field.name for field in fields(SplitOptions)}

    assert "render_common_headings" not in option_names


def test_splitter_recursively_descends_heading_levels_when_section_is_oversized() -> (
    None
):
    document = MarkdownParser().parse(
        RECURSIVE_SECTION_FIXTURE, document_title="recursive.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=90, merge_below_tokens=80),
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


def test_splitter_checks_whole_document_before_splitting_by_top_level_headings() -> (
    None
):
    document = MarkdownParser().parse(
        MULTI_ROOT_FIXTURE, document_title="multi-root.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=200, merge_below_tokens=20),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == "# First\n\nFirst body.\n\n# Second\n\nSecond body."


def test_splitter_greedily_merges_same_level_siblings_before_descending() -> None:
    document = MarkdownParser().parse(
        GREEDY_SIBLING_FIXTURE, document_title="siblings.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=62, merge_below_tokens=20),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 2
    assert chunks[0].body == "# Parent\n\n## One\n\nOne body.\n\n## Two\n\nTwo body."
    assert chunks[1].body == "# Parent\n\n## Three\n\nThree body is a little longer."
    assert all(chunk.estimated_token_count <= 60 for chunk in chunks)


def test_splitter_exposes_body_without_common_headings_for_single_leaf_chunk() -> None:
    document = MarkdownParser().parse(
        THIRD_LEVEL_FIXTURE, document_title="third-level.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=40, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert chunks[0].headings == ((1, "Root"), (2, "Scope"), (3, "A"))
    assert chunks[0].body == "# Root\n\n## Scope\n\n### A\n\nAlpha body."


def test_splitter_exposes_body_without_common_headings_for_multi_entry_chunk() -> None:
    document = MarkdownParser().parse(
        THIRD_LEVEL_FIXTURE, document_title="third-level.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=110, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Root"), (2, "Scope"))
    assert (
        chunks[0].body
        == "# Root\n\n## Scope\n\n### A\n\nAlpha body.\n\n### B\n\nBeta body."
    )


def test_splitter_body_includes_headings_by_default() -> None:
    document = MarkdownParser().parse(
        MULTI_ROOT_FIXTURE, document_title="multi-root.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=200, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == "# First\n\nFirst body.\n\n# Second\n\nSecond body."


def test_splitter_body_includes_nested_headings_by_default() -> None:
    document = MarkdownParser().parse(
        THIRD_LEVEL_FIXTURE, document_title="third-level.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=60,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=0,
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == (
        "# Root\n\n## Scope\n\n### A\n\nAlpha body.\n\n### B\n\nBeta body."
    )


def test_splitter_measures_section_token_counts_bottom_up() -> None:
    document = MarkdownParser().parse("# A\n\nBody", document_title="tokens.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=7,
            merge_below_tokens=0,
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
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=7,
            merge_below_tokens=0,
            split_oversized_blocks=frozenset(),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].estimated_token_count == 11
    assert chunks[0].token_count == 9
    assert chunks[0].estimated_token_count > splitter.options.max_tokens


def test_heading_estimate_counts_title_once_and_marker_as_one_token() -> None:
    document = MarkdownParser().parse(
        "### Cacheable Title\n\nBody", document_title="tokens.md"
    )
    tokenizer = RecordingTokenizer()
    splitter = RecursiveMarkdownSplitter(
        tokenizer=tokenizer,
        options=SplitOptions(max_tokens=100, merge_below_tokens=0),
    )

    measured_root = splitter._measure_section(document.root)

    measured_section = measured_root.children[0]
    assert measured_section.counts.title == len("### Cacheable Title\n\n")
    assert "### Cacheable Title\n\n" in tokenizer.counted


def test_estimated_tokens_include_rendered_heading_path() -> None:
    document = MarkdownParser().parse(
        THIRD_LEVEL_FIXTURE, document_title="third-level.md"
    )

    chunks = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=100, merge_below_tokens=0),
    ).split(document)

    assert chunks[0].body.startswith("# Root\n\n## Scope\n\n")
    assert chunks[0].estimated_token_count >= chunks[0].token_count


def test_splitter_does_not_count_oversized_section_rendering_for_budget_trials() -> (
    None
):
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
    splitter = RecursiveMarkdownSplitter(
        tokenizer=tokenizer,
        options=SplitOptions(max_tokens=35, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    oversized_rendering = "# Parent\n\n## One\n\nOne body.\n\n## Two\n\nTwo body.\n\n## Three\n\nThree body."
    assert oversized_rendering not in tokenizer.counted
    assert all(chunk.estimated_token_count <= 35 for chunk in chunks)


def test_section_chunk_estimate_includes_heading_tokens_without_entries() -> None:
    document = MarkdownParser().parse(
        THIRD_LEVEL_FIXTURE, document_title="third-level.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=100, merge_below_tokens=0),
    )
    measured_root = splitter._measure_section(document.root)
    measured_scope = measured_root.children[0].children[0]

    assert measured_scope.counts.subtree == 49


def test_measured_section_caches_single_chunk_eligibility_from_standalone_blocks() -> (
    None
):
    document = MarkdownParser().parse(
        """# Root

Intro.

## Plain

Plain body.

## With Table

| Data |
|------|
| val  |
""",
        document_title="standalone-cache.md",
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            standalone_blocks=frozenset({"table"}),
        ),
    )

    measured_root = splitter._measure_section(document.root)
    measured_h1 = measured_root.children[0]
    measured_plain = measured_h1.children[0]
    measured_table = measured_h1.children[1]

    assert measured_plain.can_emit_as_single_chunk is True
    assert measured_table.can_emit_as_single_chunk is False
    assert measured_h1.can_emit_as_single_chunk is False
    assert measured_root.can_emit_as_single_chunk is False

    disabled_splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            standalone_blocks=frozenset(),
        ),
    )

    measured_disabled_root = disabled_splitter._measure_section(document.root)

    assert measured_disabled_root.can_emit_as_single_chunk is True
    assert (
        measured_disabled_root.children[0].children[1].can_emit_as_single_chunk is True
    )


def test_splitter_adds_overlap_only_for_text_fallback_splits() -> None:
    document = MarkdownParser().parse(
        "alpha beta gamma delta epsilon zeta",
        document_title="overlap.md",
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=16,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=0,
            overlap_tokens=5,
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
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=10, merge_below_tokens=0, overlap_tokens=10),
    )

    try:
        splitter.split(document)
    except ValueError as exc:
        assert str(exc) == "overlap_tokens (10) must be smaller than ideal_max_tokens (8)"
    else:
        raise AssertionError("Expected overlap validation to fail")


def test_splitter_rejects_invalid_ideal_max_tokens_ratio() -> None:
    document = MarkdownParser().parse("alpha beta", document_title="invalid.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=10, ideal_max_tokens_ratio=0),
    )

    try:
        splitter.split(document)
    except ValueError as exc:
        assert str(exc) == "ideal_max_tokens_ratio must be greater than 0 and at most 1"
    else:
        raise AssertionError("Expected ideal_max_tokens_ratio validation to fail")


def test_splitter_rejects_overlap_budget_that_consumes_ideal_chunk() -> None:
    document = MarkdownParser().parse("alpha beta", document_title="invalid.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=20,
            ideal_max_tokens_ratio=0.5,
            merge_below_tokens=0,
            overlap_tokens=10,
        ),
    )

    try:
        splitter.split(document)
    except ValueError as exc:
        assert str(exc) == "overlap_tokens (10) must be smaller than ideal_max_tokens (10)"
    else:
        raise AssertionError("Expected overlap validation to fail")


def test_recursive_splitter_uses_ideal_budget_for_initial_splitting() -> None:
    document = MarkdownParser().parse(
        "# A\n\nalpha1\n\nbravo2",
        document_title="ideal-budget.md",
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            ideal_max_tokens_ratio=0.5,
            merge_below_tokens=0,
            merge_small_chunks=False,
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.body for chunk in chunks] == [
        "# A\n\nalpha1",
        "# A\n\nbravo2",
    ]
    assert all(chunk.token_count <= 15 for chunk in chunks)


def test_merge_small_chunks_can_exceed_ideal_budget_up_to_max_tokens() -> None:
    document = MarkdownParser().parse(
        "# A\n\nalpha1\n\nbravo2",
        document_title="ideal-budget.md",
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            ideal_max_tokens_ratio=0.5,
            merge_below_tokens=29,
            merge_small_chunks=True,
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.body for chunk in chunks] == ["# A\n\nalpha1\n\nbravo2"]
    assert 15 < chunks[0].token_count <= 30


def test_merge_small_chunks_combines_sibling_sections_with_same_parent() -> None:
    document = MarkdownParser().parse(
        "# Parent\n\n## One\n\nA\n\n## Two\n\nB",
        document_title="same-parent.md",
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=40,
            ideal_max_tokens_ratio=0.5,
            merge_below_tokens=39,
            merge_small_chunks=True,
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.body for chunk in chunks] == [
        "# Parent\n\n## One\n\nA\n\n## Two\n\nB"
    ]
    assert 20 < chunks[0].token_count <= 40


def test_merge_below_tokens_does_not_merge_past_rendered_budget() -> None:
    document = MarkdownParser().parse(
        "# A\n\n" + "x " * 31 + "\n\ny",
        document_title="merge-budget.md",
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=60,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=10,
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.token_count for chunk in chunks] == [60, 13]
    assert chunks[1].body == "# A\n\nx x x\n\ny"
    assert all(chunk.estimated_token_count <= 60 for chunk in chunks)


def test_merge_below_tokens_absorbs_same_parent_paragraph_tails() -> None:
    splitter = RecursiveMarkdownSplitter(
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

    assert len(splitter._merge_small_chunks([left, section_tail])[0].entries) == 2
    assert len(splitter._merge_small_chunks([left, fragment_tail])[0].entries) == 2
    assert len(splitter._merge_small_chunks([left, text_piece_tail])[0].entries) == 2


def test_splitter_keeps_oversized_lists_intact_by_default() -> None:
    document = MarkdownParser().parse(LIST_FIXTURE, document_title="list.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=20, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == LIST_FIXTURE.strip()
    assert chunks[0].token_count > 20


def test_splitter_can_split_oversized_lists_when_enabled() -> None:
    document = MarkdownParser().parse(LIST_FIXTURE, document_title="list.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=20,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=0,
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
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=28,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=0,
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
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            merge_below_tokens=0,
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
    splitter = RecursiveMarkdownSplitter(
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
    assert (
        chunks[0].body
        == "---\ntitle: Test Document\nauthor: Alice\ndate: 2024-01-01\n---"
    )
    assert chunks[0].headings == ()
    assert chunks[0].section_level == 0
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 5


def test_heading_splitter_isolates_front_matter_before_heading_chunks() -> None:
    document = MarkdownParser().parse(FRONT_MATTER_FIXTURE, document_title="doc.md")
    splitter = SectionMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=500, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert chunks[0].chunk_type == "front_matter"
    assert chunks[0].chunk_id == "chunk-0000"
    assert [chunk.headings for chunk in chunks[1:]] == [
        ((1, "Introduction"),),
        ((1, "Body"),),
    ]


def test_front_matter_included_normally_when_isolation_disabled() -> None:
    document = MarkdownParser().parse(FRONT_MATTER_FIXTURE, document_title="doc.md")
    splitter = RecursiveMarkdownSplitter(
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
    document = MarkdownParser().parse(
        "# Just a heading\n\nSome text.", document_title="doc.md"
    )
    splitter = RecursiveMarkdownSplitter(
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


def test_thematic_break_is_ignored_in_chunk_body() -> None:
    document = MarkdownParser().parse(THEMATIC_BREAK_FIXTURE, document_title="hr.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=500, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert "---" not in chunks[0].body
    assert "First paragraph." in chunks[0].body
    assert "Second paragraph." in chunks[0].body


def test_thematic_break_is_ignored_at_chunk_boundary() -> None:
    document = MarkdownParser().parse(THEMATIC_BREAK_FIXTURE, document_title="hr.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=40,
            merge_below_tokens=0,
            merge_small_chunks=False,
        ),
    )

    chunks = splitter.split(document)

    assert not any("---" in chunk.body for chunk in chunks)
    assert all(chunk.body.strip() != "---" for chunk in chunks)


def test_thematic_break_at_document_start_is_ignored() -> None:
    md = "---\n\nParagraph text."
    document = MarkdownParser().parse(md, document_title="hr-first.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=500, merge_below_tokens=0),
    )

    chunks = splitter.split(document)
    assert len(chunks) == 1
    assert "---" not in chunks[0].body
    assert "Paragraph text." in chunks[0].body


def test_thematic_break_after_front_matter_is_ignored_in_body_content() -> None:
    md = "---\ntitle: T\n---\n\n---\n\nBody"
    chunks = lumber(md, max_tokens=100, merge_below_tokens=0)

    assert chunks[0].chunk_type == "front_matter"
    assert chunks[0].body == "---\ntitle: T\n---"
    assert "---" not in chunks[1].body
    assert "Body" in chunks[1].body


def test_thematic_break_after_split_list_is_ignored() -> None:
    md = f"- {'a' * 40}\n- {'b' * 40}\n\n---\n\nAfter"
    chunks = lumber(
        md,
        max_tokens=50,
        merge_below_tokens=0,
        split_oversized_blocks={"list", "paragraph"},
    )

    assert not any("---" in chunk.body for chunk in chunks)
    assert all(chunk.body.strip() != "---" for chunk in chunks)


EMPTY_SECTION_FIXTURE = """# Getting Started

This guide walks you through the basics of using our platform.

## Installation

## Troubleshooting

If you encounter issues, check the following.
"""


def test_empty_section_discarded_by_default() -> None:
    """Heading-only chunks are discarded by default."""
    document = MarkdownParser().parse(
        EMPTY_SECTION_FIXTURE, document_title="empty-section.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(max_tokens=500, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert all(chunk.body.strip() for chunk in chunks)
    assert "This guide walks you through the basics" in chunks[0].body
    assert "If you encounter issues" in chunks[0].body


def test_empty_section_discarded_by_default_with_headings() -> None:
    """Heading-only chunks discarded by default (skip_empty_sections=True)."""
    document = MarkdownParser().parse(
        EMPTY_SECTION_FIXTURE, document_title="empty-section.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=50,
            merge_below_tokens=0,
            skip_empty_sections=True,
        ),
    )

    chunks = splitter.split(document)

    assert all(chunk.body.strip() for chunk in chunks)
    assert not any(
        chunk.headings == ((1, "Getting Started"), (2, "Installation"))
        for chunk in chunks
    )


def test_empty_section_kept_when_skip_empty_sections_false() -> None:
    """Heading-only chunks kept when skip_empty_sections=False."""
    document = MarkdownParser().parse(
        EMPTY_SECTION_FIXTURE, document_title="empty-section.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            skip_empty_sections=False,
        ),
    )

    chunks = splitter.split(document)

    assert any("## Installation" in chunk.body for chunk in chunks)


def test_empty_section_kept_with_skip_false() -> None:
    """Heading-only chunks are kept when skip_empty_sections=False."""
    document = MarkdownParser().parse(
        EMPTY_SECTION_FIXTURE, document_title="empty-section.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            skip_empty_sections=False,
        ),
    )

    chunks = splitter.split(document)

    assert all(chunk.body.strip() for chunk in chunks)
    assert any("Installation" in chunk.body for chunk in chunks)


def test_empty_section_between_non_empty_sections_is_skipped() -> None:
    document = MarkdownParser().parse(
        EMPTY_SECTION_FIXTURE, document_title="empty-section.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=50,
            merge_below_tokens=0,
        ),
    )

    chunks = splitter.split(document)

    assert all(chunk.body.strip() for chunk in chunks)


# --- standalone_blocks tests ---


STANDALONE_TABLE_FIXTURE = """# Doc

Intro paragraph.

| A | B |
|---|---|
| 1 | 2 |

Outro paragraph.
"""

STANDALONE_CODE_FENCE_IN_SECTION = """# Doc

## Section

Some text before.

```python
print("hello")
```

Some text after.
"""


def test_standalone_table_is_isolated_even_when_budget_allows_merge() -> None:
    """Table is emitted as its own chunk even when whole doc fits in budget."""
    document = MarkdownParser().parse(
        STANDALONE_TABLE_FIXTURE, document_title="standalone.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=0,
            standalone_blocks=frozenset({"table"}),
        ),
    )

    chunks = splitter.split(document)

    types = [c.chunk_type for c in chunks]
    assert "table" in types
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) == 1
    assert "| A | B |" in table_chunks[0].body
    assert "Intro paragraph." not in table_chunks[0].body
    assert "Outro paragraph." not in table_chunks[0].body
    assert any("Intro" in c.body for c in chunks)
    assert any("Outro" in c.body for c in chunks)


def test_standalone_blocks_empty_frozenset_restores_merge_behavior() -> None:
    """Empty standalone_blocks merges table back with paragraphs."""
    document = MarkdownParser().parse(
        STANDALONE_TABLE_FIXTURE, document_title="standalone.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=0,
            standalone_blocks=frozenset(),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert "Intro paragraph." in chunks[0].body
    assert "| A | B |" in chunks[0].body
    assert "Outro paragraph." in chunks[0].body
    assert chunks[0].chunk_type == "paragraph"


def test_standalone_chunk_not_merged_by_merge_small_chunks() -> None:
    """Small standalone chunks are not merged back into adjacent paragraphs."""
    document = MarkdownParser().parse(
        STANDALONE_CODE_FENCE_IN_SECTION, document_title="standalone.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=100,
            merge_small_chunks=True,
            standalone_blocks=frozenset({"code_fence"}),
        ),
    )

    chunks = splitter.split(document)

    code_chunks = [c for c in chunks if c.chunk_type == "code_fence"]
    assert len(code_chunks) == 1
    assert 'print("hello")' in code_chunks[0].body
    assert "Some text before." not in code_chunks[0].body
    assert "Some text after." not in code_chunks[0].body


def test_oversized_standalone_code_fence_with_split_oversized() -> None:
    """Oversized standalone code fence splits into independent code chunks."""
    long_code = "```python\n" + "\n".join(f"line{i}" for i in range(30)) + "\n```"
    md = f"# Code\n\n{long_code}"
    document = MarkdownParser().parse(md, document_title="code.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=50,
            merge_below_tokens=0,
            merge_small_chunks=False,
            standalone_blocks=frozenset({"code_fence"}),
            split_oversized_blocks=frozenset({"code_fence"}),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) > 1
    assert all(c.chunk_type == "code_fence" for c in chunks)
    assert all("```python" in c.body for c in chunks)
    assert all(c.body.endswith("```") for c in chunks)


def test_oversized_standalone_code_fence_without_split_stays_intact() -> None:
    """Oversized standalone code fence stays as one chunk when split_oversized_blocks is empty."""
    long_code = "```python\n" + "\n".join(f"line{i}" for i in range(30)) + "\n```"
    md = f"# Code\n\n{long_code}"
    document = MarkdownParser().parse(md, document_title="code.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=50,
            merge_below_tokens=0,
            standalone_blocks=frozenset({"code_fence"}),
            split_oversized_blocks=frozenset(),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "code_fence"
    assert chunks[0].estimated_token_count > 50


def test_section_splitter_isolates_standalone_blocks_in_body() -> None:
    """SectionMarkdownSplitter isolates standalone blocks from direct body."""
    md = """# Doc

Intro.

| A |
|---|
| 1 |

Outro.

## Child

Child body.
"""
    document = MarkdownParser().parse(md, document_title="section.md")
    splitter = SectionMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=0,
            standalone_blocks=frozenset({"table"}),
        ),
    )

    chunks = splitter.split(document)

    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) == 1
    assert "| A |" in table_chunks[0].body
    assert "Intro." not in table_chunks[0].body
    assert any("Child body." in c.body for c in chunks)


def test_standalone_block_preserves_heading_context() -> None:
    """Standalone chunk retains heading breadcrumbs."""
    document = MarkdownParser().parse(
        STANDALONE_CODE_FENCE_IN_SECTION, document_title="headings.md"
    )
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=0,
            standalone_blocks=frozenset({"code_fence"}),
        ),
    )

    chunks = splitter.split(document)
    code_chunks = [c for c in chunks if c.chunk_type == "code_fence"]

    assert len(code_chunks) == 1
    assert code_chunks[0].headings == ((1, "Doc"), (2, "Section"))


def test_standalone_blocks_in_nested_section_tree() -> None:
    """Standalone blocks in nested children prevent whole-tree merge."""
    md = """# Root

## Parent

Parent intro.

### Child

| Data |
|------|
| val  |

"""
    document = MarkdownParser().parse(md, document_title="nested.md")
    splitter = RecursiveMarkdownSplitter(
        tokenizer=SimpleCharTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            standalone_blocks=frozenset({"table"}),
        ),
    )

    chunks = splitter.split(document)

    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) == 1
    assert "Parent intro." not in table_chunks[0].body

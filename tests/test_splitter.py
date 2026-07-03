from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from lumberjack import lumber
from lumberjack.core.models import (
    BaseParams,
    ChunkDraft,
    Entry,
    SplitOptions,
    TableBlockParams,
)
from lumberjack.core.options import resolve_block_options
from lumberjack.core.parsers.markdown.parser import MarkdownParser
from lumberjack.core.splitters import (
    IncrementalRecursiveSplitter,
    IncrementalSectionSplitter,
    RecursiveSplitter,
    SectionSplitter,
    create_splitter,
)
from tests.helpers import CharacterTokenizer

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


class RecordingTokenizer(CharacterTokenizer):
    """Records every ``count`` argument; drives the incremental split path."""

    def __init__(self) -> None:
        self.counted: list[str] = []

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        self.counted.append(text)
        return super().count(text)


def markdown_block_options(
    overrides: dict[str, BaseParams] | None = None,
) -> dict[str, BaseParams]:
    return resolve_block_options(MarkdownParser().block_kinds, overrides)


def test_splitter_preserves_heading_context() -> None:
    """Test that splitter preserves heading hierarchy in chunks."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=140, merge_below_tokens=20),
    )
    chunks = splitter.split(document)

    assert len(chunks) >= 2
    assert any("# Overview" in chunk.body for chunk in chunks)
    assert any("## Details" in chunk.body for chunk in chunks)


def test_create_splitter_routes_recursive_and_section() -> None:
    options = SplitOptions(max_tokens=100, merge_below_tokens=0)

    assert isinstance(
        create_splitter("recursive", CharacterTokenizer(), options),
        RecursiveSplitter,
    )
    assert isinstance(
        create_splitter("section", CharacterTokenizer(), options),
        SectionSplitter,
    )
    assert not issubclass(SectionSplitter, RecursiveSplitter)


def test_heading_splitter_merges_small_subtree_into_one_chunk() -> None:
    """A small subtree collapses into one chunk; children render once each."""
    document = MarkdownParser().parse(
        HEADING_SPLITTER_FIXTURE, document_title="heading.md"
    )
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Parent"),)
    # Common parent breadcrumb renders once; each child renders once.
    assert chunks[0].body.count("# Parent") == 1
    assert chunks[0].body.count("## One") == 1
    assert chunks[0].body.count("## Two") == 1
    assert "Parent intro." in chunks[0].body
    assert "One body." in chunks[0].body
    assert "Two body." in chunks[0].body


def test_heading_splitter_splits_oversized_section_body() -> None:
    document = MarkdownParser().parse(
        HEADING_OVERSIZED_FIXTURE, document_title="heading.md"
    )
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=35,
            merge_below_tokens=0,
            block_options={"paragraph": BaseParams()},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) > 1
    assert all(chunk.headings == () for chunk in chunks)
    assert all(chunk.section_level == 1 for chunk in chunks)
    assert all(chunk.body.startswith("# Long\n\n") for chunk in chunks)
    assert "Alpha bravo" in chunks[0].body
    assert "juliet." in chunks[-1].body


def test_heading_splitter_splits_oversized_body_with_nosplit_blocks_kept_intact() -> (
    None
):
    """SectionSplitter respects nosplit block options for oversized bodies."""
    document = MarkdownParser().parse(
        HEADING_OVERSIZED_FIXTURE, document_title="heading.md"
    )
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=35,
            merge_below_tokens=0,
            block_options={"paragraph": BaseParams(split=False)},
        ),
    )

    chunks = splitter.split(document)

    # Paragraph is nosplit so the oversized body stays as one chunk
    assert len(chunks) == 1
    assert chunks[0].headings == ()
    assert chunks[0].section_level == 1
    assert chunks[0].estimated_token_count > splitter.options.max_tokens
    assert "Alpha bravo charlie" in chunks[0].body


def test_heading_splitter_respects_empty_section_options() -> None:
    document = MarkdownParser().parse("# Empty\n\n## Child\n\nChild body.")

    default_chunks = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    ).split(document)
    kept_chunks = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=0,
            skip_empty_sections=False,
        ),
    ).split(document)

    # The small subtree collapses to one chunk in both cases.  ``# Empty``
    # has no body of its own, so the only entry is ``## Child`` and the
    # chunk metadata exposes that entry's ancestor path.
    assert [chunk.headings for chunk in default_chunks] == [((1, "Empty"),)]
    assert [chunk.headings for chunk in kept_chunks] == [((1, "Empty"),)]
    assert "# Empty" in kept_chunks[0].body
    assert "## Child" in kept_chunks[0].body
    assert "Child body." in kept_chunks[0].body


def test_splitter_respects_budget_except_unsplittable_code_fence() -> None:
    """Test that splitter respects token budget except for code fences."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
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
    assert chunks[0].section_level == 3


def test_split_options_no_longer_exposes_render_common_headings() -> None:
    option_names = {field.name for field in fields(SplitOptions)}

    assert "render_common_headings" not in option_names


def test_split_options_no_longer_exposes_isolate_front_matter() -> None:
    option_names = {field.name for field in fields(SplitOptions)}

    assert "isolate_front_matter" not in option_names


def test_splitter_recursively_descends_heading_levels_when_section_is_oversized() -> (
    None
):
    document = MarkdownParser().parse(
        RECURSIVE_SECTION_FIXTURE, document_title="recursive.md"
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=90, ideal_max_tokens_ratio=1, merge_below_tokens=80
        ),
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=200, merge_below_tokens=20),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == "# First\n\nFirst body.\n\n# Second\n\nSecond body."


def test_splitter_greedily_merges_same_level_siblings_before_descending() -> None:
    document = MarkdownParser().parse(
        GREEDY_SIBLING_FIXTURE, document_title="siblings.md"
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=62, ideal_max_tokens_ratio=1, merge_below_tokens=20
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 2
    assert chunks[0].body == "# Parent\n\n## One\n\nOne body.\n\n## Two\n\nTwo body."
    assert chunks[1].body == "# Parent\n\n## Three\n\nThree body is a little longer."
    assert all(chunk.estimated_token_count <= 62 for chunk in chunks)


def test_splitter_exposes_ancestor_headings_for_single_leaf_chunk() -> None:
    document = MarkdownParser().parse(
        THIRD_LEVEL_FIXTURE, document_title="third-level.md"
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=40, ideal_max_tokens_ratio=1, merge_below_tokens=0
        ),
    )

    chunks = splitter.split(document)

    assert chunks[0].headings == ((1, "Root"), (2, "Scope"))
    assert chunks[0].section_level == 3
    assert chunks[0].body == "# Root\n\n## Scope\n\n### A\n\nAlpha body."


def test_splitter_exposes_common_ancestor_headings_for_multi_entry_chunk() -> None:
    document = MarkdownParser().parse(
        THIRD_LEVEL_FIXTURE, document_title="third-level.md"
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=110, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Root"), (2, "Scope"))
    assert (
        chunks[0].body
        == "# Root\n\n## Scope\n\n### A\n\nAlpha body.\n\n### B\n\nBeta body."
    )


def test_splitter_fragment_uses_ancestor_headings_and_keeps_own_title() -> None:
    document = MarkdownParser().parse(
        THIRD_LEVEL_FIXTURE, document_title="third-level.md"
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=0,
        ),
    )

    chunks = splitter.split(document)

    assert chunks[0].headings == ((1, "Root"), (2, "Scope"))
    assert chunks[0].section_level == 3
    assert chunks[0].body == "# Root\n\n## Scope\n\n### A\n\nAlpha body."


def test_splitter_render_headings_false_keeps_self_title_only() -> None:
    document = MarkdownParser().parse(
        THIRD_LEVEL_FIXTURE, document_title="third-level.md"
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=0,
            render_headings=False,
        ),
    )

    chunks = splitter.split(document)

    assert chunks[0].headings == ((1, "Root"), (2, "Scope"))
    assert chunks[0].section_level == 3
    assert chunks[0].body == "### A\n\nAlpha body."


def test_splitter_body_includes_headings_by_default() -> None:
    document = MarkdownParser().parse(
        MULTI_ROOT_FIXTURE, document_title="multi-root.md"
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=200, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == "# First\n\nFirst body.\n\n# Second\n\nSecond body."


def test_splitter_body_includes_nested_headings_by_default() -> None:
    document = MarkdownParser().parse(
        THIRD_LEVEL_FIXTURE, document_title="third-level.md"
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
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
    splitter = IncrementalRecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=7,
            merge_below_tokens=0,
            block_options={},
        ),
    )

    measured_root = splitter._measure_section(document.root)
    chunks = splitter.split(document)

    measured_section = measured_root.children[0]
    assert measured_section.counts.body == len("Body")
    assert measured_section.counts.title == len("# A\n\n")
    assert measured_section.counts.subtree == (
        measured_section.counts.title + measured_section.counts.body
    )
    assert not hasattr(document.root.children[0], "body_token_count")
    assert not hasattr(document.root.children[0], "title_token_count")
    assert not hasattr(document.root.children[0], "subtree_token_count")
    assert len(chunks) == 1
    assert chunks[0].body == "# A\n\nBody"
    assert chunks[0].estimated_token_count == len("# A\n\nBody")
    assert chunks[0].token_count == len("# A\n\nBody")


def test_splitter_uses_estimated_tokens_for_budget_decisions() -> None:
    document = MarkdownParser().parse("# A\n\nBody", document_title="estimated.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=7,
            merge_below_tokens=0,
            block_options={},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].estimated_token_count == 9
    assert chunks[0].token_count == 9
    assert chunks[0].estimated_token_count > splitter.options.max_tokens


def test_estimated_tokens_do_not_include_trailing_separator_for_last_block() -> None:
    document = MarkdownParser().parse(
        "# A\n\nOne\n\nTwo",
        document_title="multi-block.md",
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=100, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == "# A\n\nOne\n\nTwo"
    assert chunks[0].estimated_token_count == chunks[0].token_count
    assert chunks[0].estimated_token_count == len("# A\n\nOne\n\nTwo")


def test_estimated_tokens_do_not_use_tail_window_between_blocks() -> None:
    long_block = "a" * 80
    document = MarkdownParser().parse(
        f"# A\n\n{long_block}\n\nb",
        document_title="block-join.md",
    )
    tokenizer = RecordingTokenizer()
    splitter = IncrementalRecursiveSplitter(
        tokenizer=tokenizer,
        options=SplitOptions(max_tokens=500, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].estimated_token_count == chunks[0].token_count
    assert f"{long_block}\n\n" in tokenizer.counted
    assert f"{long_block[-64:]}\n\n" not in tokenizer.counted


def test_entry_merge_uses_tail_window_only_between_entry_groups() -> None:
    long_body = "a" * 80
    tokenizer = RecordingTokenizer()
    splitter = IncrementalRecursiveSplitter(
        tokenizer=tokenizer,
        options=SplitOptions(max_tokens=500, merge_below_tokens=0),
    )
    heading_path = ((1, "A"),)
    heading_tc = len("# A\n\n")
    left = ChunkDraft(
        entries=[
            Entry(
                headings=heading_path,
                body=long_body,
                start_line=1,
                end_line=1,
                body_token_count=len(long_body),
            )
        ],
        headings=heading_path,
        headings_token_count=heading_tc,
        body_token_count=len(long_body),
        token_count=heading_tc + len(long_body),
    )
    right = ChunkDraft(
        entries=[
            Entry(
                headings=heading_path,
                body="b",
                start_line=2,
                end_line=2,
                body_token_count=1,
            )
        ],
        headings=heading_path,
        headings_token_count=heading_tc,
        body_token_count=1,
        token_count=heading_tc + 1,
    )

    merged = splitter._merge_drafts(left, right)

    assert merged.token_count == len("# A\n\n" + long_body + "\n\nb")
    assert f"{long_body}\n\n" not in tokenizer.counted
    assert f"{long_body[-8:]}\n\n" in tokenizer.counted


def test_heading_estimate_counts_title_once_and_marker_as_one_token() -> None:
    document = MarkdownParser().parse(
        "### Cacheable Title\n\nBody", document_title="tokens.md"
    )
    tokenizer = RecordingTokenizer()
    splitter = IncrementalRecursiveSplitter(
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

    chunks = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
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
    splitter = IncrementalRecursiveSplitter(
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
    splitter = IncrementalRecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=100, merge_below_tokens=0),
    )
    measured_root = splitter._measure_section(document.root)
    measured_scope = measured_root.children[0].children[0]

    assert measured_scope.counts.subtree == 47


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
    splitter = IncrementalRecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            block_options={"table": BaseParams(isolated=True)},
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

    disabled_splitter = IncrementalRecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            block_options={},
        ),
    )

    measured_disabled_root = disabled_splitter._measure_section(document.root)

    assert measured_disabled_root.can_emit_as_single_chunk is True
    assert (
        measured_disabled_root.children[0].children[1].can_emit_as_single_chunk is True
    )


def test_splitter_rejects_invalid_ideal_max_tokens_ratio() -> None:
    try:
        RecursiveSplitter(
            tokenizer=CharacterTokenizer(),
            options=SplitOptions(max_tokens=10, ideal_max_tokens_ratio=0),
        )
    except ValueError as exc:
        assert str(exc) == "ideal_max_tokens_ratio must be greater than 0 and at most 1"
    else:
        raise AssertionError("Expected ideal_max_tokens_ratio validation to fail")


def test_recursive_splitter_uses_ideal_budget_for_initial_splitting() -> None:
    document = MarkdownParser().parse(
        "# A\n\nalpha1\n\nbravo2",
        document_title="ideal-budget.md",
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            ideal_max_tokens_ratio=0.5,
            merge_below_tokens=-1,
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            ideal_max_tokens_ratio=0.5,
            merge_below_tokens=29,
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=40,
            ideal_max_tokens_ratio=0.8,
            merge_below_tokens=39,
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.body for chunk in chunks] == [
        "# Parent\n\n## One\n\nA\n\n## Two\n\nB"
    ]
    assert chunks[0].estimated_token_count == chunks[0].token_count
    assert 20 < chunks[0].token_count <= 40


def test_merge_below_tokens_does_not_merge_past_rendered_budget() -> None:
    document = MarkdownParser().parse(
        "# A\n\n" + "x " * 31 + "\n\ny",
        document_title="merge-budget.md",
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=60,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=10,
            block_options=markdown_block_options(),
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.token_count for chunk in chunks] == [60, 13]
    assert chunks[1].body == "# A\n\nx x x\n\ny"
    assert all(chunk.estimated_token_count <= 60 for chunk in chunks)


def test_merge_below_tokens_none_disables_merging() -> None:
    document = MarkdownParser().parse(
        "# A\n\nalpha1\n\nbravo2",
        document_title="merge-none.md",
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            ideal_max_tokens_ratio=0.5,
            merge_below_tokens=None,
        ),
    )

    chunks = splitter.split(document)

    # With merging disabled, the two short tails stay as separate chunks.
    assert [chunk.body for chunk in chunks] == [
        "# A\n\nalpha1",
        "# A\n\nbravo2",
    ]


def test_merge_below_tokens_absorbs_same_parent_paragraph_tails() -> None:
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=100, merge_below_tokens=25),
    )
    heading_path = ((1, "A"),)
    heading_tc = len("# A\n\n")
    left = ChunkDraft(
        entries=[
            Entry(
                headings=heading_path,
                body="section body",
                start_line=1,
                end_line=1,
                body_token_count=len("section body"),
            )
        ],
        headings=heading_path,
        headings_token_count=heading_tc,
        body_token_count=len("section body"),
        token_count=heading_tc + len("section body"),
        split_origin="section",
    )
    section_tail = ChunkDraft(
        entries=[
            Entry(
                headings=heading_path,
                body="tiny section",
                start_line=2,
                end_line=2,
                body_token_count=len("tiny section"),
            )
        ],
        headings=heading_path,
        headings_token_count=heading_tc,
        body_token_count=len("tiny section"),
        token_count=heading_tc + len("tiny section"),
        split_origin="section",
    )
    fragment_tail = ChunkDraft(
        entries=[
            Entry(
                headings=heading_path,
                body="tiny fragment",
                start_line=3,
                end_line=3,
                body_token_count=len("tiny fragment"),
            )
        ],
        headings=heading_path,
        headings_token_count=heading_tc,
        body_token_count=len("tiny fragment"),
        token_count=heading_tc + len("tiny fragment"),
        split_origin="fragment",
    )
    text_piece_tail = ChunkDraft(
        entries=[
            Entry(
                headings=heading_path,
                body="tiny text",
                start_line=4,
                end_line=4,
                body_token_count=len("tiny text"),
            )
        ],
        headings=heading_path,
        headings_token_count=heading_tc,
        body_token_count=len("tiny text"),
        token_count=heading_tc + len("tiny text"),
        split_origin="text_piece",
    )

    assert len(splitter._merge_small_chunks([left, section_tail])[0].entries) == 2
    assert len(splitter._merge_small_chunks([left, fragment_tail])[0].entries) == 2
    assert len(splitter._merge_small_chunks([left, text_piece_tail])[0].entries) == 2


def test_splitter_keeps_oversized_lists_intact_when_in_nosplit_kinds() -> None:
    document = MarkdownParser().parse(LIST_FIXTURE, document_title="list.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=20,
            merge_below_tokens=0,
            block_options={"list": BaseParams(split=False)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == LIST_FIXTURE.strip()
    assert chunks[0].token_count > 20


def test_splitter_can_split_oversized_lists_by_default() -> None:
    document = MarkdownParser().parse(LIST_FIXTURE, document_title="list.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=20,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options=markdown_block_options(),
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


def test_splitter_splits_oversized_tables_by_rows_with_repeated_header() -> None:
    md = """# Data

| Name | Value |
| ---- | ----- |
| Alpha | 100 |
| Beta | 200 |
| Gamma | 300 |
| Delta | 400 |
"""
    document = MarkdownParser().parse(md, document_title="table.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=28,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={"table": BaseParams(isolated=True)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 4
    assert all(chunk.chunk_type == "table" for chunk in chunks)
    assert all("| Name | Value |" in chunk.body for chunk in chunks)
    assert all("| ---- | ----- |" in chunk.body for chunk in chunks)
    assert [chunk.body.splitlines()[-1] for chunk in chunks] == [
        "| Alpha | 100 |",
        "| Beta | 200 |",
        "| Gamma | 300 |",
        "| Delta | 400 |",
    ]


def test_splitter_can_omit_repeated_header_for_split_table_pieces() -> None:
    md = """# Data

| Name | Value |
| ---- | ----- |
| Alpha | 100 |
| Beta | 200 |
| Gamma | 300 |
| Delta | 400 |
"""
    document = MarkdownParser().parse(md, document_title="table.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=28,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={
                "table": TableBlockParams(
                    isolated=True,
                    repeat_header=False,
                )
            },
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 4
    assert "| Name | Value |" in chunks[0].body
    assert "| ---- | ----- |" in chunks[0].body
    assert all("| Name | Value |" not in chunk.body for chunk in chunks[1:])
    assert all("| ---- | ----- |" not in chunk.body for chunk in chunks[1:])
    assert [chunk.body.splitlines()[-1] for chunk in chunks] == [
        "| Alpha | 100 |",
        "| Beta | 200 |",
        "| Gamma | 300 |",
        "| Delta | 400 |",
    ]


def test_splitter_keeps_oversized_tables_intact_when_in_nosplit_kinds() -> None:
    md = """| Name | Value |
| ---- | ----- |
| Alpha | 100 |
| Beta | 200 |
| Gamma | 300 |
| Delta | 400 |
"""
    document = MarkdownParser().parse(md, document_title="table.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=58,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={"table": BaseParams(split=False)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == md.strip()
    assert chunks[0].token_count > 58


def test_splitter_uses_block_max_tokens_for_table_row_packing() -> None:
    md = """| Name | Value |
| ---- | ----- |
| Alpha | 100 |
| Beta | 200 |
| Gamma | 300 |
"""
    document = MarkdownParser().parse(md, document_title="table.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=79,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={"table": BaseParams(max_tokens=60)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 3
    assert all("| Name | Value |" in chunk.body for chunk in chunks)
    assert [chunk.body.splitlines()[-1] for chunk in chunks] == [
        "| Alpha | 100 |",
        "| Beta | 200 |",
        "| Gamma | 300 |",
    ]


def test_splitter_preserves_oversized_single_table_rows() -> None:
    md = """| Name | Value |
| ---- | ----- |
| Alpha | very very very very very very very very long |
| Beta | short |
"""
    document = MarkdownParser().parse(md, document_title="table.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=58,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={"table": BaseParams(isolated=True)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 2
    assert "| Alpha | very very very very very very very very long |" in chunks[0].body
    assert chunks[0].estimated_token_count > 58
    assert "| Beta | short |" in chunks[1].body
    assert all("| ---- | ----- |" in chunk.body for chunk in chunks)


def test_splitter_can_split_oversized_code_fences_when_enabled() -> None:
    document = MarkdownParser().parse(CODE_FENCE_FIXTURE, document_title="code.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=28,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={"code_fence": BaseParams()},
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            merge_below_tokens=-1,
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


def test_front_matter_is_handled_as_normal_block_by_default() -> None:
    document = MarkdownParser().parse(FRONT_MATTER_FIXTURE, document_title="doc.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].chunk_id == "chunk-0001"
    assert chunks[0].chunk_type == "paragraph"
    assert (
        "---\ntitle: Test Document\nauthor: Alice\ndate: 2024-01-01\n---"
        in chunks[0].body
    )
    assert "# Introduction" in chunks[0].body
    assert "# Body" in chunks[0].body
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 13


def test_section_splitter_handles_front_matter_as_root_body_chunk() -> None:
    document = MarkdownParser().parse(FRONT_MATTER_FIXTURE, document_title="doc.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=100, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert chunks[0].chunk_type == "paragraph"
    assert chunks[0].chunk_id == "chunk-0001"
    assert chunks[0].body == (
        "---\ntitle: Test Document\nauthor: Alice\ndate: 2024-01-01\n---"
    )
    assert [chunk.headings for chunk in chunks[1:]] == [(), ()]
    assert [chunk.section_level for chunk in chunks[1:]] == [1, 1]


def test_front_matter_can_be_isolated_with_block_params() -> None:
    document = MarkdownParser().parse(FRONT_MATTER_FIXTURE, document_title="doc.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            block_options={"front_matter": BaseParams(isolated=True)},
        ),
    )

    chunks = splitter.split(document)

    assert chunks[0].chunk_id == "chunk-0001"
    assert chunks[0].chunk_type == "front_matter"
    assert chunks[0].body == (
        "---\ntitle: Test Document\nauthor: Alice\ndate: 2024-01-01\n---"
    )
    assert "# Introduction" in chunks[1].body
    assert "# Body" in chunks[1].body


def test_no_front_matter_works_normally() -> None:
    document = MarkdownParser().parse(
        "# Just a heading\n\nSome text.", document_title="doc.md"
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=500, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert "---" not in chunks[0].body
    assert "First paragraph." in chunks[0].body
    assert "Second paragraph." in chunks[0].body


def test_thematic_break_is_ignored_at_chunk_boundary() -> None:
    document = MarkdownParser().parse(THEMATIC_BREAK_FIXTURE, document_title="hr.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=40,
            merge_below_tokens=-1,
        ),
    )

    chunks = splitter.split(document)

    assert not any("---" in chunk.body for chunk in chunks)
    assert all(chunk.body.strip() != "---" for chunk in chunks)


def test_thematic_break_at_document_start_is_ignored() -> None:
    md = "---\n\nParagraph text."
    document = MarkdownParser().parse(md, document_title="hr-first.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=500, merge_below_tokens=0),
    )

    chunks = splitter.split(document)
    assert len(chunks) == 1
    assert "---" not in chunks[0].body
    assert "Paragraph text." in chunks[0].body


def test_thematic_break_after_front_matter_is_ignored_in_body_content() -> None:
    md = "---\ntitle: T\n---\n\n---\n\nBody"
    chunks = lumber(md, max_tokens=100, merge_below_tokens=0)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "paragraph"
    assert "---\ntitle: T\n---" in chunks[0].body
    assert chunks[0].body.count("---") == 2
    assert "Body" in chunks[0].body


def test_thematic_break_after_split_list_is_ignored() -> None:
    md = f"- {'a' * 40}\n- {'b' * 40}\n\n---\n\nAfter"
    chunks = lumber(
        md,
        max_tokens=50,
        merge_below_tokens=0,
        block_options={
            "list": BaseParams(),
            "paragraph": BaseParams(),
        },
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=0,
            block_options={"table": BaseParams(isolated=True)},
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
    """Empty standalone_kinds merges table back with paragraphs."""
    document = MarkdownParser().parse(
        STANDALONE_TABLE_FIXTURE, document_title="standalone.md"
    )
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=0,
            block_options={},
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=100,
            block_options={"code_fence": BaseParams(isolated=True)},
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=50,
            merge_below_tokens=-1,
            block_options={"code_fence": BaseParams(isolated=True)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) > 1
    assert all(c.chunk_type == "code_fence" for c in chunks)
    assert all("```python" in c.body for c in chunks)
    assert all(c.body.endswith("```") for c in chunks)


def test_oversized_standalone_code_fence_without_split_stays_intact() -> None:
    """Oversized standalone code fence stays as one chunk when nosplit_kinds includes it."""
    long_code = "```python\n" + "\n".join(f"line{i}" for i in range(30)) + "\n```"
    md = f"# Code\n\n{long_code}"
    document = MarkdownParser().parse(md, document_title="code.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=50,
            merge_below_tokens=0,
            block_options={"code_fence": BaseParams(isolated=True, split=False)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "code_fence"
    assert chunks[0].estimated_token_count > 50


def test_section_splitter_isolates_standalone_blocks_in_body() -> None:
    """SectionSplitter isolates standalone blocks from direct body."""
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
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=0,
            block_options={"table": BaseParams(isolated=True)},
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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=1000,
            merge_below_tokens=0,
            block_options={"code_fence": BaseParams(isolated=True)},
        ),
    )

    chunks = splitter.split(document)
    code_chunks = [c for c in chunks if c.chunk_type == "code_fence"]

    assert len(code_chunks) == 1
    assert code_chunks[0].headings == ((1, "Doc"),)
    assert code_chunks[0].section_level == 2


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
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=0,
            block_options={"table": BaseParams(isolated=True)},
        ),
    )

    chunks = splitter.split(document)

    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) == 1
    assert "Parent intro." not in table_chunks[0].body


# ---------------------------------------------------------------------------
# block_max_tokens -- per-block-kind budget overrides
# ---------------------------------------------------------------------------


def test_block_max_tokens_defaults_to_none() -> None:
    """Default BaseParams.max_tokens is None."""
    options = SplitOptions()
    for cfg in options.block_options.values():
        assert cfg.max_tokens is None


def test_per_block_max_tokens_overrides_budget_for_paragraph() -> None:
    """Paragraph splitting respects per-block max_tokens override."""
    # No heading so prefix_tokens=0 and budget equals the override directly.
    long_para = " ".join(f"word{i}" for i in range(100))
    document = MarkdownParser().parse(long_para, document_title="override.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={"paragraph": BaseParams(max_tokens=30)},
        ),
    )

    chunks = splitter.split(document)

    # With a 30-token override the paragraph should be split into many chunks
    assert len(chunks) > 1
    assert all(c.token_count <= 30 for c in chunks)


def test_per_block_max_tokens_falls_back_to_unified_max_tokens() -> None:
    """Block kinds not in the override dict use the unified budget."""
    # Short paragraph (30 words ≈ 210 tokens) fits within max_tokens=500.
    short_para = " ".join(f"word{i}" for i in range(30))
    md = f"# Title\n\n{short_para}"
    document = MarkdownParser().parse(md, document_title="fallback.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={
                "paragraph": BaseParams(),
                "blockquote": BaseParams(max_tokens=30),
            },
        ),
    )

    chunks = splitter.split(document)

    # The paragraph fits within 500 tokens → single chunk
    assert len(chunks) == 1


def test_per_block_max_tokens_for_code_fence() -> None:
    """Per-block override works for standalone code fences."""
    long_code = "```python\n" + "\n".join(f"line{i}" for i in range(30)) + "\n```"
    md = f"# Code\n\n{long_code}"
    document = MarkdownParser().parse(md, document_title="code-override.md")
    splitter = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            merge_below_tokens=-1,
            block_options={"code_fence": BaseParams(isolated=True, max_tokens=25)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) > 1
    assert all(c.chunk_type == "code_fence" for c in chunks)
    assert all("```python" in c.body for c in chunks)
    assert all(c.body.endswith("```") for c in chunks)


def test_per_block_max_tokens_validation_rejects_non_positive() -> None:
    try:
        RecursiveSplitter(
            tokenizer=CharacterTokenizer(),
            options=SplitOptions(
                block_options={"paragraph": BaseParams(max_tokens=0)},
            ),
        )
    except ValueError as exc:
        assert "must be positive" in str(exc)
    else:
        raise AssertionError("Expected non-positive override validation to fail")

    try:
        RecursiveSplitter(
            tokenizer=CharacterTokenizer(),
            options=SplitOptions(
                block_options={"paragraph": BaseParams(max_tokens=-10)},
            ),
        )
    except ValueError as exc:
        assert "must be positive" in str(exc)
    else:
        raise AssertionError("Expected negative override validation to fail")


def test_lumber_api_accepts_block_max_tokens() -> None:
    """lumber() accepts and respects per-block max_tokens via BaseParams."""
    # Large enough that, under the default ``chars // 4`` counting, the block
    # exceeds ``max_tokens`` and triggers the block-split path where the
    # per-kind ``paragraph`` budget applies.
    long_para = " ".join(f"word{i}" for i in range(400))
    chunks = lumber(
        long_para,
        max_tokens=500,
        ideal_max_tokens_ratio=1,
        merge_below_tokens=-1,
        block_options={"paragraph": {"max_tokens": 30}},
    )
    assert len(chunks) > 1
    assert all(c.token_count <= 30 for c in chunks)


# ---------------------------------------------------------------------------
# SectionSplitter block_options consistency with RecursiveSplitter
# ---------------------------------------------------------------------------


def test_section_splitter_keeps_oversized_lists_intact_when_nosplit() -> None:
    """SectionSplitter respects nosplit for lists, same as RecursiveSplitter."""
    document = MarkdownParser().parse(LIST_FIXTURE, document_title="list.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=20,
            merge_below_tokens=0,
            block_options={"list": BaseParams(split=False)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].body == LIST_FIXTURE.strip()
    assert chunks[0].token_count > 20


def test_section_splitter_can_split_oversized_lists_by_default() -> None:
    """SectionSplitter splits lists when not in nosplit, same as RecursiveSplitter."""
    document = MarkdownParser().parse(LIST_FIXTURE, document_title="list.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=20,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options=markdown_block_options(),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) > 1
    assert all(chunk.estimated_token_count <= 20 for chunk in chunks)


def test_section_splitter_splits_oversized_tables_when_isolated() -> None:
    """SectionSplitter isolates and splits oversized tables, same as RecursiveSplitter."""
    md = """# Data

| Name | Value |
| ---- | ----- |
| Alpha | 100 |
| Beta | 200 |
| Gamma | 300 |
| Delta | 400 |
"""
    document = MarkdownParser().parse(md, document_title="table.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=58,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={"table": BaseParams(isolated=True)},
        ),
    )

    chunks = splitter.split(document)

    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) > 1
    assert all("| Name | Value |" in c.body for c in table_chunks)
    assert all("| ---- | ----- |" in c.body for c in table_chunks)


def test_section_splitter_can_omit_repeated_header_for_split_tables() -> None:
    """SectionSplitter uses the same table params as RecursiveSplitter."""
    md = """# Data

| Name | Value |
| ---- | ----- |
| Alpha | 100 |
| Beta | 200 |
| Gamma | 300 |
| Delta | 400 |
"""
    document = MarkdownParser().parse(md, document_title="table.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=58,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={
                "table": TableBlockParams(
                    isolated=True,
                    repeat_header=False,
                )
            },
        ),
    )

    chunks = splitter.split(document)

    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) > 1
    assert "| Name | Value |" in table_chunks[0].body
    assert all("| Name | Value |" not in c.body for c in table_chunks[1:])


def test_section_splitter_keeps_oversized_tables_intact_when_nosplit() -> None:
    """SectionSplitter keeps oversized tables intact when nosplit, same as RecursiveSplitter."""
    md = """# Data

| Name | Value |
| ---- | ----- |
| Alpha | 100 |
| Beta | 200 |
| Gamma | 300 |
| Delta | 400 |
"""
    document = MarkdownParser().parse(md, document_title="table.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=58,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={"table": BaseParams(split=False)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].token_count > 58


def test_section_splitter_uses_per_block_max_tokens() -> None:
    """SectionSplitter respects per-block max_tokens, same as RecursiveSplitter."""
    long_para = " ".join(f"word{i}" for i in range(100))
    document = MarkdownParser().parse(long_para, document_title="override.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=500,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=-1,
            block_options={"paragraph": BaseParams(max_tokens=30)},
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) > 1
    assert all(c.token_count <= 30 for c in chunks)


def test_section_splitter_merges_small_fragments() -> None:
    """SectionSplitter merges small fragments from body splitting, same as RecursiveSplitter."""
    document = MarkdownParser().parse(
        "# A\n\nalpha1\n\nbravo2",
        document_title="merge.md",
    )
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=30,
            ideal_max_tokens_ratio=0.5,
            merge_below_tokens=29,
        ),
    )

    chunks = splitter.split(document)

    assert [chunk.body for chunk in chunks] == ["# A\n\nalpha1\n\nbravo2"]
    assert 15 < chunks[0].token_count <= 30


def test_section_splitter_uses_body_not_subtree_for_oversize_check() -> None:
    """SectionSplitter checks body tokens (not subtree) for the oversize decision."""
    md = (
        """# Parent

Small body.

## Child

"""
        + "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike."
    )
    document = MarkdownParser().parse(md, document_title="body-vs-subtree.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=50,
            merge_below_tokens=0,
            block_options=markdown_block_options(),
        ),
    )

    chunks = splitter.split(document)

    # Parent body ("Small body.") fits budget → single chunk despite large subtree
    parent_chunks = [c for c in chunks if c.section_level == 1]
    assert len(parent_chunks) == 1
    assert "Small body." in parent_chunks[0].body
    # Child body is oversized → split into multiple chunks
    child_chunks = [
        c for c in chunks if c.headings == ((1, "Parent"),) and c.section_level == 2
    ]
    assert len(child_chunks) > 1
    child_bodies = " ".join(c.body for c in child_chunks)
    assert "Alpha" in child_bodies
    assert "mike." in child_bodies


def test_splitter_default_uses_approx_char_tokenizer() -> None:
    from lumberjack.core.tokenizers import ApproxCharTokenizer

    splitter = create_splitter("recursive")
    assert isinstance(splitter.tokenizer, ApproxCharTokenizer)  # ty: ignore[unresolved-attribute]


def test_section_splitter_merges_subtree_when_within_budget() -> None:
    """Subtree whose total rendered tokens <= ideal_max_tokens collapses to one chunk."""
    fixture = """# Parent

Parent intro.

## One

One body.

## Two

Two body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Parent"),)
    # Whole subtree rendered into one body
    assert "Parent intro." in chunks[0].body
    assert "## One" in chunks[0].body
    assert "One body." in chunks[0].body
    assert "## Two" in chunks[0].body
    assert "Two body." in chunks[0].body


def test_section_splitter_does_not_merge_when_subtree_has_standalone() -> None:
    """Standalone block in the subtree disables the single-chunk short-circuit."""
    fixture = """# Parent

| A | B |
|---|---|
| 1 | 2 |

## One

One body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=10000,  # well above subtree size
            merge_below_tokens=0,
            block_options=markdown_block_options(
                {"table": BaseParams(isolated=True)},
            ),
        ),
    )

    chunks = splitter.split(document)

    # Standalone table forces split: not collapsed into one chunk.
    assert len(chunks) >= 2
    table_chunk = next(c for c in chunks if "| A |" in c.body)
    assert table_chunk.headings == ()
    assert table_chunk.body.startswith("# Parent")


def test_incremental_section_splitter_merges_subtree_when_within_budget() -> None:
    """IncrementalSectionSplitter collapses a fitting subtree to one chunk."""
    fixture = """# Parent

Parent intro.

## One

One body.

## Two

Two body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = IncrementalSectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Parent"),)
    assert "Parent intro." in chunks[0].body
    assert "## One" in chunks[0].body
    assert "One body." in chunks[0].body
    assert "## Two" in chunks[0].body
    assert "Two body." in chunks[0].body
    # token_count is the authoritative full recount, estimated stays close.
    assert chunks[0].token_count > 0
    assert abs(chunks[0].token_count - chunks[0].estimated_token_count) <= 5


def test_incremental_section_splitter_does_not_merge_when_subtree_has_standalone() -> (
    None
):
    """Standalone block disables the incremental single-chunk short-circuit."""
    fixture = """# Parent

| A | B |
|---|---|
| 1 | 2 |

## One

One body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = IncrementalSectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=10000,
            merge_below_tokens=0,
            block_options=markdown_block_options(
                {"table": BaseParams(isolated=True)},
            ),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) >= 2


def test_section_splitter_subtree_merge_does_not_cross_top_level_sections() -> None:
    """Two top-level sections each collapse independently; not merged together.

    With ``max_tokens=200`` (ideal=160), the whole document exceeds the ideal
    budget so the root short-circuit fails and falls through to per-section
    splitting.  Each top-level section then independently collapses into one
    chunk (each well under 160 tokens).  The two sections are NOT merged
    together — there is no cross-sibling merging in SectionSplitter.
    """
    first_body = "Alpha beta gamma delta. " * 4  # ~100 chars
    second_body = "Echo foxtrot golf hotel. " * 4  # ~100 chars
    fixture = f"""# First

{first_body}

# Second

{second_body}
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=200, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    # Root short-circuit fails (total > ideal); each top-level section
    # collapses to its own chunk.
    assert len(chunks) == 2
    assert chunks[0].headings == ()
    assert chunks[1].headings == ()
    assert chunks[0].body.startswith("# First")
    assert chunks[1].body.startswith("# Second")
    assert "Alpha beta" in chunks[0].body
    assert "Echo foxtrot" in chunks[1].body
    assert "Echo foxtrot" not in chunks[0].body

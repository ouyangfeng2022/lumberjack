"""Tests for ``SplitOptions.render_headings``.

Both splitters are render-aware. When ``render_headings`` is False the ancestor
heading breadcrumb is excluded from the split budget *and* omitted from the
rendered body, while the chunk's own heading and internal headings still render.
So:

* the rendered body can grow into the budget previously occupied by ancestor
  headings, and
* ``estimated_token_count == token_count == tokenizer.count(body)`` exactly —
  the running estimate matches the actually-rendered body.

``Chunk.headings`` stores ancestor headings either way. The chunk's own heading
and internal relative headings always render regardless of the flag, because
they are chunk-internal structure, not the ancestor prefix.
"""

from __future__ import annotations

import pytest

from lumberjack.core.models import SplitOptions
from lumberjack.core.parser.markdown.parser import MarkdownParser
from lumberjack.core.splitter.recursive import RecursiveSplitter
from lumberjack.core.splitter.subtree import (
    IncrementalSubtreeSplitter,
    SubtreeSplitter,
)
from tests.helpers import CharacterTokenizer

# A document with multiple paragraphs per section so bodies are splittable.
SPLITTABLE_FIXTURE = """# Big Heading Title Here

""" + "\n\n".join(f"paragraph {i}: " + "word " * 8 for i in range(10))

# A simpler nested document for metadata/structure assertions.
NESTED_FIXTURE = """# Root

## Scope

### A

Alpha body. Alpha body. Alpha body.

### B

Beta body. Beta body. Beta body.
"""


@pytest.fixture
def tokenizer() -> CharacterTokenizer:
    return CharacterTokenizer()


@pytest.fixture
def splittable_ast():  # type: ignore[no-untyped-def]
    return MarkdownParser().parse(SPLITTABLE_FIXTURE, document_title="t.md")


@pytest.fixture
def nested_ast():  # type: ignore[no-untyped-def]
    return MarkdownParser().parse(NESTED_FIXTURE, document_title="t.md")


# ---------------------------------------------------------------------------
# SubtreeSplitter — render-aware budgeting
# ---------------------------------------------------------------------------


class TestSubtreeSplitterRenderAware:
    """SubtreeSplitter excludes ancestor heading tokens when not rendered."""

    @staticmethod
    def _split(
        ast,
        *,
        render_headings: bool,
        max_tokens: int = 108,  # type: ignore[no-untyped-def]
    ) -> list:
        splitter = SubtreeSplitter(
            tokenizer=CharacterTokenizer(),
            options=SplitOptions(
                max_tokens=max_tokens,
                ideal_max_tokens_ratio=1,
                merge_below_ratio=0.0,
                render_headings=render_headings,
            ),
        )
        return splitter.split(ast)

    def test_false_omits_ancestors_but_keeps_own_heading(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(nested_ast, render_headings=False, max_tokens=60)
        assert chunks, "expected at least one chunk"
        for chunk in chunks:
            assert chunk.body.lstrip().startswith("###")
            assert "# Root" not in chunk.body
            assert "## Scope" not in chunk.body

    def test_false_preserves_headings_metadata(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(splittable_ast, render_headings=False)
        for chunk in chunks:
            assert chunk.headings == ()
            assert chunk.section_level == 1

    def test_true_renders_ancestor_and_own_heading_in_body(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(splittable_ast, render_headings=True)
        assert chunks
        assert chunks[0].body.startswith("# Big Heading Title Here")

    def test_false_keeps_h1_budget_when_only_own_heading_renders(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """Hiding ancestors reclaims no budget for a top-level section."""
        true_chunks = self._split(splittable_ast, render_headings=True, max_tokens=108)
        false_chunks = self._split(
            splittable_ast, render_headings=False, max_tokens=108
        )
        assert len(false_chunks) == len(true_chunks)
        assert [c.body for c in false_chunks] == [c.body for c in true_chunks]

    def test_false_token_count_equals_body_tokens(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """With no headings rendered, token_count == estimated == measured body."""
        tok = CharacterTokenizer()
        chunks = self._split(splittable_ast, render_headings=False)
        for chunk in chunks:
            measured = tok.count(chunk.body)
            assert chunk.token_count == measured
            assert chunk.estimated_token_count == measured

    def test_false_respects_max_tokens(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(splittable_ast, render_headings=False, max_tokens=108)
        for chunk in chunks:
            assert chunk.token_count <= 108

    def test_false_works_for_nested_sections(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        splitter = SubtreeSplitter(
            tokenizer=CharacterTokenizer(),
            options=SplitOptions(
                max_tokens=60,
                ideal_max_tokens_ratio=1,
                merge_below_ratio=0.0,
                render_headings=False,
            ),
        )
        chunks = splitter.split(nested_ast)
        assert len(chunks) == 2
        headings = [c.headings for c in chunks]
        assert headings == [
            ((1, "Root"), (2, "Scope")),
            ((1, "Root"), (2, "Scope")),
        ]
        for chunk in chunks:
            # Ancestors are hidden, own section headings remain.
            assert chunk.body.lstrip().startswith("###")
            assert "Alpha body" in chunk.body or "Beta body" in chunk.body
            assert "Root" not in chunk.body and "Scope" not in chunk.body

    def test_oversized_body_false_mode_keeps_metadata(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """Oversized body splitting still tags every fragment with the path."""
        chunks = self._split(splittable_ast, render_headings=False, max_tokens=60)
        for chunk in chunks:
            assert chunk.headings == ()
            assert chunk.section_level == 1

    def test_incremental_false_uses_rendered_heading_budget(self) -> None:
        ast = MarkdownParser().parse(
            """# Very Long Root Ancestor Heading

## Very Long Scope Ancestor Heading

### Leaf

alpha alpha alpha alpha alpha

beta beta beta beta beta beta
""",
            document_title="t.md",
        )
        splitter = IncrementalSubtreeSplitter(
            tokenizer=CharacterTokenizer(),
            options=SplitOptions(
                max_tokens=40,
                ideal_max_tokens_ratio=1,
                merge_below_ratio=0.0,
                render_headings=False,
            ),
        )

        chunks = splitter.split(ast)

        assert len(chunks) == 2
        assert all(chunk.body.startswith("### Leaf") for chunk in chunks)
        assert all(chunk.token_count <= 40 for chunk in chunks)


# ---------------------------------------------------------------------------
# RecursiveSplitter — render-aware budgeting
# ---------------------------------------------------------------------------


class TestRecursiveSplitterRenderAware:
    """RecursiveSplitter excludes the ancestor breadcrumb from budget and body."""

    @staticmethod
    def _split(
        ast,
        *,
        render_headings: bool,
        max_tokens: int = 60,  # type: ignore[no-untyped-def]
    ) -> list:
        splitter = RecursiveSplitter(
            tokenizer=CharacterTokenizer(),
            options=SplitOptions(
                max_tokens=max_tokens,
                ideal_max_tokens_ratio=1,
                merge_below_ratio=0.0,
                render_headings=render_headings,
            ),
        )
        return splitter.split(ast)

    def test_false_omits_ancestor_heading_from_body(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(nested_ast, render_headings=False)
        for chunk in chunks:
            assert not chunk.body.lstrip().startswith("# Root")
            # Internal relative headings (### A / ### B) may still appear
            # because they are chunk-internal structure, not ancestor prefix.
            assert "Alpha body" in chunk.body or "Beta body" in chunk.body

    def test_false_preserves_headings_metadata(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(nested_ast, render_headings=False)
        assert chunks
        for chunk in chunks:
            assert chunk.headings[0] == (1, "Root")

    def test_false_estimated_equals_measured(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """The running estimate matches the rendered body tokens exactly."""
        tok = CharacterTokenizer()
        chunks = self._split(nested_ast, render_headings=False, max_tokens=60)
        for chunk in chunks:
            measured = tok.count(chunk.body)
            assert chunk.token_count == measured
            assert chunk.estimated_token_count == measured

    def test_false_respects_max_tokens(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """With body-only budgeting, bodies can grow up to max_tokens."""
        chunks = self._split(splittable_ast, render_headings=False, max_tokens=108)
        for chunk in chunks:
            assert chunk.token_count <= 108

    def test_false_keeps_h1_budget_when_only_own_heading_renders(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """Hiding ancestors reclaims no budget for a top-level section."""
        true_chunks = self._split(splittable_ast, render_headings=True, max_tokens=108)
        false_chunks = self._split(
            splittable_ast, render_headings=False, max_tokens=108
        )
        assert len(false_chunks) == len(true_chunks)
        assert [c.body for c in false_chunks] == [c.body for c in true_chunks]

    def test_false_estimated_equals_measured_splittable(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """estimated == token_count == measured on the splittable fixture."""
        tok = CharacterTokenizer()
        chunks = self._split(splittable_ast, render_headings=False, max_tokens=108)
        for chunk in chunks:
            measured = tok.count(chunk.body)
            assert chunk.token_count == measured
            assert chunk.estimated_token_count == measured

    def test_internal_relative_headings_still_rendered(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """RecursiveSplitter only drops the ancestor prefix; internal headings stay."""
        chunks = self._split(nested_ast, render_headings=False, max_tokens=120)
        # When siblings merge into one chunk, ### A and ### B are internal
        # relative headings and must still appear in the body.
        joined = "\n\n".join(c.body for c in chunks)
        assert "### A" in joined or "### B" in joined

    def test_false_asymmetric_merge_estimated_equals_measured(self) -> None:
        """Merged sibling sections: common dropped, relative kept, estimate exact."""
        fixture = (
            "# Development Guide\n\n"
            "## Current Scope\n\nWe are building a splitter.\n\n"
            "## Milestones\n\n### M0\n\nFirst milestone.\n\n"
            "### M1\n\nSecond milestone.\n\n"
            "## Suggested Workflow\n\nFollow these steps.\n"
        )
        ast = MarkdownParser().parse(fixture, document_title="t.md")
        tok = CharacterTokenizer()
        splitter = RecursiveSplitter(
            tokenizer=tok,
            options=SplitOptions(
                max_tokens=400,
                ideal_max_tokens_ratio=1,
                merge_below_ratio=0.0,
                render_headings=False,
            ),
        )
        chunks = splitter.split(ast)
        assert len(chunks) == 1
        chunk = chunks[0]
        # Ancestor breadcrumb (# Development Guide) is not rendered.
        assert "# Development Guide" not in chunk.body
        # Internal relative headings are rendered.
        assert "## Current Scope" in chunk.body
        assert "### M0" in chunk.body
        # Estimate matches the measured body exactly.
        measured = tok.count(chunk.body)
        assert chunk.token_count == measured
        assert chunk.estimated_token_count == measured


# ---------------------------------------------------------------------------
# Public API + option plumbing
# ---------------------------------------------------------------------------


class TestRenderHeadingsOption:
    def test_default_is_true(self) -> None:
        opts = SplitOptions()
        assert opts.render_headings is True

    def test_can_be_disabled(self) -> None:
        opts = SplitOptions(render_headings=False)
        assert opts.render_headings is False

    def test_lumber_threads_option_section(self) -> None:
        from lumberjack import lumber

        chunks = lumber(
            NESTED_FIXTURE,
            splitter="subtree",
            max_tokens=60,
            ideal_max_tokens_ratio=1,
            merge_below_ratio=0.0,
            render_headings=False,
        )
        assert chunks
        for chunk in chunks:
            assert "Root" not in chunk.body
            assert chunk.headings  # metadata preserved

    def test_lumber_threads_option_recursive(self) -> None:
        from lumberjack import lumber

        chunks = lumber(
            NESTED_FIXTURE,
            splitter="recursive",
            max_tokens=60,
            ideal_max_tokens_ratio=1,
            merge_below_ratio=0.0,
            render_headings=False,
        )
        assert chunks
        for chunk in chunks:
            assert chunk.headings  # metadata always preserved

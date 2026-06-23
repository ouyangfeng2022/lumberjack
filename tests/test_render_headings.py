"""Tests for ``SplitOptions.render_headings``.

Two splitter profiles are covered:

* :class:`SectionSplitter` — render-aware budgeting. When ``render_headings``
  is False the heading breadcrumb is excluded from the split budget, so the
  rendered body can grow up to ``max_tokens`` and ``token_count`` matches the
  actual body tokens exactly.
* :class:`RecursiveSplitter` — body-only rendering with a documented budget
  caveat. The common heading breadcrumb is omitted from ``Chunk.body`` but the
  split budget still reserves tokens for it; the resulting body is therefore
  shorter than ``max_tokens`` allows. Metadata (``Chunk.headings``) is
  preserved either way.
"""

from __future__ import annotations

import pytest

from lumberjack.core.models import SplitOptions
from lumberjack.core.parsers.markdown.parser import MarkdownParser
from lumberjack.core.splitters.recursive import RecursiveSplitter
from lumberjack.core.splitters.section import SectionSplitter
from lumberjack.core.tokenizers import SimpleCharTokenizer

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
def tokenizer() -> SimpleCharTokenizer:
    return SimpleCharTokenizer()


@pytest.fixture
def splittable_ast():  # type: ignore[no-untyped-def]
    return MarkdownParser().parse(SPLITTABLE_FIXTURE, document_title="t.md")


@pytest.fixture
def nested_ast():  # type: ignore[no-untyped-def]
    return MarkdownParser().parse(NESTED_FIXTURE, document_title="t.md")


# ---------------------------------------------------------------------------
# SectionSplitter — render-aware budgeting
# ---------------------------------------------------------------------------


class TestSectionSplitterRenderAware:
    """SectionSplitter excludes heading tokens from the budget when not rendered."""

    @staticmethod
    def _split(
        ast,
        *,
        render_headings: bool,
        max_tokens: int = 108,  # type: ignore[no-untyped-def]
    ) -> list:
        splitter = SectionSplitter(
            tokenizer=SimpleCharTokenizer(),
            options=SplitOptions(
                max_tokens=max_tokens,
                ideal_max_tokens_ratio=1,
                merge_below_tokens=0,
                render_headings=render_headings,
            ),
        )
        return splitter.split(ast)

    def test_false_omits_common_heading_from_body(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(splittable_ast, render_headings=False)
        assert chunks, "expected at least one chunk"
        for chunk in chunks:
            # No rendered ATX heading line at the start of the body.
            assert not chunk.body.lstrip().startswith("#")
            assert "Big Heading Title Here" not in chunk.body

    def test_false_preserves_headings_metadata(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(splittable_ast, render_headings=False)
        for chunk in chunks:
            assert chunk.headings == ((1, "Big Heading Title Here"),)

    def test_true_renders_common_heading_in_body(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(splittable_ast, render_headings=True)
        assert chunks
        assert chunks[0].body.startswith("# Big Heading Title Here")

    def test_false_enlarges_body_budget(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """At max_tokens=108, False packs ~2 paragraphs per chunk vs ~1 for True."""
        true_chunks = self._split(splittable_ast, render_headings=True, max_tokens=108)
        false_chunks = self._split(
            splittable_ast, render_headings=False, max_tokens=108
        )
        # Fewer chunks when the heading is not reserved.
        assert len(false_chunks) < len(true_chunks)
        # And each False chunk carries more body tokens (the heading budget is
        # reclaimed for content).
        avg_true = sum(c.token_count for c in true_chunks) / len(true_chunks)
        avg_false = sum(c.token_count for c in false_chunks) / len(false_chunks)
        # True includes ~26 heading tokens per chunk; False does not, so the
        # False average body is larger than the True average body would be even
        # after subtracting the heading overhead.
        assert avg_false > avg_true - 26

    def test_false_token_count_equals_body_tokens(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """With no headings rendered, token_count == estimated == measured body."""
        tok = SimpleCharTokenizer()
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
        splitter = SectionSplitter(
            tokenizer=SimpleCharTokenizer(),
            options=SplitOptions(
                max_tokens=60,
                ideal_max_tokens_ratio=1,
                merge_below_tokens=0,
                render_headings=False,
            ),
        )
        chunks = splitter.split(nested_ast)
        assert len(chunks) == 2
        headings = [c.headings for c in chunks]
        assert ((1, "Root"), (2, "Scope"), (3, "A")) in headings
        assert ((1, "Root"), (2, "Scope"), (3, "B")) in headings
        for chunk in chunks:
            # Bodies are body-only — no ATX headings.
            assert "Alpha body" in chunk.body or "Beta body" in chunk.body
            assert "Root" not in chunk.body and "Scope" not in chunk.body

    def test_oversized_body_false_mode_keeps_metadata(
        self,
        splittable_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """Oversized body splitting still tags every fragment with the path."""
        chunks = self._split(splittable_ast, render_headings=False, max_tokens=60)
        for chunk in chunks:
            assert chunk.headings == ((1, "Big Heading Title Here"),)


# ---------------------------------------------------------------------------
# RecursiveSplitter — body-only rendering with budget caveat
# ---------------------------------------------------------------------------


class TestRecursiveSplitterBudgetCaveat:
    """RecursiveSplitter keeps headings in the budget but omits them from body."""

    @staticmethod
    def _split(
        ast,
        *,
        render_headings: bool,
        max_tokens: int = 60,  # type: ignore[no-untyped-def]
    ) -> list:
        splitter = RecursiveSplitter(
            tokenizer=SimpleCharTokenizer(),
            options=SplitOptions(
                max_tokens=max_tokens,
                ideal_max_tokens_ratio=1,
                merge_below_tokens=0,
                render_headings=render_headings,
            ),
        )
        return splitter.split(ast)

    def test_false_omits_common_heading_from_body(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(nested_ast, render_headings=False)
        for chunk in chunks:
            assert not chunk.body.lstrip().startswith("# Root")
            # Internal relative headings (### A / ### B) may still appear
            # because they are chunk-internal structure, not common prefix.
            assert "Alpha body" in chunk.body or "Beta body" in chunk.body

    def test_false_preserves_headings_metadata(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        chunks = self._split(nested_ast, render_headings=False)
        assert chunks
        for chunk in chunks:
            assert chunk.headings[0] == (1, "Root")

    def test_false_body_is_shorter_than_budget(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """The documented caveat: budget reserves heading tokens the body omits."""
        chunks = self._split(nested_ast, render_headings=False, max_tokens=60)
        for chunk in chunks:
            # Body tokens strictly below the budget because heading tokens
            # are reserved but not rendered.
            assert chunk.token_count < 60
            assert chunk.estimated_token_count <= 60

    def test_budget_decisions_match_true_mode(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """The split *plan* (count, headings) is identical between modes —
        only the rendered body differs."""
        true_chunks = self._split(nested_ast, render_headings=True)
        false_chunks = self._split(nested_ast, render_headings=False)
        assert len(true_chunks) == len(false_chunks)
        assert [c.headings for c in true_chunks] == [c.headings for c in false_chunks]

    def test_internal_relative_headings_still_rendered(
        self,
        nested_ast,  # type: ignore[no-untyped-def]
    ) -> None:
        """RecursiveSplitter only drops the common prefix; internal headings stay."""
        chunks = self._split(nested_ast, render_headings=False, max_tokens=120)
        # When siblings merge into one chunk, ### A and ### B are internal
        # relative headings and must still appear in the body.
        joined = "\n\n".join(c.body for c in chunks)
        assert "### A" in joined or "### B" in joined


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
            splitter="section",
            max_tokens=60,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=0,
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
            merge_below_tokens=0,
            render_headings=False,
        )
        assert chunks
        for chunk in chunks:
            assert chunk.headings  # metadata always preserved

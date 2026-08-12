"""Heading metadata, body rendering, and heading-sensitive budget regressions."""

from __future__ import annotations

from typing import Any

import pytest

from lumberjack.feller.markdown.feller import MarkdownFeller
from lumberjack.models import (
    Chunk,
    Entry,
    HeadingPath,
    complete_heading_path,
    render_heading_path,
)
from lumberjack.sawyer import (
    ExactSectionSawyer,
    ExactSiblingSawyer,
    ExactSubtreeSawyer,
    IncrementalSectionSawyer,
    IncrementalSiblingSawyer,
    IncrementalSubtreeSawyer,
)
from lumberjack.sawyer.base import BaseSawyer
from tests.helpers import CharacterScaler, saw

ALL_SPLITTERS = (
    ExactSiblingSawyer,
    IncrementalSiblingSawyer,
    ExactSubtreeSawyer,
    IncrementalSubtreeSawyer,
    ExactSectionSawyer,
    IncrementalSectionSawyer,
)


class FloorTenScaler:
    """Non-additive scaler that makes incremental join error observable."""

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(range(len(text) // 10))

    def scale(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text) // 10


def test_complete_heading_path_appends_optional_own_heading() -> None:
    ancestors = ((1, "Root"), (2, "Scope"))

    assert complete_heading_path(ancestors, (3, "Detail")) == (
        (1, "Root"),
        (2, "Scope"),
        (3, "Detail"),
    )
    assert complete_heading_path(ancestors, None) == ancestors


def _split(
    splitter_class: type[BaseSawyer],
    source: str,
    *,
    max_tokens: int = 1000,
    heading_sensitive: bool = True,
) -> list[Chunk]:
    options: dict[str, Any] = {
        "max_tokens": max_tokens,
        "ideal_max_tokens_ratio": 1.0,
        "heading_sensitive": heading_sensitive,
    }
    options["merge_below_ratio"] = 0.0
    log = MarkdownFeller().fell(source, document_title="test.md")
    return saw(splitter_class(CharacterScaler(), **options), log)


@pytest.mark.parametrize("splitter_class", ALL_SPLITTERS)
def test_single_section_externalizes_complete_heading_path(
    splitter_class: type[BaseSawyer],
) -> None:
    chunks = _split(splitter_class, "# Root\n\nBody.")

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.ancestor_headings == ()
    assert chunk.own_heading == (1, "Root")
    assert chunk.body == "Body."
    assert "Root" not in chunk.body


@pytest.mark.parametrize("splitter_class", ALL_SPLITTERS)
def test_final_token_fields_are_exact_and_additive(
    splitter_class: type[BaseSawyer],
) -> None:
    scaler = CharacterScaler()
    chunks = _split(
        splitter_class,
        "# Root\n\n## Scope\n\nAlpha.\n\n### Detail\n\nBeta.",
    )

    assert chunks
    for chunk in chunks:
        heading_text = render_heading_path(
            complete_heading_path(chunk.ancestor_headings, chunk.own_heading)
        )
        assert chunk.headings_token_count == scaler.scale(heading_text)
        assert chunk.body_token_count == scaler.scale(chunk.body)
        assert chunk.token_count == (
            chunk.headings_token_count + scaler.scale("\n\n") + chunk.body_token_count
        )
        if splitter_class.__name__.startswith("Exact"):
            assert chunk.estimated_token_count == chunk.token_count


@pytest.mark.parametrize(
    "splitter_class",
    (
        IncrementalSiblingSawyer,
        IncrementalSubtreeSawyer,
        IncrementalSectionSawyer,
    ),
)
def test_incremental_finalization_preserves_split_time_estimate(
    splitter_class: type[BaseSawyer],
) -> None:
    document = MarkdownFeller().fell("# H\n\naaaaa\n\nbbbbb")
    options: dict[str, Any] = {
        "max_tokens": 100,
        "ideal_max_tokens_ratio": 1.0,
    }
    options["merge_below_ratio"] = 0.0

    chunk = saw(splitter_class(FloorTenScaler(), **options), document)[0]

    assert chunk.headings_token_count == 0
    assert chunk.body_token_count == 1
    assert chunk.token_count == 1
    assert chunk.estimated_token_count == 0


@pytest.mark.parametrize(
    "splitter_class",
    (ExactSiblingSawyer, IncrementalSiblingSawyer),
)
def test_parent_subtree_keeps_parent_as_own_and_children_in_body(
    splitter_class: type[BaseSawyer],
) -> None:
    chunks = _split(
        splitter_class,
        "# Root\n\nRoot body.\n\n## A\n\nAlpha.\n\n## B\n\nBeta.",
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.ancestor_headings == ()
    assert chunk.own_heading == (1, "Root")
    assert chunk.body == "Root body.\n\n## A\n\nAlpha.\n\n## B\n\nBeta."


@pytest.mark.parametrize(
    "splitter_class",
    (ExactSiblingSawyer, IncrementalSiblingSawyer),
)
def test_merged_root_siblings_have_no_own_heading(
    splitter_class: type[BaseSawyer],
) -> None:
    chunks = _split(
        splitter_class,
        "# First\n\nOne.\n\n# Second\n\nTwo.",
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.ancestor_headings == ()
    assert chunk.own_heading is None
    assert chunk.body == "# First\n\nOne.\n\n# Second\n\nTwo."


@pytest.mark.parametrize("splitter_class", ALL_SPLITTERS)
def test_fragmented_section_repeats_metadata_but_not_heading_in_body(
    splitter_class: type[BaseSawyer],
) -> None:
    source = "# Root\n\n" + "\n\n".join(
        f"paragraph-{index}-" + "x" * 20 for index in range(4)
    )
    chunks = _split(splitter_class, source, max_tokens=45)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.ancestor_headings == ()
        assert chunk.own_heading == (1, "Root")
        assert "# Root" not in chunk.body


@pytest.mark.parametrize("splitter_class", ALL_SPLITTERS)
def test_heading_sensitive_controls_budget_not_rendering(
    splitter_class: type[BaseSawyer],
) -> None:
    source = "# Very Long Heading Path\n\n" + "\n\n".join(
        f"paragraph-{index}-" + "x" * 19 for index in range(3)
    )
    sensitive = _split(splitter_class, source, max_tokens=48, heading_sensitive=True)
    insensitive = _split(splitter_class, source, max_tokens=48, heading_sensitive=False)

    assert len(insensitive) <= len(sensitive)
    assert ["# Very Long Heading Path" in chunk.body for chunk in sensitive] == [
        False
    ] * len(sensitive)
    assert all(chunk.body_token_count <= 48 for chunk in insensitive)
    assert any(chunk.token_count > 48 for chunk in insensitive)


@pytest.mark.parametrize("splitter_class", ALL_SPLITTERS)
def test_heading_only_section_is_kept_when_empty_sections_are_enabled(
    splitter_class: type[BaseSawyer],
) -> None:
    options: dict[str, Any] = {
        "max_tokens": 100,
        "ideal_max_tokens_ratio": 1.0,
        "heading_sensitive": True,
        "skip_empty_sections": False,
    }
    if "Section" not in splitter_class.__name__:
        options["merge_below_ratio"] = 0.0
    document = MarkdownFeller().fell("# Empty", document_title="test.md")

    chunks = saw(splitter_class(CharacterScaler(), **options), document)

    assert len(chunks) == 1
    assert chunks[0].own_heading == (1, "Empty")
    assert chunks[0].body == ""
    assert chunks[0].body_token_count == 0


@pytest.mark.parametrize("splitter_class", ALL_SPLITTERS)
def test_oversized_external_heading_is_kept_intact(
    splitter_class: type[BaseSawyer],
) -> None:
    chunks = _split(
        splitter_class,
        f"# {'H' * 50}\n\nBody.",
        max_tokens=20,
        heading_sensitive=True,
    )

    assert chunks
    assert all(chunk.own_heading == (1, "H" * 50) for chunk in chunks)
    assert all(chunk.headings_token_count > 20 for chunk in chunks)
    assert all("# " not in chunk.body for chunk in chunks)


def test_incremental_does_not_full_recount_candidate_bodies() -> None:
    class GuardedIncrementalSiblingSawyer(IncrementalSiblingSawyer):
        def _rendered_token_count(
            self,
            entries: list[Entry],
            *,
            external_headings: HeadingPath | None = None,
        ) -> int:
            del entries, external_headings
            raise AssertionError("incremental budget path must not recount candidates")

    chunks = _split(
        GuardedIncrementalSiblingSawyer,
        "# Root\n\n## A\n\nAlpha.\n\n## B\n\nBeta.",
    )

    assert chunks

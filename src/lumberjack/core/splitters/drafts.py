from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..models import HeadingPath, SectionNode


@dataclass(slots=True)
class _Entry:
    """Rendered content unit with heading context and line range, a flattened SectionNode.

    Args:
        headings: Full heading path for the entry, used for rendering and metadata.
        body: Rendered Markdown body text for the entry, excluding headings.
        start_line: Starting line number of the entry in the original document, if available.
        end_line: Ending line number of the entry in the original document, if available.
        body_token_count: Cached token count for the entry body, excluding headings.
    """

    headings: HeadingPath
    body: str
    start_line: int | None
    end_line: int | None
    body_token_count: int = 0


@dataclass(slots=True)
class _ChunkDraft:
    """Intermediate chunk holding grouped entries, token estimate, and split source.

    Args:
        entries: List of entries to be merged into the chunk, with heading context and body.
        headings: The full heading path context for the chunk, used for rendering and metadata.

            ``# H1 \\n\\n ## H2.1 \\n\\n Content1``, headings=[(1, "H1"), (2, "H2.1")].

            ``# H1 \\n\\n ## H2.1 \\n\\n Content1 ## H2.2 \\n\\n Content2``, headings=[(1, "H1")].

        headings_token_count: The token count for the chunk's full heading path.
        body_token_count: The token count for the chunk body (sum of entry body_token_count plus separator deltas).
        token_count: `headings_token_count` + `body_token_count`.
        split_origin: The source of the split that produced this draft, for debugging/analysis.
        chunk_type: The type of content in the chunk (e.g. "paragraph", "code_block"), used for metadata.

    """

    entries: list[_Entry]
    headings: HeadingPath
    headings_token_count: int
    body_token_count: int
    token_count: int
    split_origin: Literal["section", "fragment", "text_piece", "merge"] = "section"
    chunk_type: str = "paragraph"


@dataclass(slots=True, frozen=True)
class _SectionTokenCounts:
    """Token estimates for a section heading, own body, and full subtree.

    Args:
        title: Tokens for the section's own heading title (0 if level 0).
        body: Tokens for the section's own body blocks (0 if no blocks).
        subtree: Tokens for the entire section subtree, including own heading and body,
            and all descendant sections' headings and bodies.
    """

    title: int
    body: int
    subtree: int


@dataclass(slots=True, frozen=True)
class _MeasuredSection:
    """A SectionNode plus splitter-specific token counts for its measured children.

    Args:
        node: The original SectionNode.
        counts: Cached token counts for the section's title, body, and full subtree.
        tail_text: Rendered tail text for cheap separator-delta estimates when this
            section is followed by more rendered Markdown.
        can_emit_as_single_chunk: Whether the section subtree can be emitted as one
            chunk without isolating standalone blocks.
        children: Measured child sections with the same structure as the original.
    """

    node: SectionNode
    counts: _SectionTokenCounts
    tail_text: str
    can_emit_as_single_chunk: bool
    children: tuple[_MeasuredSection, ...] = ()


__all__ = [
    "_ChunkDraft",
    "_Entry",
    "_MeasuredSection",
    "_SectionTokenCounts",
]

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from lumberjack.block import BlockKind

from ._internal.rendering import join_rendered_blocks

HeadingKey: TypeAlias = tuple[int, str]
HeadingPath: TypeAlias = tuple[HeadingKey, ...]


@dataclass(slots=True, frozen=True)
class DocumentInline:
    """Format-neutral inline node normalized by an input parser.

    Attributes:
        kind: Inline node type (e.g. ``"text"``, ``"link"``, ``"code_inline"``,
            ``"strong"``, ``"em"``, ``"image"``).
        text: Rendered plain text of this node.
        children: Nested inline children (e.g. emphasis wrapping text).
        attrs: Additional attributes (``"href"``, ``"src"``, ``"title"``, etc.).
    """

    kind: str
    text: str = ""
    children: tuple[DocumentInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class DocumentBlock:
    """Format-neutral block node in the canonical rendered representation.

    Attributes:
        kind: Block type (e.g. ``"paragraph"``, ``"heading"``, ``"code_fence"``,
            ``"blockquote"``, ``"list"``, ``"list_item"``, ``"table"``,
            ``"html_block"``, ``"math_block"``).
        text: Canonical rendered text consumed by splitters. Markdown input is
            normalized Markdown; HTML and DOCX input is converted to the same
            Markdown-like representation. It is not guaranteed to be a source
            slice.
        start_line: 1-based line number where the block begins.
        end_line: 1-based line number where the block ends.
        children: Nested child blocks for container types (``"blockquote"``,
            ``"list"``, ``"list_item"``).  Empty for leaf blocks.
        inlines: Normalized inline nodes parsed from the block content.
            Populated for ``"paragraph"`` and ``"heading"`` blocks.
        attrs: Additional attributes (e.g. heading level, list style, code language).
    """

    kind: BlockKind | str
    text: str
    start_line: int | None = None
    end_line: int | None = None
    children: tuple[DocumentBlock, ...] = ()
    inlines: tuple[DocumentInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SectionNode:
    """Heading-tree node representing a section and its children.

    Attributes:
        level: Heading level.
        title: Plain-text heading title.
        path: Tuple of ``(level, title)`` pairs from root to this section.
        blocks: Block-level content directly under this section (not in sub-sections).
        children: Child sections (sub-headings nested within this section).
        index: Position of this section among its siblings (0-based).
        start_line: 1-based line number where the section heading begins.
        title_inlines: Normalized inline nodes parsed from the heading text.
    """

    level: int
    title: str
    path: HeadingPath = ()
    blocks: list[DocumentBlock] = field(default_factory=list)
    children: list[SectionNode] = field(default_factory=list)
    index: int = 0
    start_line: int | None = None
    title_inlines: tuple[DocumentInline, ...] = ()

    @property
    def heading_key(self) -> HeadingKey:
        return (self.level, self.title)

    def add_block(self, block: DocumentBlock) -> None:
        """Append a block (roughly one paragraph) to this section."""
        self.blocks.append(block)

    def add_child(self, child: SectionNode) -> None:
        self.children.append(child)


@dataclass(slots=True, frozen=True)
class DocumentAST:
    """Parsed document with a normalized section tree, source, and metadata.

    Attributes:
        title: Document title.  Priority: user-provided ``document_title``,
            then front matter ``title`` field, then first level-1 heading,
            then ``"Anonymous"``.
        source: Original text for Markdown and HTML inputs. Binary parsers may
            leave this empty or provide a normalized textual representation.
        root: Root section node of the heading tree.
        source_path: Original file path or caller-supplied source provenance.
        metadata: Semantic document metadata parsed from the source and merged
            with caller-provided overrides.
        reference_definitions: Link/image reference definitions (``[label]: url``).
    """

    title: str
    source: str
    root: SectionNode
    source_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    reference_definitions: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class Chunk:
    """Final chunk payload with rendered and estimated token counts plus source metadata.

    Attributes:
        chunk_id: Unique identifier for this chunk.
        chunk_type: Origin block type (e.g. ``"paragraph"``, ``"heading"``,
            ``"code_fence"``, ``"document"``).
        body: Rendered chunk text, optionally including heading breadcrumbs.
        token_count: Token count measured by the configured tokenizer.
        estimated_token_count: Split-time running estimate (additive + separator-delta
            window) used for budget decisions; ``token_count`` is the authoritative
            full recount of the rendered body. The two may differ slightly due
            to join approximations.
        headings: Tuple of ``(level, title)`` pairs representing the chunk's
            ancestor heading path.

            ``# H1 \\n\\n ## H2.1 \\n\\n Content1``, headings=[(1, "H1")].

            ``# H1 \\n\\n ## H2.1 \\n\\n Content1 ## H2.2 \\n\\n Content2``, headings=[(1, "H1")].

        section_level: Deepest heading level in this chunk.

            ``section_level`` is derived from the full section paths covered by
            the chunk, not from the ancestor-only ``headings`` metadata.

        document_title: Title of the source document.
        document_path: File path of the source document, if split from a file.
        start_line: 1-based line number where this chunk begins in the source.
        end_line: 1-based line number where this chunk ends in the source.
    """

    chunk_id: str
    chunk_type: str = "paragraph"
    body: str = ""
    token_count: int = 0
    estimated_token_count: int = 0
    headings: HeadingPath = ()
    section_level: int = 0
    document_title: str = ""
    document_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None


def render_heading_path(path: HeadingPath) -> str:
    """Render a full heading breadcrumb path as nested Markdown headings."""

    def _render_heading(level: int, title: str) -> str:
        """Render a heading as a Markdown ATX heading string."""
        if level <= 0:
            return title.strip()
        return f"{'#' * level} {title.strip()}"

    return join_rendered_blocks(
        [_render_heading(level, title) for level, title in path]
    )


def common_heading_path(paths: Iterable[HeadingPath]) -> HeadingPath:
    iterator = iter(paths)
    first = tuple(next(iterator, ()))
    common = first
    for path in iterator:
        limit = min(len(common), len(path))
        index = 0
        while index < limit and common[index] == path[index]:
            index += 1
        common = common[:index]
        if not common:
            break
    return common


def ancestor_heading_path(paths: Iterable[HeadingPath]) -> HeadingPath:
    path_list = [tuple(path) for path in paths]
    if not path_list:
        return ()

    first = path_list[0]
    if all(path == first for path in path_list):
        return first[:-1] if first else ()

    return common_heading_path(path_list)


@dataclass(slots=True)
class Entry:
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
class ChunkDraft:
    """Intermediate chunk holding grouped entries, token estimate, and split source.

    Args:
        entries: List of entries to be merged into the chunk, with heading context and body.
        headings: The full heading path context for the chunk, used for rendering and metadata.

            ``# H1 \n\n ## H2.1 \n\n Content1``, headings=[(1, "H1"), (2, "H2.1")].

            ``# H1 \n\n ## H2.1 \n\n Content1 ## H2.2 \n\n Content2``, headings=[(1, "H1")].

        headings_token_count: The token count for the chunk's full heading path.
        body_token_count: The token count for the chunk body (sum of entry body_token_count plus separator deltas).
        token_count: `headings_token_count` + `body_token_count`.
        split_origin: The source of the split that produced this draft, for debugging/analysis.
        chunk_type: The type of content in the chunk (e.g. "paragraph", "code_block"), used for metadata.

    """

    entries: list[Entry]
    headings: HeadingPath
    headings_token_count: int
    body_token_count: int
    token_count: int
    split_origin: Literal["section", "fragment", "text_piece", "merge"] = "section"
    chunk_type: str = "paragraph"


@dataclass(slots=True, frozen=True)
class SectionTokenCounts:
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
class MeasuredSection:
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
    counts: SectionTokenCounts
    tail_text: str
    can_emit_as_single_chunk: bool
    children: tuple[MeasuredSection, ...] = ()

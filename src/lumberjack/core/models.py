from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from .utils import join_markdown

HeadingKey: TypeAlias = tuple[int, str]  # noqa: UP040
HeadingPath: TypeAlias = tuple[HeadingKey, ...]  # noqa: UP040


@dataclass(slots=True, frozen=True)
class MarkdownInline:
    """Normalized inline node (text, link, code, emphasis, etc.).

    Attributes:
        kind: Inline node type (e.g. ``"text"``, ``"link"``, ``"code_inline"``,
            ``"strong"``, ``"em"``, ``"image"``).
        text: Rendered plain text of this node.
        children: Nested inline children (e.g. emphasis wrapping text).
        attrs: Additional attributes (``"href"``, ``"src"``, ``"title"``, etc.).
    """

    kind: str
    text: str = ""
    children: tuple[MarkdownInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class MarkdownBlock:
    """Block-level node with rendered text, line range, inline children, and nested blocks.

    Attributes:
        kind: Block type (e.g. ``"paragraph"``, ``"heading"``, ``"code_fence"``,
            ``"blockquote"``, ``"list"``, ``"list_item"``, ``"table"``,
            ``"html_block"``, ``"math_block"``).
        text: Rendered source text of this block.
        start_line: 1-based line number where the block begins.
        end_line: 1-based line number where the block ends.
        children: Nested child blocks for container types (``"blockquote"``,
            ``"list"``, ``"list_item"``).  Empty for leaf blocks.
        inlines: Normalized inline nodes parsed from the block content.
            Populated for ``"paragraph"`` and ``"heading"`` blocks.
        attrs: Additional attributes (e.g. heading level, list style, code language).
    """

    kind: str
    text: str
    start_line: int | None = None
    end_line: int | None = None
    children: tuple[MarkdownBlock, ...] = ()
    inlines: tuple[MarkdownInline, ...] = ()
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
    blocks: list[MarkdownBlock] = field(default_factory=list)
    children: list[SectionNode] = field(default_factory=list)
    index: int = 0
    start_line: int | None = None
    title_inlines: tuple[MarkdownInline, ...] = ()

    @property
    def heading_key(self) -> HeadingKey:
        return (self.level, self.title)

    def add_block(self, block: MarkdownBlock) -> None:
        """Append a block (roughly one paragraph) to this section."""
        self.blocks.append(block)

    def add_child(self, child: SectionNode) -> None:
        self.children.append(child)


@dataclass(slots=True, frozen=True)
class DocumentAST:
    """Parsed document with root section tree, raw source, and metadata.

    Attributes:
        title: Document title.  Priority: user-provided ``document_title``,
            then front matter ``title`` field, then first level-1 heading,
            then ``"Anonymous"``.
        source: Raw Markdown source text.
        root: Root section node of the heading tree.
        metadata: Front matter key-value pairs parsed from YAML front matter,
            or externally provided metadata as fallback.
        reference_definitions: Link/image reference definitions (``[label]: url``).
    """

    title: str
    source: str
    root: SectionNode
    metadata: dict[str, Any] = field(default_factory=dict)
    reference_definitions: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class BaseParams:
    """Common parameters for all block kinds.

    Attributes:
        isolated: When ``True``, the block is always emitted as its own
            chunk (no merge with adjacent content).
        split: Whether to allow splitting this block kind when oversized.
            When ``False``, oversized blocks are kept intact even if they
            exceed ``max_tokens``.
        max_tokens: Per-block-kind token budget override.  When ``None``
            (the default), the current splitter budget is used.
    """

    isolated: bool = False
    split: bool = True
    max_tokens: int | None = None


@dataclass(slots=True, frozen=True)
class TableBlockParams(BaseParams):
    """Table-specific oversized block splitting options.

    Attributes:
        isolated: Common block isolation flag inherited from :class:`BaseParams`.
        split: Common oversized-block splitting flag inherited from :class:`BaseParams`.
        max_tokens: Common per-kind budget override inherited from :class:`BaseParams`.
        repeat_header: When ``True``, each split table piece repeats the table
            header.  When ``False``, only the first split piece includes the
            header rows.
    """

    repeat_header: bool = True


class BlockKindRegistry:
    """Registry of block kinds the splitter handles for merge/split decisions.

    Create an instance by passing the known block kinds from a parser:
        registry = BlockKindRegistry(parser.block_kinds)
    """

    def __init__(self, kinds: frozenset[str]) -> None:
        self._kinds = kinds

    @property
    def kinds(self) -> frozenset[str]:
        """All registered block kind names."""
        return self._kinds

    def default_handling(self) -> dict[str, BaseParams]:
        """Return all registered kinds mapped to default block params."""
        return {
            kind: TableBlockParams()
            if kind in {"table", "html_table"}
            else BaseParams()
            for kind in sorted(self._kinds)
        }

    def validate_kind(self, kind: str) -> str:
        """Validate and return *kind*, raising :class:`ValueError` if unknown."""
        if kind not in self._kinds:
            valid = ", ".join(sorted(self._kinds))
            raise ValueError(f"Unknown block kind: {kind!r} (valid: {valid})")
        return kind


@dataclass(slots=True, frozen=True)
class SplitOptions:
    """Parameters controlling how documents are split into chunks.

    Attributes:
        max_tokens: Target maximum token count per chunk.
        ideal_max_tokens_ratio: Ratio of ``max_tokens`` used as the preferred
            split budget before post-processing merge passes. Must be greater
            than 0 and at most 1.
        ideal_max_tokens: Computed as ``max(1, int(max_tokens *
            ideal_max_tokens_ratio))``.  This is the effective split budget
            used during chunking.
        merge_below_tokens: Soft threshold for merging short tails produced by
            fragment or text fallback splitting. This is not a final minimum
            chunk size. A negative value or ``None`` disables merging entirely;
            otherwise the value must be non-negative and smaller than ``max_tokens``.
        skip_empty_sections: When True, discard chunks that contain only a heading
            with no body content. Chunks with zero rendered tokens are always discarded
            regardless of this setting.
        render_headings: When False, omit the chunk's common heading breadcrumb from
            the rendered ``Chunk.body`` while keeping ``Chunk.headings`` metadata
            intact. Both splitters are render-aware: the split budget grows to fill
            ``max_tokens`` with body content (the heading tokens are reclaimed), so
            ``token_count == estimated_token_count == measured body tokens``.
            Internal relative headings (e.g. sibling titles inside a merged chunk in
            the recursive splitter) always render regardless of this flag, because
            they are chunk-internal structure rather than the common prefix.
        block_options: Per-block-kind configuration. Keys are lowercase block
            kind strings matching :attr:`MarkdownBlock.kind` values; values are
            :class:`BaseParams` instances. Callers that need parser-specific
            defaults should resolve them before constructing
            :class:`SplitOptions`.
        standalone_kinds: Block kinds marked as isolated (cached).
    """

    max_tokens: int = 1200
    ideal_max_tokens_ratio: float = 0.8
    merge_below_tokens: int | None = 50
    skip_empty_sections: bool = True
    render_headings: bool = True
    block_options: dict[str, BaseParams] = field(default_factory=dict)

    # Cached derived fields — computed in __post_init__.
    ideal_max_tokens: int = field(init=False, repr=False)
    standalone_kinds: frozenset[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ideal_max_tokens",
            max(1, int(self.max_tokens * self.ideal_max_tokens_ratio)),
        )
        object.__setattr__(
            self,
            "standalone_kinds",
            frozenset(kind for kind, cfg in self.block_options.items() if cfg.isolated),
        )


@dataclass(slots=True, frozen=True)
class Chunk:
    """Final chunk payload with rendered and estimated token counts plus source metadata.

    Attributes:
        chunk_id: Unique identifier for this chunk.
        chunk_type: Origin block type (e.g. ``"paragraph"``, ``"heading"``,
            ``"code_fence"``, ``"document"``).
        body: Rendered chunk text, optionally including heading breadcrumbs.
        token_count: Token count measured by the configured tokenizer.
        estimated_token_count: Estimated token count when exact counting is unavailable.
        headings: Tuple of ``(level, title)`` pairs representing the heading path.

            ``# H1 \\n\\n ## H2.1 \\n\\n Content1``, headings=[(1, "H1"), (2, "H2.1")].

            ``# H1 \\n\\n ## H2.1 \\n\\n Content1 ## H2.2 \\n\\n Content2``, headings=[(1, "H1")].

        section_level: Deepest heading level in this chunk.

            ``section_level = max((level for level, _ in headings), default=0)``.

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

    return join_markdown([_render_heading(level, title) for level, title in path])


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

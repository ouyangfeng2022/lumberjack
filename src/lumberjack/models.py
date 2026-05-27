from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

type HeadingKey = tuple[int, str]
type HeadingPath = tuple[HeadingKey, ...]


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
            ``"html_block"``, ``"hr"``).
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
class SplitOptions:
    """Parameters controlling how documents are split into chunks.

    Attributes:
        max_tokens: Target maximum token count per chunk.
        merge_below_tokens: Soft threshold for merging short tails produced by
            fragment or text fallback splitting. This is not a final minimum
            chunk size.
        overlap_tokens: Number of tokens to duplicate between adjacent chunks.
        merge_small_chunks: Combine adjacent chunks that share the same heading path.
        isolate_front_matter: Always emit front matter as the first chunk.
        skip_empty_sections: When True, discard chunks that contain only a heading
            with no body content. Chunks with zero rendered tokens are always discarded
            regardless of this setting.
        recursive_split: When True, split oversized direct section bodies in splitters
            that support strict heading-level output.
        split_oversized_blocks: Block kinds to split when they exceed ``max_tokens``.
            Must be a frozenset of lowercase strings matching :attr:`MarkdownBlock.kind`
            values.
        standalone_blocks: Block kinds that must be emitted as independent chunks,
            never merged with adjacent blocks. Defaults to ``{"table", "code_block",
            "code_fence"}``.  Set to an empty frozenset to disable.
    """

    max_tokens: int = 1200
    merge_below_tokens: int = 50
    overlap_tokens: int = 0
    merge_small_chunks: bool = True
    isolate_front_matter: bool = True
    skip_empty_sections: bool = True
    recursive_split: bool = False
    split_oversized_blocks: frozenset[str] = frozenset(
        {
            "paragraph",
            "blockquote",
            "html_block",
        }
    )
    standalone_blocks: frozenset[str] = frozenset(
        {
            "table",
            "code_block",
            "code_fence",
        }
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
        section_level: Deepest heading level in this chunk.
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

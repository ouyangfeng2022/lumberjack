from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

type HeadingKey = tuple[int, str]
type HeadingPath = tuple[HeadingKey, ...]


@dataclass(slots=True, frozen=True)
class MarkdownInline:
    """Normalized inline node (text, link, code, emphasis, etc.)."""

    kind: str
    text: str = ""
    children: tuple[MarkdownInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class MarkdownBlock:
    """Block-level node with rendered text, line range, inline children, and nested blocks."""

    kind: str
    text: str
    start_line: int | None = None
    end_line: int | None = None
    children: tuple[MarkdownBlock, ...] = ()
    inlines: tuple[MarkdownInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SectionNode:
    """Heading-tree node representing a section and its children."""

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
    """Parsed document with root section tree, raw source, and metadata."""

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
        merge_below_tokens: Soft threshold for small-chunk merging. Adjacent
            chunks below this size are merge candidates when merging is enabled.
        overlap_tokens: Number of tokens to duplicate between adjacent chunks.
        retain_headings: Prepend rendered heading breadcrumbs to :attr:`Chunk.body`.
        include_common_headings: When ``retain_headings`` is True, include the shared
            common heading prefix in :attr:`Chunk.body`.  Only effective when
            ``retain_headings`` is also True.
        merge_small_chunks: Combine adjacent chunks that share the same heading path.
        isolate_front_matter: Always emit front matter as the first chunk.
        split_oversized_blocks: Block kinds to split when they exceed ``max_tokens``.
            Must be a frozenset of lowercase strings matching :attr:`MarkdownBlock.kind`
            values.
    """

    max_tokens: int = 1200
    merge_below_tokens: int = 50
    overlap_tokens: int = 0
    retain_headings: bool = True
    include_common_headings: bool = True
    merge_small_chunks: bool = True
    isolate_front_matter: bool = True
    split_oversized_blocks: frozenset[str] = frozenset(
        {
            "paragraph",
            "blockquote",
            "html_block",
        }
    )


@dataclass(slots=True, frozen=True)
class Chunk:
    """Final chunk payload with type, body content, token count, heading breadcrumbs, and line range."""

    chunk_id: str
    chunk_type: str = "paragraph"
    body: str = ""
    token_count: int = 0
    headings: HeadingPath = ()
    section_level: int = 0
    document_title: str = ""
    document_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None

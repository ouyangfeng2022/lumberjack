from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

type HeadingKey = tuple[int, str]
type HeadingPath = tuple[HeadingKey, ...]


@dataclass(slots=True)
class MarkdownInline:
    """Normalized inline node (text, link, code, emphasis, etc.)."""

    kind: str
    text: str = ""
    children: list[MarkdownInline] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MarkdownBlock:
    """Block-level node with rendered text, line range, inline children, and nested blocks."""

    kind: str
    text: str
    start_line: int | None = None
    end_line: int | None = None
    children: list[MarkdownBlock] = field(default_factory=list)
    inlines: list[MarkdownInline] = field(default_factory=list)
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
    title_inlines: list[MarkdownInline] = field(default_factory=list)

    @property
    def heading_key(self) -> HeadingKey:
        return (self.level, self.title)

    def add_block(self, block: MarkdownBlock) -> None:
        self.blocks.append(block)

    def add_child(self, child: SectionNode) -> None:
        self.children.append(child)


@dataclass(slots=True)
class DocumentAST:
    """Parsed document with root section tree, raw source, and metadata."""

    title: str
    source: str
    root: SectionNode
    metadata: dict[str, Any] = field(default_factory=dict)
    reference_definitions: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(slots=True)
class SplitOptions:
    """Parameters controlling how documents are split into chunks."""

    max_tokens: int = 1200
    min_tokens: int = 50
    overlap_tokens: int = 0
    retain_headings: bool = True
    merge_small_chunks: bool = True
    split_oversized_blocks: tuple[str, ...] = (
        "paragraph",
        "blockquote",
        "html_block",
    )


@dataclass(slots=True)
class Chunk:
    """Final chunk payload with text, token count, heading breadcrumbs, and line range."""

    chunk_id: str
    text: str
    body: str = ""
    token_count: int = 0
    headings: HeadingPath = ()
    section_level: int = 0
    document_title: str = ""
    document_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None

    def __post_init__(self) -> None:
        # Backward compatibility for the legacy positional signature:
        # Chunk(chunk_id, text, token_count, headings, section_level, document_title, ...)
        if (
            isinstance(self.body, int)
            and isinstance(self.token_count, tuple)
            and isinstance(self.headings, int)
            and isinstance(self.section_level, str)
            and not self.document_title
        ):
            import warnings

            warnings.warn(
                "Positional Chunk() signature without 'body' is deprecated; "
                "use keyword arguments or include body=''.",
                DeprecationWarning,
                stacklevel=2,
            )
            legacy_token_count = self.body
            legacy_headings = self.token_count
            legacy_section_level = self.headings
            legacy_document_title = self.section_level

            self.body = ""
            self.token_count = legacy_token_count
            self.headings = legacy_headings
            self.section_level = legacy_section_level
            self.document_title = legacy_document_title

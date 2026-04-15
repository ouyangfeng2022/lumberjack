from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

type HeadingKey = tuple[int, str]
type HeadingPath = tuple[HeadingKey, ...]


@dataclass(slots=True)
class MarkdownInline:
    kind: str
    text: str = ""
    children: list[MarkdownInline] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MarkdownBlock:
    kind: str
    text: str
    start_line: int | None = None
    end_line: int | None = None
    children: list[MarkdownBlock] = field(default_factory=list)
    inlines: list[MarkdownInline] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SectionNode:
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
    title: str
    source: str
    root: SectionNode
    metadata: dict[str, Any] = field(default_factory=dict)
    reference_definitions: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(slots=True)
class SplitOptions:
    max_tokens: int = 1200
    min_tokens: int = 50
    overlap_tokens: int = 0
    retain_headings: bool = True
    merge_small_chunks: bool = True
    split_oversized_blocks: tuple[str, ...] = (
        "paragraph",
        "blockquote",
        "html_block",
        "link_reference_definition",
    )


@dataclass(slots=True)
class Chunk:
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

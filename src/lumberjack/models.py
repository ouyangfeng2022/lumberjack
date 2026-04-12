from __future__ import annotations

from dataclasses import dataclass, field

type HeadingKey = tuple[int, str]
type HeadingPath = tuple[HeadingKey, ...]


@dataclass(slots=True)
class MarkdownBlock:
    kind: str
    text: str
    start_line: int | None = None
    end_line: int | None = None
    token_count: int = 0


@dataclass(slots=True)
class SectionNode:
    level: int
    title: str
    path: HeadingPath = ()
    blocks: list[MarkdownBlock] = field(default_factory=list)
    children: list[SectionNode] = field(default_factory=list)
    index: int = 0
    start_line: int | None = None

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


@dataclass(slots=True)
class SplitOptions:
    max_tokens: int = 1200
    min_tokens: int = 200
    retain_headings: bool = True
    merge_small_chunks: bool = True


@dataclass(slots=True)
class Chunk:
    text: str
    token_count: int
    headings: HeadingPath = ()
    section_level: int = 0

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ..base.interfaces import SplitterProtocol, TokenizerProtocol
from ..models import (
    Chunk,
    DocumentAST,
    HeadingPath,
    MarkdownBlock,
    SectionNode,
    SplitOptions,
)
from ..utils import join_markdown, render_heading_path
from .tokenizers import SimpleCharTokenizer

if TYPE_CHECKING:
    from collections.abc import Iterable

SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?\u3002\uFF01\uFF1F])\s+")
PROTECTED_SPAN_RE = re.compile(r"<https?://[^\s>]+>|https?://[^\s)>\]]+")
SEPARATOR = "\n\n"
SplitOrigin = Literal["section", "fragment", "text_piece"]
THEMATIC_BREAK_ATTACH_PREVIOUS_KINDS = frozenset(
    {
        "paragraph",
        "blockquote",
        "html_block",
        "math_block",
        "math_block_eqno",
    }
)


def max_line(left: int | None, right: int | None) -> int | None:
    lines = [line for line in (left, right) if line is not None]
    return max(lines, default=None)


def count_joined(
    tokenizer: TokenizerProtocol,
    current: str,
    next_part: str,
    separator: str = "\n\n",
) -> int:
    if not current:
        return tokenizer.count(next_part)
    if not next_part:
        return tokenizer.count(current)
    return tokenizer.count(f"{current}{separator}{next_part}")


def heading_path_token_count(tokenizer: TokenizerProtocol, path: HeadingPath) -> int:
    if not path:
        return 0
    tokens = 0
    for level, title in path:
        if title:
            tokens = tokens + tokenizer.count(
                "#" * level + " " + title + SEPARATOR, cache=True
            )
    return tokens


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


def attach_thematic_breaks(blocks: list[MarkdownBlock]) -> list[MarkdownBlock]:
    attached: list[MarkdownBlock] = []
    pending: list[MarkdownBlock] = []

    for block in blocks:
        if block.kind == "thematic_break":
            if attached and attached[-1].kind in THEMATIC_BREAK_ATTACH_PREVIOUS_KINDS:
                attached[-1] = MarkdownBlock(
                    kind=attached[-1].kind,
                    text=join_markdown([attached[-1].text, block.text]),
                    start_line=attached[-1].start_line,
                    end_line=max_line(attached[-1].end_line, block.end_line),
                    children=attached[-1].children,
                    inlines=attached[-1].inlines,
                    attrs=attached[-1].attrs,
                )
            else:
                pending.append(block)
            continue

        if pending:
            start_lines = [break_block.start_line for break_block in pending]
            start_lines.append(block.start_line)
            block = MarkdownBlock(
                kind=block.kind,
                text=join_markdown(
                    [*(break_block.text for break_block in pending), block.text]
                ),
                start_line=min(
                    (line for line in start_lines if line is not None), default=None
                ),
                end_line=block.end_line,
                children=block.children,
                inlines=block.inlines,
                attrs=block.attrs,
            )
            pending = []
        attached.append(block)

    if pending:
        attached.extend(pending)

    return attached


@dataclass(slots=True)
class _Entry:
    """Rendered content unit with heading context and line range, a flattened SectionNode.

    Attributes:
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
    """Intermediate chunk holding grouped entries, token estimate, and split source."""

    entries: list[_Entry]
    token_count: int
    split_origin: SplitOrigin = "section"


@dataclass(slots=True, frozen=True)
class _SectionTokenCounts:
    """Token estimates for a section heading, own body, and full subtree.

    Attributes:
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

    Attributes:
        node: The original SectionNode.
        counts: Cached token counts for the section's title, body, and full subtree.
        children: Measured child sections with the same structure as the original.
    """

    node: SectionNode
    counts: _SectionTokenCounts
    children: tuple[_MeasuredSection, ...] = ()


class TextSplitter:
    """Splits oversized text blocks into token-bounded pieces."""

    def __init__(self, tokenizer: TokenizerProtocol, overlap_tokens: int = 0):
        self.tokenizer = tokenizer
        self.overlap_tokens = overlap_tokens

    def split_oversized_block(
        self,
        block: MarkdownBlock,
        *,
        max_tokens: int,
        allowed_kinds: frozenset[str] | set[str],
    ) -> list[str] | None:
        if block.kind.lower() not in allowed_kinds:
            return None

        if block.kind in {"code_block", "code_fence"}:
            return self.split_code_block(block, max_tokens=max_tokens)

        if block.kind == "list" and block.children:
            return self.split_list_block(block, max_tokens=max_tokens)

        return self.split_text(block.text, max_tokens=max_tokens)

    def split_code_block(
        self,
        block: MarkdownBlock,
        *,
        max_tokens: int,
    ) -> list[str]:
        info = str(block.attrs.get("info") or block.attrs.get("language") or "").strip()
        literal = str(block.attrs.get("literal") or "")
        open_fence = f"```{info}".rstrip()
        close_fence = "```"
        empty_render = f"{open_fence}\n{close_fence}"
        wrapper_tokens = self.tokenizer.count(empty_render, cache=True)
        if wrapper_tokens >= max_tokens:
            return [block.text]

        code_budget = max_tokens - wrapper_tokens
        pieces = self.split_text(literal, max_tokens=code_budget)
        return [f"{open_fence}\n{piece}\n{close_fence}" for piece in pieces]

    def split_list_block(
        self,
        block: MarkdownBlock,
        *,
        max_tokens: int,
    ) -> list[str]:
        items = [child.text for child in block.children if child.text]
        if len(items) <= 1:
            return self.split_text(
                block.text,
                max_tokens=max_tokens,
            )

        packed = self.pack_parts(
            items,
            max_tokens,
            separator="\n",
            overlap_tokens=0,
        )
        if all(self.tokenizer.count(part) <= max_tokens for part in packed):
            return packed

        pieces: list[str] = []
        for item in items:
            if self.tokenizer.count(item) <= max_tokens:
                pieces.append(item)
                continue
            pieces.extend(
                self.split_text(
                    item,
                    max_tokens=max_tokens,
                )
            )
        return pieces

    def split_text(
        self,
        text: str,
        *,
        max_tokens: int,
    ) -> list[str]:
        overlap_tokens = self.overlap_tokens
        if self.tokenizer.count(text) <= max_tokens:
            return [text]

        if any(
            self.tokenizer.count(m.group(0)) > max_tokens
            for m in PROTECTED_SPAN_RE.finditer(text)
        ):
            return [text]

        for separator in ("\n\n", "\n"):
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) > 1:
                packed = self.pack_parts(
                    parts,
                    max_tokens,
                    separator=separator,
                    overlap_tokens=overlap_tokens,
                )
                if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                    return packed

        sentence_parts = [
            part.strip() for part in SENTENCE_BREAK_RE.split(text) if part.strip()
        ]
        if len(sentence_parts) > 1:
            packed = self.pack_parts(
                sentence_parts,
                max_tokens,
                separator=" ",
                overlap_tokens=overlap_tokens,
            )
            if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                return packed

        word_parts = [part for part in text.split(" ") if part]
        if len(word_parts) > 1:
            packed = self.pack_parts(
                word_parts,
                max_tokens,
                separator=" ",
                overlap_tokens=overlap_tokens,
            )
            if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                return packed

        return self.hard_split(text, max_tokens, overlap_tokens=overlap_tokens)

    def pack_parts(
        self,
        parts: list[str],
        max_tokens: int,
        *,
        separator: str,
        overlap_tokens: int,
    ) -> list[str]:
        packed: list[str] = []
        current_parts: list[str] = []
        current_joined = ""
        current_tokens = 0
        for part in parts:
            candidate_tokens = count_joined(
                self.tokenizer, current_joined, part, separator
            )
            if current_parts and candidate_tokens > max_tokens:
                packed.append(current_joined)
                overlap_parts, _ = self.tail_parts_within_budget(
                    current_joined,
                    max_tokens=overlap_tokens,
                    separator=separator,
                )
                current_parts = [*overlap_parts, part]
                current_joined = separator.join(current_parts)
                current_tokens = self.tokenizer.count(current_joined)
                if current_tokens > max_tokens:
                    current_parts = [part]
                    current_joined = part
                    current_tokens = self.tokenizer.count(part)
            else:
                current_parts.append(part)
                current_joined = separator.join(current_parts)
                current_tokens = candidate_tokens
        if current_parts:
            packed.append(current_joined)
        return packed

    def hard_split(
        self,
        text: str,
        max_tokens: int,
        *,
        overlap_tokens: int,
    ) -> list[str]:
        parts: list[str] = []
        current = ""
        for character in text:
            candidate = f"{current}{character}"
            if current and self.tokenizer.count(candidate) > max_tokens:
                parts.append(current)
                overlap = self.suffix_within_budget(current, overlap_tokens)
                current = f"{overlap}{character}" if overlap else character
                if self.tokenizer.count(current) > max_tokens:
                    current = character
            else:
                current = candidate
        if current:
            parts.append(current)
        return [part.strip() for part in parts if part.strip()]

    def tail_parts_within_budget(
        self,
        current_joined: str,
        *,
        max_tokens: int,
        separator: str,
    ) -> tuple[list[str], int]:
        if max_tokens <= 0 or not current_joined:
            return ([], 0)
        parts = current_joined.split(separator)
        tail: list[str] = []
        for part in reversed(parts):
            candidate = separator.join([part, *tail]) if tail else part
            if self.tokenizer.count(candidate) > max_tokens:
                break
            tail = [part, *tail]
        tail_joined = separator.join(tail) if tail else ""
        return (tail, self.tokenizer.count(tail_joined))

    def suffix_within_budget(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0 or not text:
            return ""
        if self.tokenizer.count(text) <= max_tokens:
            return text

        for start in range(1, len(text)):
            suffix = text[start:]
            if any(
                m.start() < start < m.end() for m in PROTECTED_SPAN_RE.finditer(text)
            ):
                continue
            if self.tokenizer.count(suffix) <= max_tokens:
                return suffix
        return ""


class _BaseMarkdownSplitter(SplitterProtocol):
    """Shared state and helpers for markdown-based splitter strategies."""

    def __init__(
        self,
        tokenizer: TokenizerProtocol | None = None,
        options: SplitOptions | None = None,
    ):
        self.tokenizer = tokenizer or SimpleCharTokenizer()
        self.options = options or SplitOptions()
        self._text_splitter = TextSplitter(self.tokenizer, self.options.overlap_tokens)

    def split(self, document: DocumentAST) -> list[Chunk]:
        self._validate_options()
        front_matter_block = self._extract_front_matter(document.root)
        measured_root = self._measure_section(document.root)
        drafts = self._split_section(measured_root)
        drafts = self._post_process_drafts(drafts)
        finalized = self._finalize_chunks(drafts, document)
        if front_matter_block is not None:
            finalized.insert(
                0, self._make_front_matter_chunk(front_matter_block, document)
            )
        return finalized

    def _split_section(self, root: _MeasuredSection) -> list[_ChunkDraft]:
        raise NotImplementedError

    def _post_process_drafts(self, drafts: list[_ChunkDraft]) -> list[_ChunkDraft]:
        return drafts

    def _validate_options(self) -> None:
        if self.options.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")
        if self.options.merge_below_tokens < 0:
            raise ValueError("merge_below_tokens must be non-negative")
        if self.options.overlap_tokens < 0:
            raise ValueError("overlap_tokens must be non-negative")
        if self.options.merge_below_tokens >= self.options.max_tokens:
            raise ValueError("merge_below_tokens must be smaller than max_tokens")
        if self.options.overlap_tokens >= self.options.max_tokens:
            raise ValueError("overlap_tokens must be smaller than max_tokens")
        if self.options.include_common_headings and not self.options.retain_headings:
            print(
                "include_common_headings cannot be True when retain_headings is False, setting include_common_headings to False"
            )
            object.__setattr__(self.options, "include_common_headings", False)

    def _extract_front_matter(self, root: SectionNode) -> MarkdownBlock | None:
        if (
            self.options.isolate_front_matter
            and root.blocks
            and root.blocks[0].kind == "front_matter"
        ):
            return root.blocks.pop(0)
        return None

    def _make_front_matter_chunk(
        self, block: MarkdownBlock, document: DocumentAST
    ) -> Chunk:
        token_count = self.tokenizer.count(block.text)
        return Chunk(
            chunk_id="chunk-0000",
            chunk_type="front_matter",
            body=block.text,
            token_count=token_count,
            estimated_token_count=token_count,
            headings=(),
            section_level=0,
            document_title=document.title,
            document_path=document.metadata.get("path"),
            start_line=block.start_line,
            end_line=block.end_line,
        )

    def _measure_section(self, section: SectionNode) -> _MeasuredSection:
        """Return a measured wrapper for *section* and all descendants."""
        children = tuple(self._measure_section(child) for child in section.children)

        body_token_count = 0
        if section.blocks:
            for block in section.blocks:
                body_token_count += self.tokenizer.count(
                    block.text + SEPARATOR, cache=True
                )

        if section.level > 0 and self.options.retain_headings:
            title_token_count = self.tokenizer.count(
                "#" * section.level + " " + section.title + SEPARATOR, cache=True
            )
        else:
            title_token_count = 0

        subtree_token_count = (
            title_token_count
            + body_token_count
            + sum(child.counts.subtree for child in children)
        )
        return _MeasuredSection(
            node=section,
            counts=_SectionTokenCounts(
                title=title_token_count,
                body=body_token_count,
                subtree=subtree_token_count,
            ),
            children=children,
        )

    def _split_section_body(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Split a section's own blocks into fragments, then into chunk drafts."""
        node = section.node
        include_prefix = (
            self.options.retain_headings
            and self.options.include_common_headings
            and node.level > 0
        )
        headings = node.path
        blocks = attach_thematic_breaks(node.blocks)
        max_tokens = self.options.max_tokens

        prefix_tokens = (
            heading_path_token_count(self.tokenizer, headings) if include_prefix else 0
        )
        if prefix_tokens >= max_tokens or not blocks:
            entry = self._entry_from_blocks(headings, blocks)
            return [
                _ChunkDraft(
                    entries=[entry],
                    token_count=prefix_tokens + entry.body_token_count,
                    split_origin="fragment",
                )
            ]

        chunks: list[_ChunkDraft] = []
        current_parts: list[str] = []
        current_joined = ""
        current_body_tokens = 0
        current_start_line: int | None = None
        current_end_line: int | None = None

        budget = max(0, max_tokens - prefix_tokens) if prefix_tokens > 0 else max_tokens

        def draft_current() -> _ChunkDraft:
            return self._draft_from_entries(
                [
                    _Entry(
                        headings=headings,
                        body=join_markdown(current_parts),
                        start_line=current_start_line,
                        end_line=current_end_line,
                        body_token_count=current_body_tokens,
                    )
                ],
                split_origin="fragment",
            )

        for block in blocks:
            block_tokens = self.tokenizer.count(f"{block.text}{SEPARATOR}", cache=True)
            candidate_body_tokens = count_joined(
                self.tokenizer, current_joined, block.text
            )
            candidate_total = prefix_tokens + candidate_body_tokens
            if current_parts and candidate_total > max_tokens:
                chunks.append(draft_current())
                current_parts = []
                current_joined = ""
                current_body_tokens = 0
                current_start_line = None
                current_end_line = None

            single_block_total = prefix_tokens + block_tokens
            if single_block_total <= max_tokens:
                current_parts.append(block.text)
                current_body_tokens = count_joined(
                    self.tokenizer, current_joined, block.text
                )
                current_joined = (
                    f"{current_joined}{SEPARATOR}{block.text}"
                    if current_joined
                    else block.text
                )
                if block.start_line is not None and (
                    current_start_line is None or block.start_line < current_start_line
                ):
                    current_start_line = block.start_line
                if block.end_line is not None and (
                    current_end_line is None or block.end_line > current_end_line
                ):
                    current_end_line = block.end_line
                continue

            block_pieces = self._text_splitter.split_oversized_block(
                block,
                max_tokens=budget,
                allowed_kinds=self.options.split_oversized_blocks,
            )
            if block_pieces is None:
                chunks.append(
                    self._draft_from_entries(
                        [
                            _Entry(
                                headings=headings,
                                body=block.text,
                                start_line=block.start_line,
                                end_line=block.end_line,
                                body_token_count=block_tokens,
                            )
                        ],
                        split_origin="fragment",
                    )
                )
                current_parts = []
                current_joined = ""
                current_body_tokens = 0
                current_start_line = None
                current_end_line = None
                continue

            for piece in block_pieces:
                piece_tokens = self.tokenizer.count(piece)
                chunks.append(
                    self._draft_from_entries(
                        [
                            _Entry(
                                headings=headings,
                                body=piece,
                                start_line=block.start_line,
                                end_line=block.end_line,
                                body_token_count=piece_tokens,
                            )
                        ],
                        split_origin="text_piece",
                    )
                )

        if current_parts:
            rendered = join_markdown(current_parts)
            if rendered:
                chunks.append(draft_current())

        return chunks

    def _finalize_chunks(
        self,
        chunks: list[_ChunkDraft],
        document: DocumentAST,
    ) -> list[Chunk]:
        """Convert chunk drafts into final ``Chunk`` objects with rendered body and metadata."""
        finalized: list[Chunk] = []
        doc_path = document.metadata.get("path")
        document_path = str(doc_path) if doc_path is not None else None
        index = 0
        for chunk in chunks:
            headings = common_heading_path(entry.headings for entry in chunk.entries)
            body = self._render_body(chunk.entries, common_headings=headings)
            if not body:
                continue
            if self.options.skip_empty_sections and not any(
                entry.body.strip() for entry in chunk.entries
            ):
                continue
            index += 1
            token_count = self.tokenizer.count(body)
            finalized.append(
                Chunk(
                    chunk_id=f"chunk-{index:04d}",
                    body=body,
                    token_count=token_count,
                    estimated_token_count=chunk.token_count,
                    headings=headings,
                    section_level=headings[-1][0] if headings else 0,
                    document_title=document.title,
                    document_path=document_path,
                    start_line=min(
                        (
                            entry.start_line
                            for entry in chunk.entries
                            if entry.start_line is not None
                        ),
                        default=None,
                    ),
                    end_line=max(
                        (
                            entry.end_line
                            for entry in chunk.entries
                            if entry.end_line is not None
                        ),
                        default=None,
                    ),
                )
            )
        return finalized

    def _entry_from_blocks(
        self,
        headings: HeadingPath,
        blocks: list[MarkdownBlock],
        *,
        body_token_count: int | None = None,
    ) -> _Entry:
        body = join_markdown([block.text for block in blocks])
        start_lines = [b.start_line for b in blocks if b.start_line is not None]
        end_lines = [b.end_line for b in blocks if b.end_line is not None]
        if body_token_count is None:
            body_token_count = 0
            for block in blocks:
                body_token_count += self.tokenizer.count(
                    block.text + SEPARATOR, cache=True
                )

        return _Entry(
            headings=headings,
            body=body,
            start_line=min(start_lines) if start_lines else None,
            end_line=max(end_lines) if end_lines else None,
            body_token_count=body_token_count,
        )

    def _draft_from_entries(
        self,
        entries: list[_Entry],
        *,
        split_origin: SplitOrigin = "section",
    ) -> _ChunkDraft:
        """Build a chunk draft using cached/additive token estimates."""
        return _ChunkDraft(
            entries=entries.copy(),
            token_count=self._estimate_entries(entries),
            split_origin=split_origin,
        )

    def _estimate_entries(self, entries: list[_Entry]) -> int:
        if not entries:
            return 0

        if not self.options.retain_headings:
            return sum(entry.body_token_count for entry in entries)

        parts: list[int] = []
        common_headings = common_heading_path(entry.headings for entry in entries)
        if self.options.include_common_headings and common_headings:
            parts.append(heading_path_token_count(self.tokenizer, common_headings))

        previous_headings = common_headings
        for entry in entries:
            shared_headings = common_heading_path((previous_headings, entry.headings))
            if len(shared_headings) < len(common_headings):
                shared_headings = common_headings
            relative_headings = entry.headings[len(shared_headings) :]
            entry_token_count = (
                heading_path_token_count(self.tokenizer, relative_headings)
                + entry.body_token_count
            )

            if entry_token_count:
                parts.append(entry_token_count)
            previous_headings = entry.headings

        return sum(parts)

    def _render_body(
        self,
        entries: list[_Entry],
        *,
        common_headings: HeadingPath,
    ) -> str:
        """Render entries into Markdown body content.

        When ``retain_headings`` is True the rendered heading prefix is prepended;
        otherwise only the pure entry body text is included.
        """
        if not entries:
            return ""

        if not self.options.retain_headings:
            parts = [entry.body for entry in entries if entry.body]
            return join_markdown(parts)

        parts: list[str] = []
        include_common = self.options.include_common_headings
        if include_common and common_headings:
            parts.append(render_heading_path(common_headings))

        previous_headings = common_headings
        for entry in entries:
            shared_headings = common_heading_path((previous_headings, entry.headings))
            if len(shared_headings) < len(common_headings):
                shared_headings = common_headings
            relative_headings = entry.headings[len(shared_headings) :]

            entry_parts: list[str] = []
            if relative_headings:
                entry_parts.append(render_heading_path(relative_headings))
            if entry.body:
                entry_parts.append(entry.body)
            rendered = join_markdown(entry_parts)
            if rendered:
                parts.append(rendered)
            previous_headings = entry.headings

        return join_markdown(parts)


class RecursiveMarkdownSplitter(_BaseMarkdownSplitter):
    """Recursively split a Markdown document into token-bounded chunks.

    Unlike SectionSplitter which keeps each heading section intact, this splitter
    recursively breaks down oversized sections and merges small adjacent chunks
    to stay within the configured max_tokens budget.
    """

    def _post_process_drafts(self, drafts: list[_ChunkDraft]) -> list[_ChunkDraft]:
        if self.options.merge_small_chunks:
            return self._merge_small_chunks(drafts)
        return drafts

    def _split_section(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Recursively split a section into chunk drafts."""
        if not (section.node.blocks or section.children or section.node.level > 0):
            return []

        common_heading_token_count: int = (
            heading_path_token_count(self.tokenizer, section.node.path[:-1])
            if self.options.include_common_headings
            else 0
        )
        chunk_token = common_heading_token_count + section.counts.subtree

        if chunk_token <= self.options.max_tokens:
            return [
                _ChunkDraft(
                    entries=self._entries_from_section(section),
                    token_count=chunk_token,
                )
            ]

        if section.children:
            return self._split_section_children(section)  # include section.body

        return self._split_section_body(section)

    def _split_section_children(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Split a section's body blocks and child sections, packing adjacent entries that fit."""
        node = section.node
        chunks: list[_ChunkDraft] = []
        current_entries: list[_Entry] = []
        current_token_count: int = 0

        common_heading_token_count: int = (
            heading_path_token_count(self.tokenizer, node.path)
            if self.options.include_common_headings
            else 0
        )
        budget_token_count = self.options.max_tokens - common_heading_token_count

        def flush_current() -> None:
            nonlocal current_entries, current_token_count

            if not current_entries:
                return

            chunks.append(
                _ChunkDraft(
                    entries=current_entries,
                    token_count=current_token_count,
                )
            )
            current_entries = []
            current_token_count = common_heading_token_count

        def add_packable(entries: list[_Entry], token_count: int) -> None:
            """Add a draft whose tokens are already guaranteed not to exceed max_tokens.

            Args:
                entries (list[_Entry]): list of entry with a common headings
                token_count (int): estimated token counts of the rendered `entries`.
            """
            nonlocal current_entries, current_token_count

            if not current_entries:
                current_entries = entries.copy()
                current_token_count = common_heading_token_count + token_count
                return

            candidate_entries = [*current_entries, *entries]
            candidate_token_count = current_token_count + token_count

            if candidate_token_count > self.options.max_tokens:
                flush_current()
                current_entries = entries.copy()
                current_token_count = common_heading_token_count + token_count
                return

            current_entries = candidate_entries
            current_token_count = candidate_token_count

        if node.blocks:
            body_token_count = section.counts.body
            if body_token_count <= budget_token_count:
                entry = self._entry_from_blocks(
                    node.path,
                    node.blocks,
                    body_token_count=body_token_count,
                )
                add_packable([entry], body_token_count)
            else:
                flush_current()
                chunks.extend(self._split_section_body(section))

        for child in section.children:
            if not (child.node.blocks or child.children or child.node.level > 0):
                continue

            if child.counts.subtree <= budget_token_count:
                entries = self._entries_from_section(child)
                add_packable(entries, child.counts.subtree)
                continue

            flush_current()
            chunks.extend(self._split_section(child))

        flush_current()
        return chunks

    def _entries_from_section(self, section: _MeasuredSection) -> list[_Entry]:
        """Render-ready entries for a section selected as a chunk."""
        node = section.node
        entries: list[_Entry] = []
        if node.blocks or (not section.children and node.level > 0):
            entries.append(
                self._entry_from_blocks(
                    node.path,
                    node.blocks,
                    body_token_count=section.counts.body,
                )
            )

        for child in section.children:
            entries.extend(self._entries_from_section(child))

        return entries

    def _merge_small_chunks(
        self,
        chunks: list[_ChunkDraft],
    ) -> list[_ChunkDraft]:
        """Merge adjacent fragment/text-piece tails below *merge_below_tokens*."""
        if not chunks:
            return chunks

        merged: list[_ChunkDraft] = [chunks[0]]
        for chunk in chunks[1:]:
            previous = merged[-1]
            merged_entries = [*previous.entries, *chunk.entries]
            merged_token_count = self._estimate_entries(merged_entries)
            prev_headings = {e.headings for e in previous.entries}
            can_merge = (
                len(prev_headings) == 1
                and chunk.entries
                and prev_headings == {e.headings for e in chunk.entries}
            )
            if (
                can_merge
                and merged_token_count <= self.options.max_tokens
                and chunk.token_count < self.options.merge_below_tokens
                and chunk.split_origin in {"fragment", "text_piece"}
            ):
                # TODO: prefix tokens ?
                merged[-1] = _ChunkDraft(
                    entries=merged_entries,
                    token_count=merged_token_count,
                    split_origin=previous.split_origin,
                )
            else:
                merged.append(chunk)
        return merged


class SectionMarkdownSplitter(_BaseMarkdownSplitter):
    """Split a document into non-overlapping chunks by heading section.

    Each heading-defined section becomes its own chunk. When ``recursive_split``
    is enabled, oversized section bodies are further split by token budget.
    """

    def _split_section(self, section: _MeasuredSection) -> list[_ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children."""
        chunks: list[_ChunkDraft] = []
        node = section.node

        if node.blocks or node.level > 0:
            if self.options.recursive_split and self._section_body_exceeds_budget(
                section
            ):
                chunks.extend(self._split_section_body(section))
            else:
                chunks.append(
                    self._draft_from_entries(
                        [
                            self._entry_from_blocks(
                                node.path,
                                node.blocks,
                                body_token_count=section.counts.body,
                            )
                        ]
                    )
                )

        for child in section.children:
            chunks.extend(self._split_section(child))

        return chunks

    def _section_body_exceeds_budget(self, section: _MeasuredSection) -> bool:
        if not section.node.blocks:
            return False
        entries = [
            self._entry_from_blocks(
                section.node.path,
                section.node.blocks,
                body_token_count=section.counts.body,
            )
        ]
        return self._estimate_entries(entries) > self.options.max_tokens


SPLITTER_REGISTRY: dict[str, type[_BaseMarkdownSplitter]] = {
    "default": RecursiveMarkdownSplitter,
    "section": SectionMarkdownSplitter,
    "recursive": RecursiveMarkdownSplitter,
}


def create_splitter(
    name: str,
    tokenizer: TokenizerProtocol | None = None,
    options: SplitOptions | None = None,
) -> SplitterProtocol:
    """Instantiate a splitter by name."""
    normalized = name.strip().lower()
    cls = SPLITTER_REGISTRY.get(normalized)
    if cls is None:
        raise ValueError(f"Unsupported splitter: {name}")
    return cls(tokenizer=tokenizer, options=options)

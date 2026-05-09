from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ..base.interfaces import SplitterProtocol, TokenizerProtocol
from ..models import Chunk, DocumentAST, HeadingPath, MarkdownBlock, SectionNode, SplitOptions
from ..utils import join_markdown, render_heading_path
from .tokenizers import SimpleCharTokenizer

if TYPE_CHECKING:
    from collections.abc import Iterable

SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?\u3002\uFF01\uFF1F])\s+")
PROTECTED_SPAN_RE = re.compile(r"<https?://[^\s>]+>|https?://[^\s)>\]]+")
SplitOrigin = Literal["section", "fragment", "text_piece"]
SEPARATOR_TOKEN_COUNT = 1
HEADING_TOKEN_COUNT = 1


@dataclass(slots=True)
class _Entry:
    """Rendered content unit with heading context and line range, a flattened SectionNode."""

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
    """Token estimates for a section heading, own body, and full subtree."""

    title: int
    body: int
    subtree: int


@dataclass(slots=True, frozen=True)
class _MeasuredSection:
    """A SectionNode plus splitter-specific token counts for its measured children."""

    node: SectionNode
    counts: _SectionTokenCounts
    children: tuple[_MeasuredSection, ...] = ()


class MarkdownSplitter(SplitterProtocol):
    """Split a parsed Markdown document into token-bounded chunks."""

    def __init__(
        self,
        tokenizer: TokenizerProtocol | None = None,
        options: SplitOptions | None = None,
    ):
        """Initialise the splitter.

        Args:
            tokenizer: Token counter used to measure chunk sizes.
                Defaults to :class:`~lumberjack.core.tokenizers.SimpleCharTokenizer`.
            options: Split parameters (token budget, merge behaviour, etc.).
                Defaults to a zero-customised :class:`~lumberjack.models.SplitOptions`.
        """
        self.tokenizer = tokenizer or SimpleCharTokenizer()
        self.options = options or SplitOptions()
        self._cache_block_token_count: dict[int, int] = {}
        self._cache_title_token_count: dict[str, int] = {}

    def split(self, document: DocumentAST) -> list[Chunk]:
        """Split *document* into chunks respecting token limits and merge preferences."""
        self._validate_options()
        front_matter_block = self._extract_front_matter(document.root)
        self._cache_block_token_count.clear()
        self._cache_title_token_count.clear()
        measured_root = self._measure_section(document.root)
        chunks = self._split_section(measured_root)
        if self.options.merge_small_chunks:
            chunks = self._merge_small_chunks(chunks)
        finalized = self._finalize_chunks(chunks, document)
        if front_matter_block is not None:
            finalized.insert(0, self._make_front_matter_chunk(front_matter_block, document))
        return finalized

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

    def _extract_front_matter(self, root: SectionNode) -> MarkdownBlock | None:
        if (
            self.options.isolate_front_matter
            and root.blocks
            and root.blocks[0].kind == "front_matter"
        ):
            return root.blocks.pop(0)
        return None

    def _make_front_matter_chunk(self, block: MarkdownBlock, document: DocumentAST) -> Chunk:
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

        body = join_markdown([block.text for block in section.blocks])
        body_token_count = self.tokenizer.count(body) if body else 0

        if section.level > 0:
            title_token_count = self._heading_title_token_count(section.title)
        else:
            title_token_count = 0

        for block in section.blocks:
            self._cache_block_token_count[id(block)] = self.tokenizer.count(block.text)

        subtree_token_count = self._joined_token_count(
            [
                title_token_count if section.level > 0 else 0,
                body_token_count,
                *(child.counts.subtree for child in children),
            ]
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

    def _joined_token_count(self, token_counts: Iterable[int]) -> int:
        """Estimate Markdown joining cost with one token per separator."""
        present = [token_count for token_count in token_counts if token_count > 0]
        if not present:
            return 0
        return sum(present) + SEPARATOR_TOKEN_COUNT * (len(present) - 1)

    def _append_token_count(self, current: int, next_count: int) -> int:
        if current <= 0:
            return next_count
        if next_count <= 0:
            return current
        return current + SEPARATOR_TOKEN_COUNT + next_count

    def _block_token_count(self, block: MarkdownBlock) -> int:
        token_count = self._cache_block_token_count.get(id(block))
        if token_count is None:
            token_count = self.tokenizer.count(block.text)
            self._cache_block_token_count[id(block)] = token_count
        return token_count

    def _heading_title_token_count(self, title: str) -> int:
        token_count = self._cache_title_token_count.get(title)
        if token_count is None:
            token_count = self.tokenizer.count(title)
            self._cache_title_token_count[title] = token_count
        return token_count + HEADING_TOKEN_COUNT

    def _heading_path_token_count(self, path: HeadingPath) -> int:
        heading_tokens: list[int] = []
        for _, title in path:
            heading_tokens.append(self._heading_title_token_count(title))
        return self._joined_token_count(heading_tokens)

    def _section_chunk_token_count(self, section: _MeasuredSection) -> int:
        """Estimate rendered tokens for a chunk containing this section subtree."""
        if not self.options.retain_headings:
            return self._section_content_token_count(section)

        if not self.options.include_common_headings:
            common_headings = self._section_entry_common_path(section)
            return self._section_relative_token_count(section, common_headings=common_headings)

        ancestor_tokens = self._heading_path_token_count(section.node.path[:-1])
        return self._joined_token_count([ancestor_tokens, section.counts.subtree])

    def _section_entry_common_path(self, section: _MeasuredSection) -> HeadingPath:
        """Return the common heading prefix for renderable entries in *section*."""
        node = section.node
        paths: list[HeadingPath] = []
        if node.blocks or (not section.children and node.level > 0):
            paths.append(node.path)

        for child in section.children:
            child_common = self._section_entry_common_path(child)
            if child_common:
                paths.append(child_common)

        return self._common_heading_path(paths)

    def _section_relative_token_count(
        self,
        section: _MeasuredSection,
        *,
        common_headings: HeadingPath,
    ) -> int:
        """Estimate a section subtree without the common heading prefix."""
        parts: list[int] = []
        previous_headings = common_headings

        def visit(current: _MeasuredSection) -> None:
            nonlocal previous_headings
            node = current.node

            if node.blocks or (not current.children and node.level > 0):
                shared_headings = self._common_heading_path((previous_headings, node.path))
                if len(shared_headings) < len(common_headings):
                    shared_headings = common_headings
                relative_headings = node.path[len(shared_headings) :]
                token_count = self._joined_token_count(
                    [
                        self._heading_path_token_count(relative_headings),
                        current.counts.body,
                    ]
                )
                if token_count:
                    parts.append(token_count)
                previous_headings = node.path

            for child in current.children:
                visit(child)

        visit(section)
        return self._joined_token_count(parts)

    def _section_content_token_count(self, section: _MeasuredSection) -> int:
        """Estimate a section subtree containing only rendered body content."""
        return self._joined_token_count(
            [
                section.counts.body,
                *(self._section_content_token_count(child) for child in section.children),
            ]
        )

    def _split_section(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Recursively split a section into chunk drafts."""
        if not (section.node.blocks or section.children or section.node.level > 0):
            return []

        chunk_tokens = self._section_chunk_token_count(section)
        if chunk_tokens <= self.options.max_tokens:
            return [
                _ChunkDraft(
                    entries=self._entries_from_section(section),
                    token_count=chunk_tokens,
                )
            ]

        if section.children:
            return self._split_section_children(section)

        return self._split_section_body(section)

    def _split_section_children(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Split a section's body blocks and child sections, packing adjacent entries that fit."""
        node = section.node
        chunks: list[_ChunkDraft] = []
        current_entries: list[_Entry] = []
        current_draft: _ChunkDraft | None = None

        def flush_current() -> None:
            nonlocal current_entries, current_draft
            if not current_entries:
                return
            if current_draft is not None:
                chunks.append(current_draft)
            else:
                chunks.append(self._draft_from_entries(current_entries))
            current_entries = []
            current_draft = None

        def add_packable(draft: _ChunkDraft) -> None:
            """Add a draft whose tokens are already guaranteed not to exceed max_tokens."""
            nonlocal current_entries, current_draft
            if current_draft is None:
                current_entries = draft.entries.copy()
                current_draft = draft
                return
            candidate_entries = [*current_entries, *draft.entries]
            candidate = self._draft_from_entries(candidate_entries)
            if candidate.token_count > self.options.max_tokens:
                flush_current()
                current_entries = draft.entries.copy()
                current_draft = draft
                return
            current_entries = candidate_entries
            current_draft = candidate

        if node.blocks:
            # The first element of entries is body_entry `if section.blocks`.
            body_entry = self._make_entry(
                node.path,
                node.blocks,
                body_token_count=section.counts.body,
            )
            body_draft = self._draft_from_entries([body_entry])
            if body_draft.token_count <= self.options.max_tokens:
                add_packable(body_draft)
            else:
                flush_current()
                chunks.extend(self._split_section_body(section))

        for child in section.children:
            if not (child.node.blocks or child.children or child.node.level > 0):
                continue

            child_token_count = self._section_chunk_token_count(child)
            if child_token_count <= self.options.max_tokens:
                add_packable(
                    _ChunkDraft(
                        entries=self._entries_from_section(child),
                        token_count=child_token_count,
                    )
                )
                continue

            flush_current()
            chunks.extend(self._split_section(child))

        flush_current()
        return chunks

    def _split_section_body(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Split a section's own blocks into fragments, then into chunk drafts."""
        node = section.node
        include_prefix = (
            self.options.retain_headings and self.options.include_common_headings and node.level > 0
        )
        prefix = render_heading_path(node.path) if include_prefix else ""
        return self._split_fragment(
            headings=node.path,
            prefix=prefix,
            blocks=node.blocks.copy(),
        )

    def _split_fragment(
        self,
        *,
        headings: HeadingPath,
        prefix: str,
        blocks: list[MarkdownBlock],
    ) -> list[_ChunkDraft]:
        """Greedy block-level split of a fragment into chunk drafts within token budget."""
        max_tokens = self.options.max_tokens
        prefix_tokens = self._heading_path_token_count(headings) if prefix else 0
        if prefix_tokens >= max_tokens:
            return [
                self._draft_from_entries(
                    [self._make_entry(headings, blocks)],
                    split_origin="fragment",
                )
            ]

        chunks: list[_ChunkDraft] = []
        current_parts: list[str] = []
        current_body_tokens = 0
        current_start_line: int | None = None
        current_end_line: int | None = None

        if not blocks:
            return [
                self._draft_from_entries(
                    [self._make_entry(headings, blocks)],
                    split_origin="fragment",
                )
            ]

        budget = (
            max(0, max_tokens - prefix_tokens - SEPARATOR_TOKEN_COUNT)
            if prefix_tokens > 0
            else max_tokens
        )

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
            block_tokens = self._block_token_count(block)
            candidate_body_tokens = self._append_token_count(current_body_tokens, block_tokens)
            candidate_total = self._joined_token_count([prefix_tokens, candidate_body_tokens])
            if current_parts and candidate_total > max_tokens:
                chunks.append(draft_current())
                current_parts = []
                current_body_tokens = 0
                current_start_line = None
                current_end_line = None

            single_block_total = self._joined_token_count([prefix_tokens, block_tokens])
            if single_block_total <= max_tokens:
                current_parts.append(block.text)
                current_body_tokens = self._append_token_count(current_body_tokens, block_tokens)
                if block.start_line is not None and (
                    current_start_line is None or block.start_line < current_start_line
                ):
                    current_start_line = block.start_line
                if block.end_line is not None and (
                    current_end_line is None or block.end_line > current_end_line
                ):
                    current_end_line = block.end_line
                continue

            block_pieces = self._split_oversized_block(block, max_tokens=budget)
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

    def _split_oversized_block(
        self,
        block: MarkdownBlock,
        max_tokens: int,
    ) -> list[str] | None:
        """Split an oversized block if its kind is allowed, otherwise return ``None``."""
        if block.kind.lower() not in self.options.split_oversized_blocks:
            return None

        if block.kind in {"code_block", "code_fence"}:
            return self._split_code_block(block, max_tokens=max_tokens)

        if block.kind == "list" and block.children:
            return self._split_list_block(block, max_tokens=max_tokens)

        return self._split_text(block.text, max_tokens=max_tokens)

    def _split_code_block(
        self,
        block: MarkdownBlock,
        max_tokens: int,
    ) -> list[str]:
        """Split a fenced/indented code block, preserving fence wrappers in each piece."""
        info = str(block.attrs.get("info") or block.attrs.get("language") or "").strip()
        literal = str(block.attrs.get("literal") or "")
        open_fence = f"```{info}".rstrip()
        close_fence = "```"
        empty_render = f"{open_fence}\n{close_fence}"
        wrapper_tokens = self.tokenizer.count(empty_render)
        if wrapper_tokens >= max_tokens:
            return [block.text]

        code_budget = max_tokens - wrapper_tokens
        pieces = self._split_text(literal, max_tokens=code_budget)
        return [f"{open_fence}\n{piece}\n{close_fence}" for piece in pieces]

    def _split_list_block(
        self,
        block: MarkdownBlock,
        max_tokens: int,
    ) -> list[str]:
        """Split a list block by packing list items, falling back to text splitting."""
        items = [child.text for child in block.children if child.text]
        if len(items) <= 1:
            return self._split_text(
                block.text,
                max_tokens=max_tokens,
            )

        packed = self._pack_parts(
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
                self._split_text(
                    item,
                    max_tokens=max_tokens,
                )
            )
        return pieces

    def _split_text(
        self,
        text: str,
        max_tokens: int,
    ) -> list[str]:
        """Split text through paragraph -> line -> sentence -> word -> hard-split fallback."""
        overlap_tokens = self.options.overlap_tokens
        if self.tokenizer.count(text) <= max_tokens:
            return [text]

        if any(
            self.tokenizer.count(m.group(0)) > max_tokens for m in PROTECTED_SPAN_RE.finditer(text)
        ):
            return [text]

        for separator in ("\n\n", "\n"):
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) > 1:
                packed = self._pack_parts(
                    parts,
                    max_tokens,
                    separator=separator,
                    overlap_tokens=overlap_tokens,
                )
                if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                    return packed

        sentence_parts = [part.strip() for part in SENTENCE_BREAK_RE.split(text) if part.strip()]
        if len(sentence_parts) > 1:
            packed = self._pack_parts(
                sentence_parts,
                max_tokens,
                separator=" ",
                overlap_tokens=overlap_tokens,
            )
            if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                return packed

        word_parts = [part for part in text.split(" ") if part]
        if len(word_parts) > 1:
            packed = self._pack_parts(
                word_parts,
                max_tokens,
                separator=" ",
                overlap_tokens=overlap_tokens,
            )
            if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                return packed

        return self._hard_split(text, max_tokens, overlap_tokens=overlap_tokens)

    def _pack_parts(
        self,
        parts: list[str],
        max_tokens: int,
        *,
        separator: str,
        overlap_tokens: int,
    ) -> list[str]:
        """Greedily pack parts into groups that fit within *max_tokens*, with optional overlap."""
        packed: list[str] = []
        current_parts: list[str] = []
        current_part_tokens: list[int] = []
        current_tokens = 0
        part_tokens = [self.tokenizer.count(part) for part in parts]
        for part, part_token_count in zip(parts, part_tokens, strict=True):
            candidate_tokens = self._append_token_count(current_tokens, part_token_count)
            if current_parts and candidate_tokens > max_tokens:
                packed.append(separator.join(current_parts))
                overlap_parts, overlap_token_count, overlap_part_tokens = (
                    self._tail_parts_within_budget(
                        current_parts,
                        part_tokens=current_part_tokens,
                        max_tokens=overlap_tokens,
                    )
                )
                current_parts = [*overlap_parts, part]
                current_part_tokens = [*overlap_part_tokens, part_token_count]
                current_tokens = self._append_token_count(
                    overlap_token_count,
                    part_token_count,
                )
                if current_tokens > max_tokens:
                    current_parts = [part]
                    current_part_tokens = [part_token_count]
                    current_tokens = part_token_count
            else:
                current_parts = [*current_parts, part]
                current_part_tokens = [*current_part_tokens, part_token_count]
                current_tokens = candidate_tokens
        if current_parts:
            packed.append(separator.join(current_parts))
        return packed

    def _hard_split(
        self,
        text: str,
        max_tokens: int,
        *,
        overlap_tokens: int,
    ) -> list[str]:
        """Character-level split when no higher-level boundary is available."""
        parts: list[str] = []
        current = ""
        for character in text:
            candidate = f"{current}{character}"
            if current and self.tokenizer.count(candidate) > max_tokens:
                parts.append(current)
                overlap = self._suffix_within_budget(current, overlap_tokens)
                current = f"{overlap}{character}" if overlap else character
                if self.tokenizer.count(current) > max_tokens:
                    current = character
            else:
                current = candidate
        if current:
            parts.append(current)
        return [part.strip() for part in parts if part.strip()]

    def _tail_parts_within_budget(
        self,
        parts: list[str],
        *,
        part_tokens: list[int],
        max_tokens: int,
    ) -> tuple[list[str], int, list[int]]:
        if max_tokens <= 0 or not parts:
            return ([], 0, [])

        tail: list[str] = []
        tail_part_tokens: list[int] = []
        tail_tokens = 0
        for part, part_token_count in zip(reversed(parts), reversed(part_tokens), strict=True):
            candidate_tokens = self._append_token_count(part_token_count, tail_tokens)
            if candidate_tokens > max_tokens:
                break
            tail = [part, *tail]
            tail_part_tokens = [part_token_count, *tail_part_tokens]
            tail_tokens = candidate_tokens
        return (tail, tail_tokens, tail_part_tokens)

    def _suffix_within_budget(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0 or not text:
            return ""
        if self.tokenizer.count(text) <= max_tokens:
            return text

        for start in range(1, len(text)):
            suffix = text[start:]
            if any(m.start() < start < m.end() for m in PROTECTED_SPAN_RE.finditer(text)):
                continue
            if self.tokenizer.count(suffix) <= max_tokens:
                return suffix
        return ""

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
                merged[-1] = _ChunkDraft(
                    entries=merged_entries,
                    token_count=merged_token_count,
                    split_origin=previous.split_origin,
                )
            else:
                merged.append(chunk)
        return merged

    def _finalize_chunks(
        self,
        chunks: list[_ChunkDraft],
        document: DocumentAST,
    ) -> list[Chunk]:
        """Convert chunk drafts into final ``Chunk`` objects with rendered body and metadata."""
        finalized: list[Chunk] = []
        doc_path = document.metadata.get("path")
        document_path = str(doc_path) if doc_path is not None else None
        for index, chunk in enumerate(chunks, start=1):
            headings = self._common_heading_path(entry.headings for entry in chunk.entries)
            body = self._render_body(chunk.entries, common_headings=headings)
            finalized.append(
                Chunk(
                    chunk_id=f"chunk-{index:04d}",
                    body=body,
                    token_count=self.tokenizer.count(body),
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
                        (entry.end_line for entry in chunk.entries if entry.end_line is not None),
                        default=None,
                    ),
                )
            )
        return finalized

    def _make_entry(
        self,
        headings: HeadingPath,
        blocks: list[MarkdownBlock],
        *,
        body_token_count: int | None = None,
    ) -> _Entry:
        body = join_markdown([block.text for block in blocks])
        start_lines = [b.start_line for b in blocks if b.start_line is not None]
        end_lines = [b.end_line for b in blocks if b.end_line is not None]
        return _Entry(
            headings=headings,
            body=body,
            start_line=min(start_lines) if start_lines else None,
            end_line=max(end_lines) if end_lines else None,
            body_token_count=(
                self._joined_token_count(self._block_token_count(block) for block in blocks)
                if body_token_count is None
                else body_token_count
            ),
        )

    def _entries_from_section(self, section: _MeasuredSection) -> list[_Entry]:
        """Render-ready entries for a section selected as a chunk."""
        node = section.node
        entries: list[_Entry] = []
        if node.blocks or (not section.children and node.level > 0):
            entries.append(
                self._make_entry(
                    node.path,
                    node.blocks,
                    body_token_count=section.counts.body,
                )
            )

        for child in section.children:
            entries.extend(self._entries_from_section(child))

        return entries

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

        common_headings = self._common_heading_path(entry.headings for entry in entries)
        if not self.options.retain_headings:
            return self._joined_token_count(entry.body_token_count for entry in entries)

        parts: list[int] = []
        if self.options.include_common_headings and common_headings:
            parts.append(self._heading_path_token_count(common_headings))

        previous_headings = common_headings
        for entry in entries:
            shared_headings = self._common_heading_path((previous_headings, entry.headings))
            if len(shared_headings) < len(common_headings):
                shared_headings = common_headings
            relative_headings = entry.headings[len(shared_headings) :]
            entry_token_count = self._joined_token_count(
                [
                    self._heading_path_token_count(relative_headings),
                    entry.body_token_count,
                ]
            )
            if entry_token_count:
                parts.append(entry_token_count)
            previous_headings = entry.headings

        return self._joined_token_count(parts)

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
            shared_headings = self._common_heading_path((previous_headings, entry.headings))
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

    def _common_heading_path(self, paths: Iterable[HeadingPath]) -> HeadingPath:
        """Return the longest shared heading prefix across all given paths."""
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

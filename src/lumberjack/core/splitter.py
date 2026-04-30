from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..base.interfaces import SplitterProtocol, TokenizerProtocol
from ..models import Chunk, DocumentAST, HeadingPath, MarkdownBlock, SectionNode, SplitOptions
from ..utils import join_markdown, render_heading_path
from .tokenizers import SimpleCharTokenizer

if TYPE_CHECKING:
    from collections.abc import Iterable

SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?\u3002\uFF01\uFF1F])\s+")
PROTECTED_SPAN_RE = re.compile(r"<https?://[^\s>]+>|https?://[^\s)>\]]+")


@dataclass(slots=True)
class _Fragment:
    headings: HeadingPath
    prefix: str
    blocks: list[MarkdownBlock]
    section_level: int

    def render(self) -> str:
        parts = [self.prefix] if self.prefix else []
        parts.extend(block.text for block in self.blocks)
        return join_markdown(parts)


@dataclass(slots=True)
class _Entry:
    headings: HeadingPath
    body: str
    section_level: int
    start_line: int | None
    end_line: int | None


@dataclass(slots=True)
class _ChunkDraft:
    entries: list[_Entry]
    token_count: int


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

    def split(self, document: DocumentAST) -> list[Chunk]:
        """Split *document* into chunks respecting token limits and merge preferences."""
        self._validate_options()
        chunks = self._split_section(document.root)
        if self.options.merge_small_chunks:
            chunks = self._merge_small_chunks(chunks)
        return self._finalize_chunks(chunks, document)

    def _validate_options(self) -> None:
        """Raise ``ValueError`` if split options contain illegal values."""
        if self.options.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")
        if self.options.min_tokens < 0:
            raise ValueError("min_tokens must be non-negative")
        if self.options.overlap_tokens < 0:
            raise ValueError("overlap_tokens must be non-negative")
        if self.options.min_tokens >= self.options.max_tokens:
            raise ValueError("min_tokens must be smaller than max_tokens")
        if self.options.overlap_tokens >= self.options.max_tokens:
            raise ValueError("overlap_tokens must be smaller than max_tokens")

    def _split_section(
        self,
        section: SectionNode,
        entries: list[_Entry] | None = None,
        draft: _ChunkDraft | None = None,
    ) -> list[_ChunkDraft]:
        """Recursively split a section into chunk drafts."""
        if entries is None:
            entries = self._collect_section_entries(section)
        if not entries:
            return []

        if draft is None:
            draft = self._draft_from_entries(entries)
        if draft.token_count <= self.options.max_tokens:
            return [draft]

        if section.children:
            return self._split_section_children(section)

        return self._split_section_body(section)

    def _split_section_children(
        self,
        section: SectionNode,
    ) -> list[_ChunkDraft]:
        """Split a section's body blocks and child sections, packing adjacent entries that fit."""
        chunks: list[_ChunkDraft] = []
        current_entries: list[_Entry] = []

        def flush_current() -> None:
            nonlocal current_entries
            if not current_entries:
                return
            chunks.append(self._draft_from_entries(current_entries))
            current_entries = []

        def add_packable(draft: _ChunkDraft) -> None:
            nonlocal current_entries
            candidate_entries = [*current_entries, *draft.entries]
            candidate = self._draft_from_entries(candidate_entries)
            if current_entries and candidate.token_count > self.options.max_tokens:
                flush_current()
                current_entries = draft.entries.copy()
                return
            current_entries = candidate_entries

        if section.blocks:
            body_draft = self._draft_from_entries([self._entry_from_section(section)])
            if body_draft.token_count <= self.options.max_tokens:
                add_packable(body_draft)
            else:
                flush_current()
                chunks.extend(self._split_section_body(section))

        for child in section.children:
            child_entries = self._collect_section_entries(child)
            if not child_entries:
                continue

            child_draft = self._draft_from_entries(child_entries)
            if child_draft.token_count <= self.options.max_tokens:
                add_packable(child_draft)
                continue

            flush_current()
            chunks.extend(self._split_section(child, entries=child_entries, draft=child_draft))

        flush_current()
        return chunks

    def _split_section_body(
        self,
        section: SectionNode,
    ) -> list[_ChunkDraft]:
        """Split a section's own blocks into fragments, then into chunk drafts."""
        prefix = (
            render_heading_path(section.path)
            if self.options.retain_headings and section.level > 0
            else ""
        )
        fragment = _Fragment(
            headings=section.path,
            prefix=prefix,
            blocks=section.blocks.copy(),
            section_level=section.level,
        )
        return self._split_fragment(fragment)

    def _split_fragment(
        self,
        fragment: _Fragment,
    ) -> list[_ChunkDraft]:
        """Greedy block-level split of a fragment into chunk drafts within token budget."""
        max_tokens = self.options.max_tokens
        prefix_tokens = self.tokenizer.count(fragment.prefix) if fragment.prefix else 0
        if prefix_tokens >= max_tokens:
            return [self._draft_from_entry(self._entry_from_fragment(fragment), fragment.render())]

        chunks: list[_ChunkDraft] = []
        current_parts: list[str] = []
        current_tokens = prefix_tokens
        current_start_line: int | None = None
        current_end_line: int | None = None

        if not fragment.blocks:
            return [self._draft_from_entry(self._entry_from_fragment(fragment), fragment.render())]

        budget = max_tokens - prefix_tokens

        for block in fragment.blocks:
            block_tokens = self.tokenizer.count(block.text)
            if (
                current_parts
                and current_tokens > prefix_tokens
                and current_tokens + block_tokens > max_tokens
            ):
                chunks.append(
                    _ChunkDraft(
                        entries=[
                            _Entry(
                                headings=fragment.headings,
                                body=join_markdown(current_parts),
                                section_level=fragment.section_level,
                                start_line=current_start_line,
                                end_line=current_end_line,
                            )
                        ],
                        token_count=current_tokens,
                    )
                )
                current_parts = []
                current_tokens = prefix_tokens
                current_start_line = None
                current_end_line = None

            if prefix_tokens + block_tokens <= max_tokens:
                # The flush makes `prefix_tokens + block_tokens <= max_tokens`
                # equivalent to `current_tokens + block_tokens <= max_tokens`.
                current_parts.append(block.text)
                current_tokens += block_tokens
                current_start_line = self._coalesce_min(current_start_line, block.start_line)
                current_end_line = self._coalesce_max(current_end_line, block.end_line)
                continue

            block_pieces = self._split_oversized_block(block, max_tokens=budget)
            if block_pieces is None:
                chunks.append(
                    _ChunkDraft(
                        entries=[
                            _Entry(
                                headings=fragment.headings,
                                body=block.text,
                                section_level=fragment.section_level,
                                start_line=block.start_line,
                                end_line=block.end_line,
                            )
                        ],
                        token_count=prefix_tokens + block_tokens,
                    )
                )
                current_parts = []
                current_tokens = prefix_tokens
                current_start_line = None
                current_end_line = None
                continue

            for piece in block_pieces:
                piece_tokens = self.tokenizer.count(piece)
                chunks.append(
                    _ChunkDraft(
                        entries=[
                            _Entry(
                                headings=fragment.headings,
                                body=piece,
                                section_level=fragment.section_level,
                                start_line=block.start_line,
                                end_line=block.end_line,
                            )
                        ],
                        token_count=prefix_tokens + piece_tokens,
                    )
                )

        if current_parts:
            rendered = join_markdown(current_parts)
            if rendered:
                chunks.append(
                    _ChunkDraft(
                        entries=[
                            _Entry(
                                headings=fragment.headings,
                                body=rendered,
                                section_level=fragment.section_level,
                                start_line=current_start_line,
                                end_line=current_end_line,
                            )
                        ],
                        token_count=current_tokens,
                    )
                )

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

        if self._contains_oversized_protected_span(text, max_tokens=max_tokens):
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
        for part in parts:
            candidate_parts = [*current_parts, part]
            candidate = separator.join(candidate_parts)
            if current_parts and self.tokenizer.count(candidate) > max_tokens:
                packed.append(separator.join(current_parts))
                overlap_parts = self._tail_parts_within_budget(
                    current_parts,
                    separator=separator,
                    max_tokens=overlap_tokens,
                )
                current_parts = [*overlap_parts, part]
                if self.tokenizer.count(separator.join(current_parts)) > max_tokens:
                    current_parts = [part]
            else:
                current_parts = candidate_parts
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
        separator: str,
        max_tokens: int,
    ) -> list[str]:
        if max_tokens <= 0 or not parts:
            return []

        tail: list[str] = []
        for part in reversed(parts):
            candidate = [part, *tail]
            if self.tokenizer.count(separator.join(candidate)) > max_tokens:
                break
            tail = candidate
        return tail

    def _suffix_within_budget(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0 or not text:
            return ""
        if self.tokenizer.count(text) <= max_tokens:
            return text

        for start in range(1, len(text)):
            suffix = text[start:]
            if self._ends_inside_protected_span(text, start):
                continue
            if self.tokenizer.count(suffix) <= max_tokens:
                return suffix
        return ""

    def _contains_oversized_protected_span(self, text: str, *, max_tokens: int) -> bool:
        return any(
            self.tokenizer.count(match.group(0)) > max_tokens
            for match in PROTECTED_SPAN_RE.finditer(text)
        )

    def _ends_inside_protected_span(self, text: str, start: int) -> bool:
        return any(
            match.start() < start < match.end() for match in PROTECTED_SPAN_RE.finditer(text)
        )

    def _merge_small_chunks(
        self,
        chunks: list[_ChunkDraft],
    ) -> list[_ChunkDraft]:
        """Merge adjacent chunks that share a heading path and fall below *min_tokens*."""
        if not chunks:
            return chunks

        merged: list[_ChunkDraft] = [chunks[0]]
        for chunk in chunks[1:]:
            previous = merged[-1]
            if (
                self._can_merge_small_chunks(previous, chunk)
                and previous.token_count + chunk.token_count <= self.options.max_tokens
                and chunk.token_count < self.options.min_tokens
            ):
                merged[-1] = _ChunkDraft(
                    entries=[*previous.entries, *chunk.entries],
                    token_count=previous.token_count + chunk.token_count,
                )
            else:
                merged.append(chunk)
        return merged

    def _finalize_chunks(
        self,
        chunks: list[_ChunkDraft],
        document: DocumentAST,
    ) -> list[Chunk]:
        """Convert chunk drafts into final ``Chunk`` objects with rendered text and metadata."""
        finalized: list[Chunk] = []
        document_path = self._document_path(document)
        for index, chunk in enumerate(chunks, start=1):
            headings = self._common_heading_path(entry.headings for entry in chunk.entries)
            text = self._render_chunk_entries(
                chunk.entries,
                common_headings=headings,
            )
            body = self._render_chunk_entries(
                chunk.entries,
                common_headings=headings,
                include_common_headings=False,
            )
            finalized.append(
                Chunk(
                    chunk_id=f"chunk-{index:04d}",
                    text=text,
                    body=body,
                    token_count=self.tokenizer.count(text),
                    headings=headings,
                    section_level=headings[-1][0] if headings else 0,
                    document_title=document.title,
                    document_path=document_path,
                    start_line=self._coalesce_min(
                        None,
                        min(
                            (
                                entry.start_line
                                for entry in chunk.entries
                                if entry.start_line is not None
                            ),
                            default=None,
                        ),
                    ),
                    end_line=self._coalesce_max(
                        None,
                        max(
                            (
                                entry.end_line
                                for entry in chunk.entries
                                if entry.end_line is not None
                            ),
                            default=None,
                        ),
                    ),
                )
            )
        return finalized

    def _entry_from_fragment(self, fragment: _Fragment) -> _Entry:
        return _Entry(
            headings=fragment.headings,
            body=join_markdown([block.text for block in fragment.blocks]),
            section_level=fragment.section_level,
            start_line=self._first_line(blocks=fragment.blocks),
            end_line=self._last_line(blocks=fragment.blocks),
        )

    def _collect_section_entries(self, section: SectionNode) -> list[_Entry]:
        """Recursively collect entries from a section and all its descendants."""
        entries: list[_Entry] = []
        if section.blocks or (not section.children and section.level > 0):
            entries.append(self._entry_from_section(section))

        for child in section.children:
            entries.extend(self._collect_section_entries(child))

        return entries

    def _entry_from_section(self, section: SectionNode) -> _Entry:
        return _Entry(
            headings=section.path,
            body=join_markdown([block.text for block in section.blocks]),
            section_level=section.level,
            start_line=self._first_line(blocks=section.blocks),
            end_line=self._last_line(blocks=section.blocks),
        )

    def _draft_from_entry(self, entry: _Entry, rendered: str) -> _ChunkDraft:
        return _ChunkDraft(entries=[entry], token_count=self.tokenizer.count(rendered))

    def _draft_from_entries(
        self,
        entries: list[_Entry],
    ) -> _ChunkDraft:
        """Build a chunk draft by rendering entries and counting their tokens."""
        headings = self._common_heading_path(entry.headings for entry in entries)
        rendered = self._render_chunk_entries(
            entries,
            common_headings=headings,
        )
        return _ChunkDraft(entries=entries.copy(), token_count=self.tokenizer.count(rendered))

    def _render_chunk_entries(
        self,
        entries: list[_Entry],
        *,
        common_headings: HeadingPath,
        include_common_headings: bool = True,
    ) -> str:
        """Render entries into Markdown, deduplicating shared heading prefixes."""
        if not entries:
            return ""

        full_common_headings = self._visible_heading_path(common_headings)
        visible_common_headings = full_common_headings if include_common_headings else ()
        parts: list[str] = []
        if visible_common_headings:
            parts.append(render_heading_path(visible_common_headings))

        previous_visible_headings = full_common_headings
        for entry in entries:
            entry_visible_headings = self._visible_heading_path(entry.headings)
            shared_headings = self._common_heading_path(
                (previous_visible_headings, entry_visible_headings)
            )
            if len(shared_headings) < len(visible_common_headings):
                shared_headings = visible_common_headings
            relative_headings = entry_visible_headings[len(shared_headings) :]

            entry_parts: list[str] = []
            if relative_headings:
                entry_parts.append(render_heading_path(relative_headings))
            if entry.body:
                entry_parts.append(entry.body)
            rendered = join_markdown(entry_parts)
            if rendered:
                parts.append(rendered)
            previous_visible_headings = entry_visible_headings

        return join_markdown(parts)

    def _visible_heading_path(
        self,
        headings: HeadingPath,
    ) -> HeadingPath:
        if self.options.retain_headings:
            return headings
        return headings[1:] if len(headings) > 1 else ()

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

    def _document_path(self, document: DocumentAST) -> str | None:
        path = document.metadata.get("path")
        return str(path) if path is not None else None

    def _can_merge_small_chunks(self, left: _ChunkDraft, right: _ChunkDraft) -> bool:
        if not left.entries or not right.entries:
            return False

        left_headings = {entry.headings for entry in left.entries}
        right_headings = {entry.headings for entry in right.entries}
        return len(left_headings) == 1 and left_headings == right_headings

    def _first_line(
        self,
        *,
        blocks: list[MarkdownBlock] | None = None,
        fragments: list[_Fragment] | None = None,
    ) -> int | None:
        line_numbers: list[int] = []
        if blocks is not None:
            line_numbers.extend(
                block.start_line for block in blocks if block.start_line is not None
            )
        if fragments is not None:
            for fragment in fragments:
                line_numbers.extend(
                    block.start_line for block in fragment.blocks if block.start_line is not None
                )
        return min(line_numbers) if line_numbers else None

    def _last_line(
        self,
        *,
        blocks: list[MarkdownBlock] | None = None,
        fragments: list[_Fragment] | None = None,
    ) -> int | None:
        line_numbers: list[int] = []
        if blocks is not None:
            line_numbers.extend(block.end_line for block in blocks if block.end_line is not None)
        if fragments is not None:
            for fragment in fragments:
                line_numbers.extend(
                    block.end_line for block in fragment.blocks if block.end_line is not None
                )
        return max(line_numbers) if line_numbers else None

    def _coalesce_min(self, left: int | None, right: int | None) -> int | None:
        values = [value for value in (left, right) if value is not None]
        return min(values) if values else None

    def _coalesce_max(self, left: int | None, right: int | None) -> int | None:
        values = [value for value in (left, right) if value is not None]
        return max(values) if values else None

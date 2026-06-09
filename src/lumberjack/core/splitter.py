from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .models import (
    Chunk,
    DocumentAST,
    HeadingPath,
    MarkdownBlock,
    SectionNode,
    SplitOptions,
)
from .protocols import SplitterProtocol, TokenizerProtocol
from .tokenizers import SimpleCharTokenizer
from .utils import join_markdown

if TYPE_CHECKING:
    from collections.abc import Iterable

SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?\u3002\uFF01\uFF1F])\s+")
PROTECTED_SPAN_RE = re.compile(r"<https?://[^\s>]+>|https?://[^\s)>\]]+")
TABLE_DELIMITER_CELL_RE = re.compile(r":?-+(:?-+)*:?")
SEPARATOR = "\n\n"
SEPARATOR_DELTA_WINDOW_CHARS = 8
SplitOrigin = Literal["section", "fragment", "text_piece"]


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
class _Entry:
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
class _ChunkDraft:
    """Intermediate chunk holding grouped entries, token estimate, and split source.

    Args:
        entries: List of entries to be merged into the chunk, with heading context and body.
        headings: The full heading path context for the chunk, used for rendering and metadata.

            ``# H1 \\n\\n ## H2.1 \\n\\n Content1``, headings=[(1, "H1"), (2, "H2.1")].

            ``# H1 \\n\\n ## H2.1 \\n\\n Content1 ## H2.2 \\n\\n Content2``, headings=[(1, "H1")].

        headings_token_count: The token count for the chunk's full heading path.
        body_token_count: The token count for the chunk body (sum of entry body_token_count plus separator deltas).
        token_count: `headings_token_count` + `body_token_count`.
        split_origin: The source of the split that produced this draft, for debugging/analysis.
        chunk_type: The type of content in the chunk (e.g. "paragraph", "code_block"), used for metadata.

    """

    entries: list[_Entry]
    headings: HeadingPath
    headings_token_count: int
    body_token_count: int
    token_count: int
    split_origin: SplitOrigin = "section"
    chunk_type: str = "paragraph"


@dataclass(slots=True, frozen=True)
class _SectionTokenCounts:
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
class _MeasuredSection:
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
    counts: _SectionTokenCounts
    tail_text: str
    can_emit_as_single_chunk: bool
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

        if block.kind == "table":
            return self.split_table_block(block, max_tokens=max_tokens)

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

    def split_table_block(
        self,
        block: MarkdownBlock,
        *,
        max_tokens: int,
    ) -> list[str]:
        lines = [line.rstrip() for line in block.text.splitlines() if line.strip()]
        if len(lines) < 3 or not self.is_table_delimiter_row(lines[1]):
            return self.split_text(block.text, max_tokens=max_tokens)

        header = lines[:2]
        rows = lines[2:]
        pieces: list[str] = []
        current_rows: list[str] = []

        for row in rows:
            candidate_rows = [*current_rows, row]
            candidate = self.render_table_piece(header, candidate_rows)
            if current_rows and self.tokenizer.count(candidate) > max_tokens:
                pieces.append(self.render_table_piece(header, current_rows))
                current_rows = [row]
                single_row = self.render_table_piece(header, current_rows)
                if self.tokenizer.count(single_row) > max_tokens:
                    pieces.append(single_row)
                    current_rows = []
                continue

            if not current_rows and self.tokenizer.count(candidate) > max_tokens:
                pieces.append(candidate)
                continue

            current_rows = candidate_rows

        if current_rows:
            pieces.append(self.render_table_piece(header, current_rows))

        return pieces or [block.text]

    def is_table_delimiter_row(self, line: str) -> bool:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        return bool(cells) and all(
            cell and TABLE_DELIMITER_CELL_RE.fullmatch(cell) for cell in cells
        )

    def render_table_piece(self, header: list[str], rows: list[str]) -> str:
        return "\n".join([*header, *rows])

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
            candidate_text = (
                current_joined + separator + part if current_joined else part
            )
            candidate_tokens = self.tokenizer.count(candidate_text)
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
        measured_root = self._measure_section(document.root)
        drafts = self._split_section(measured_root)
        drafts = self._post_process_drafts(drafts)
        return self._finalize_chunks(drafts, document)

    def _heading_path_token_count(self, path: HeadingPath) -> int:
        if not path:
            return 0
        tokens = 0
        for level, title in path:
            if title:
                tokens = tokens + self.tokenizer.count(
                    "#" * level + " " + title + SEPARATOR, cache=True
                )
        return tokens

    def _split_section(self, root: _MeasuredSection) -> list[_ChunkDraft]:
        raise NotImplementedError

    def _post_process_drafts(self, drafts: list[_ChunkDraft]) -> list[_ChunkDraft]:
        return drafts

    def _block_budget(self, block_kind: str, default_budget: int) -> int:
        """Return the per-block max_tokens override, or *default_budget*."""
        override = self.options.block_max_tokens.get(block_kind.lower())
        return override if override and override > 0 else default_budget

    def _separator_delta_after(self, text: str) -> int:
        """Estimate the token delta caused by appending the Markdown separator."""
        if not text:
            return 0
        tail = text.rstrip("\n")[-SEPARATOR_DELTA_WINDOW_CHARS:]
        return self.tokenizer.count(
            f"{tail}{SEPARATOR}", cache=True
        ) - self.tokenizer.count(tail, cache=True)

    def _validate_options(self) -> None:
        if self.options.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")
        if not 0 < self.options.ideal_max_tokens_ratio <= 1:
            raise ValueError(
                "ideal_max_tokens_ratio must be greater than 0 and at most 1"
            )
        if self.options.merge_below_tokens < 0:
            raise ValueError("merge_below_tokens must be non-negative")
        if self.options.overlap_tokens < 0:
            raise ValueError("overlap_tokens must be non-negative")
        if self.options.merge_below_tokens >= self.options.max_tokens:
            raise ValueError("merge_below_tokens must be smaller than max_tokens")
        if self.options.overlap_tokens >= self.options.ideal_max_tokens:
            raise ValueError(
                f"overlap_tokens ({self.options.overlap_tokens}) must be smaller than "
                f"ideal_max_tokens ({self.options.ideal_max_tokens})"
            )
        for kind, tokens in self.options.block_max_tokens.items():
            if tokens <= 0:
                raise ValueError(
                    f"block_max_tokens[{kind!r}] must be positive, got {tokens}"
                )

    def _measure_section(self, section: SectionNode) -> _MeasuredSection:
        """Return a measured wrapper for *section* and all descendants."""
        children = tuple(self._measure_section(child) for child in section.children)

        # 1. Count body tokens
        body_token_count = 0
        for idx, block in enumerate(section.blocks):
            if idx == len(section.blocks) - 1:
                body_token_count += self.tokenizer.count(block.text, cache=True)
            else:
                body_token_count += self.tokenizer.count(
                    block.text + SEPARATOR, cache=True
                )

        # 2. Count title tokens
        if section.level > 0:
            title_token_count = self.tokenizer.count(
                "#" * section.level + " " + section.title + SEPARATOR, cache=True
            )
        else:
            title_token_count = 0

        # 3. Count subtree tokens
        subtree_token_count = title_token_count + body_token_count
        previous_tail = section.blocks[-1].text if section.blocks else ""
        prev_child: _MeasuredSection | None = None
        for child in children:
            # When the previous child is a leaf section with no body
            # blocks, its heading's trailing \n\n (from
            # heading_path_token_count) already serves as the separator
            # to this child.  Adding sep_delta would double-count it.
            if previous_tail and not (
                prev_child is not None
                and not prev_child.node.blocks
                and not prev_child.children
            ):
                subtree_token_count += self._separator_delta_after(previous_tail)
            subtree_token_count += child.counts.subtree
            previous_tail = child.tail_text
            prev_child = child

        if previous_tail:
            tail_text = previous_tail
        elif section.level > 0:
            tail_text = "#" * section.level + " " + section.title
        else:
            tail_text = ""

        body_has_standalone = any(
            block.kind in self.options.standalone_kinds for block in section.blocks
        )
        can_emit_as_single_chunk = not body_has_standalone and all(
            child.can_emit_as_single_chunk for child in children
        )
        return _MeasuredSection(
            node=section,
            counts=_SectionTokenCounts(
                title=title_token_count,
                body=body_token_count,
                subtree=subtree_token_count,
            ),
            tail_text=tail_text,
            can_emit_as_single_chunk=can_emit_as_single_chunk,
            children=children,
        )

    def _split_section_body(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Split a section's own blocks into fragments, then into chunk drafts."""
        node = section.node
        headings = node.path
        blocks = node.blocks
        max_tokens = self.options.ideal_max_tokens
        splittable_kinds = self.options.splittable_kinds
        standalone = self.options.standalone_kinds

        prefix_tokens = (
            self._heading_path_token_count(headings) if node.level > 0 else 0
        )
        if prefix_tokens >= max_tokens or not blocks:
            entry = self._entry_from_blocks(
                headings, blocks, body_token_count=section.counts.body
            )
            return [
                _ChunkDraft(
                    entries=[entry],
                    headings=node.path,
                    headings_token_count=prefix_tokens,
                    body_token_count=entry.body_token_count,
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
            entry = _Entry(
                headings=headings,
                body=join_markdown(current_parts),
                start_line=current_start_line,
                end_line=current_end_line,
                body_token_count=current_body_tokens,
            )
            token_count = prefix_tokens + current_body_tokens
            return _ChunkDraft(
                entries=[entry],
                headings=headings,
                headings_token_count=prefix_tokens,
                body_token_count=token_count - prefix_tokens,
                token_count=token_count,
                split_origin="fragment",
            )

        for block in blocks:
            if standalone and block.kind in standalone:
                if current_parts:
                    chunks.append(draft_current())
                    current_parts = []
                    current_joined = ""
                    current_body_tokens = 0
                    current_start_line = None
                    current_end_line = None

                block_tokens = self.tokenizer.count(block.text, cache=True)
                block_pieces = self._text_splitter.split_oversized_block(
                    block,
                    max_tokens=self._block_budget(block.kind, budget),
                    allowed_kinds=splittable_kinds,
                )
                if block_pieces is not None:
                    for piece in block_pieces:
                        piece_tokens = self.tokenizer.count(piece)
                        entry = _Entry(
                            headings=headings,
                            body=piece,
                            start_line=block.start_line,
                            end_line=block.end_line,
                            body_token_count=piece_tokens,
                        )
                        chunks.append(
                            _ChunkDraft(
                                entries=[entry],
                                headings=headings,
                                headings_token_count=prefix_tokens,
                                body_token_count=piece_tokens,
                                token_count=prefix_tokens + piece_tokens,
                                split_origin="text_piece",
                                chunk_type=block.kind,
                            )
                        )
                else:
                    entry = _Entry(
                        headings=headings,
                        body=block.text,
                        start_line=block.start_line,
                        end_line=block.end_line,
                        body_token_count=block_tokens,
                    )

                    chunks.append(
                        _ChunkDraft(
                            entries=[entry],
                            headings=headings,
                            headings_token_count=prefix_tokens,
                            body_token_count=block_tokens,
                            token_count=prefix_tokens + block_tokens,
                            split_origin="fragment",
                            chunk_type=block.kind,
                        )
                    )

                continue

            block_tokens = self.tokenizer.count(block.text, cache=True)
            candidate_body_tokens = (
                current_body_tokens
                - self.tokenizer.count(current_parts[-1], cache=True)
                + self.tokenizer.count(f"{current_parts[-1]}{SEPARATOR}", cache=True)
                + block_tokens
                if current_parts
                else block_tokens
            )
            candidate_total = prefix_tokens + candidate_body_tokens
            if current_parts and candidate_total > max_tokens:
                chunks.append(draft_current())
                current_parts = []
                current_joined = ""
                current_body_tokens = 0
                current_start_line = None
                current_end_line = None
                candidate_body_tokens = block_tokens

            single_block_total = prefix_tokens + block_tokens
            if single_block_total <= max_tokens:
                current_parts.append(block.text)
                candidate_text = (
                    current_joined + SEPARATOR + block.text
                    if current_joined
                    else block.text
                )
                current_body_tokens = candidate_body_tokens
                current_joined = candidate_text
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
                max_tokens=self._block_budget(block.kind, budget),
                allowed_kinds=splittable_kinds,
            )
            if block_pieces is None:
                entry = _Entry(
                    headings=headings,
                    body=block.text,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    body_token_count=block_tokens,
                )
                chunks.append(
                    _ChunkDraft(
                        entries=[entry],
                        headings=headings,
                        headings_token_count=prefix_tokens,
                        body_token_count=block_tokens,
                        token_count=prefix_tokens + block_tokens,
                        split_origin="fragment",
                        chunk_type="paragraph",
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
                entry = _Entry(
                    headings=headings,
                    body=piece,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    body_token_count=piece_tokens,
                )
                chunks.append(
                    _ChunkDraft(
                        entries=[entry],
                        headings=headings,
                        headings_token_count=prefix_tokens,
                        body_token_count=piece_tokens,
                        token_count=prefix_tokens + piece_tokens,
                        split_origin="text_piece",
                        chunk_type="paragraph",
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
            # Adjust the estimate for the trailing phantom \n\n in the last
            # entry.  When the last entry has empty body, its heading's
            # trailing \n\n (from heading_path_token_count) was counted in
            # the incremental estimate but is never rendered — there is no
            # next entry for it to separate from.
            estimated = chunk.token_count
            if chunk.entries:
                last = chunk.entries[-1]
                if not last.body.strip():
                    relative = last.headings[len(headings) :]
                    if relative:
                        ht = render_heading_path(relative)
                        estimated -= self.tokenizer.count(
                            ht + SEPARATOR, cache=True
                        ) - self.tokenizer.count(ht, cache=True)
            finalized.append(
                Chunk(
                    chunk_id=f"chunk-{index:04d}",
                    chunk_type=chunk.chunk_type,
                    body=body,
                    token_count=token_count,
                    estimated_token_count=estimated,
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

        return _Entry(
            headings=headings,
            body=body,
            start_line=min(start_lines) if start_lines else None,
            end_line=max(end_lines) if end_lines else None,
            body_token_count=body_token_count,
        )

    def _entry_group_tail(self, entries: list[_Entry]) -> str:
        if not entries:
            return ""
        last = entries[-1]
        if last.body:
            return last.body
        if last.headings:
            level, title = last.headings[-1]
            return "#" * level + " " + title
        return ""

    def _merge_drafts(
        self,
        left_draft: _ChunkDraft,
        right_draft: _ChunkDraft,
    ) -> _ChunkDraft:
        left_headings = left_draft.headings
        right_headings = right_draft.headings

        common_headings = common_heading_path([left_headings, right_headings])
        headings_token_count = self._heading_path_token_count(common_headings)

        left_body_token_count = left_draft.token_count - headings_token_count
        right_body_token_count = right_draft.token_count - headings_token_count

        body_token_count = left_body_token_count + right_body_token_count

        # Account for the \n\n separator between the last left entry and
        # the first right entry introduced by join_markdown during rendering.
        #
        # When the last left entry has empty body, its heading's trailing
        # \n\n (from heading_path_token_count in _measure_section) already
        # serves as the separator to the next entry.  Adding sep_delta here
        # would double-count that separator.
        if left_draft.entries and right_draft.entries:
            last_left = left_draft.entries[-1]
            if last_left.body:
                left_tail = self._entry_group_tail(left_draft.entries)
                body_token_count += self._separator_delta_after(left_tail)

        return _ChunkDraft(
            entries=[*left_draft.entries, *right_draft.entries],
            headings=common_headings,
            headings_token_count=headings_token_count,
            body_token_count=body_token_count,
            token_count=headings_token_count + body_token_count,
            split_origin=f"merge({left_draft.split_origin}+{right_draft.split_origin})",
            chunk_type=left_draft.chunk_type,
        )

    def _render_body(
        self,
        entries: list[_Entry],
        *,
        common_headings: HeadingPath,
    ) -> str:
        """Render entries into Markdown body content."""
        if not entries:
            return ""

        parts: list[str] = []
        if common_headings:
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

    def _split_section(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Recursively split a section into chunk drafts."""
        if not (section.node.blocks or section.children or section.node.level > 0):
            return []
        entries = self._entries_from_section(section)
        common_headings = common_heading_path(entry.headings for entry in entries)
        headings_token_count = self._heading_path_token_count(common_headings)

        chunk_token_count = (
            self._heading_path_token_count(section.node.path[:-1])
            + section.counts.subtree
        )

        if (
            chunk_token_count <= self.options.ideal_max_tokens
            and section.can_emit_as_single_chunk
        ):
            return [
                _ChunkDraft(
                    entries=entries,
                    headings=section.node.path,
                    headings_token_count=headings_token_count,
                    body_token_count=chunk_token_count - headings_token_count,
                    token_count=chunk_token_count,
                )
            ]

        if section.children:
            return self._split_section_children(section)  # include section.body

        chunks = self._split_section_body(section)
        return self._merge_small_chunks(chunks, parent_headings=section.node.path)

    def _split_section_children(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Split a section's body blocks and child sections, packing adjacent entries that fit."""
        node = section.node
        chunks: list[_ChunkDraft] = []
        current_draft: _ChunkDraft | None = None
        standalone_kinds = self.options.standalone_kinds

        common_heading_token_count = self._heading_path_token_count(node.path)
        budget_token_count = self.options.ideal_max_tokens - common_heading_token_count

        def flush_current() -> None:
            nonlocal current_draft

            if not current_draft:
                return

            chunks.append(current_draft)
            current_draft = _ChunkDraft(
                entries=[],
                headings=node.path,
                headings_token_count=common_heading_token_count,
                body_token_count=0,
                token_count=common_heading_token_count,
            )

        def add_packable(new_draft: _ChunkDraft) -> None:
            """Add a draft whose tokens are already guaranteed not to exceed max_tokens.

            Args:
                new_draft: The draft to add, which may be merged with the current draft if it fits within the budget.
            """
            nonlocal current_draft

            if not current_draft:
                current_draft = new_draft
                return

            temp_merged_draft = self._merge_drafts(current_draft, new_draft)

            if temp_merged_draft.token_count > self.options.ideal_max_tokens:
                flush_current()
                current_draft = new_draft
                return

            current_draft = temp_merged_draft

        if node.blocks:
            body_token_count = section.counts.body
            body_has_standalone = any(b.kind in standalone_kinds for b in node.blocks)
            if body_has_standalone:
                flush_current()
                chunks.extend(self._split_section_body(section))
            elif body_token_count <= budget_token_count:
                entry = self._entry_from_blocks(
                    node.path,
                    node.blocks,
                    body_token_count=body_token_count,
                )
                draft = _ChunkDraft(
                    entries=[entry],
                    headings=node.path,
                    headings_token_count=common_heading_token_count,
                    body_token_count=body_token_count,
                    token_count=common_heading_token_count + body_token_count,
                )
                add_packable(draft)
            else:
                flush_current()
                chunks.extend(self._split_section_body(section))

        for child in section.children:
            if not (child.node.blocks or child.children or child.node.level > 0):
                continue

            if child.counts.subtree <= budget_token_count:
                if not child.can_emit_as_single_chunk:
                    flush_current()
                    chunks.extend(self._split_section(child))
                else:
                    entries = self._entries_from_section(child)
                    child_common_headings = common_heading_path(
                        entry.headings for entry in entries
                    )
                    child_common_headings_token_count = self._heading_path_token_count(
                        child_common_headings
                    )
                    child_chunk_token_count = (
                        common_heading_token_count + child.counts.subtree
                    )
                    child_body_token_count = (
                        child_chunk_token_count - child_common_headings_token_count
                    )

                    draft = _ChunkDraft(
                        entries=entries,
                        headings=child.node.path,
                        headings_token_count=child_common_headings_token_count,
                        body_token_count=child_body_token_count,
                        token_count=child_chunk_token_count,
                    )
                    add_packable(draft)
                continue

            flush_current()
            chunks.extend(self._split_section(child))

        flush_current()
        return self._merge_small_chunks(chunks, parent_headings=node.path)

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
        *,
        parent_headings: HeadingPath | None = None,
    ) -> list[_ChunkDraft]:
        """Merge adjacent same-parent chunks below *merge_below_tokens*, bottom-up."""
        if not self.options.merge_small_chunks:
            return chunks
        if not chunks:
            return chunks

        merged: list[_ChunkDraft] = list(chunks)
        i = len(merged) - 1
        while i > 0:
            current = merged[i]
            previous = merged[i - 1]
            can_merge = (
                (parent_headings is None or previous.headings == parent_headings)
                and previous.headings == current.headings
                and current.entries
            )
            if (
                can_merge
                and current.token_count < self.options.merge_below_tokens
                and previous.chunk_type == "paragraph"
                and current.chunk_type == "paragraph"
            ):
                merged_draft = self._merge_drafts(previous, current)
                if merged_draft.token_count <= self.options.max_tokens:
                    merged[i - 1] = merged_draft
                    del merged[i]
            i -= 1
        return merged


class SectionMarkdownSplitter(_BaseMarkdownSplitter):
    """Split a document into non-overlapping chunks by heading section.

    Each heading-defined section becomes its own chunk. When ``recursive_split``
    is enabled, oversized section bodies are further split by token budget.
    """

    def _split_section(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children."""
        chunks: list[_ChunkDraft] = []
        node = section.node

        if node.blocks or node.level > 0:
            body_has_standalone = any(
                b.kind in self.options.standalone_kinds for b in node.blocks
            )
            if (
                self.options.recursive_split
                and section.counts.subtree > self.options.ideal_max_tokens
            ) or body_has_standalone:
                chunks.extend(self._split_section_body(section))
            else:
                entry = self._entry_from_blocks(
                    node.path,
                    node.blocks,
                    body_token_count=section.counts.body,
                )
                headings_token_count = self._heading_path_token_count(node.path)
                chunks.append(
                    _ChunkDraft(
                        entries=[entry],
                        headings=node.path,
                        headings_token_count=headings_token_count,
                        body_token_count=section.counts.body,
                        token_count=headings_token_count + section.counts.body,
                    )
                )

        for child in section.children:
            chunks.extend(self._split_section(child))

        return chunks


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

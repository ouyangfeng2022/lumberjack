from __future__ import annotations

from ..block import BlockSplitter
from ..models import (
    Chunk,
    ChunkDraft,
    DocumentAST,
    Entry,
    HeadingPath,
    MarkdownBlock,
    MeasuredSection,
    SectionNode,
    SectionTokenCounts,
    SplitOptions,
    common_heading_path,
    render_heading_path,
)
from ..protocols import SplitterProtocol, TokenizerProtocol
from ..tokenizers import (
    CountMode,
    ExactTokenCount,
    IncrementalTokenCount,
    SimpleCharTokenizer,
)
from ..utils import join_markdown

SEPARATOR = "\n\n"


class BaseSplitter(SplitterProtocol):
    """Shared state and helpers for splitter strategies."""

    def __init__(
        self,
        tokenizer: TokenizerProtocol | None = None,
        options: SplitOptions | None = None,
        count_mode: CountMode = "exact",
    ):
        self.tokenizer = tokenizer or SimpleCharTokenizer()
        self.options = options or SplitOptions()
        self.count_mode = count_mode
        self.token_counter = self._build_token_counter(count_mode)
        self._validate_options()
        self._block_splitter = BlockSplitter(self.tokenizer, self.options)

    def _build_token_counter(self, count_mode: CountMode):
        if count_mode == "incremental":
            return IncrementalTokenCount(self.tokenizer)
        return ExactTokenCount(self.tokenizer)

    def split(self, document: DocumentAST) -> list[Chunk]:
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
                tokens = tokens + self.token_counter.count_text(
                    "#" * level + " " + title + SEPARATOR
                )
        return tokens

    def _heading_budget_token_count(self, path: HeadingPath) -> int:
        """Heading tokens counted toward the split budget.

        The base implementation always returns the full heading token count —
        headings consume budget whether or not they are rendered.  Subclasses
        that can prove every entry in a chunk shares the chunk's common heading
        path (no internal relative headings) may override this to return 0 when
        ``render_headings=False``, making the budget match the rendered body.
        """
        return self._heading_path_token_count(path)

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        """Render-aware token budget a draft occupies.

        Drafts carry full heading token counts internally so that merge
        arithmetic stays self-consistent (when a merge shrinks the common
        prefix, the displaced heading tokens fall back into the body as
        internal relative headings).  This helper translates that internal
        count into the *rendered* footprint so budget comparisons match what
        will actually appear in ``Chunk.body``:

        * ``render_headings=True``  — the common breadcrumb is rendered, so
          the full ``token_count`` counts toward the budget.
        * ``render_headings=False`` — the common breadcrumb is omitted, so
          only the body (which still includes internal relative headings)
          counts.  Using ``body_token_count`` here is correct for both
          splitters: SectionSplitter's drafts already exclude heading tokens
          via the budget hook, and RecursiveSplitter's merge arithmetic
          folds displaced heading tokens into ``body_token_count``.
        """
        if self.options.render_headings:
            return draft.token_count
        return draft.body_token_count

    def _split_section(self, section: MeasuredSection) -> list[ChunkDraft]:
        raise NotImplementedError

    def _post_process_drafts(self, drafts: list[ChunkDraft]) -> list[ChunkDraft]:
        return drafts

    def _separator_delta_after(self, text: str) -> int:
        """Estimate the token delta caused by appending the Markdown separator."""
        return self.token_counter.separator_delta(text, SEPARATOR)

    def _validate_options(self) -> None:
        if self.options.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")
        if not 0 < self.options.ideal_max_tokens_ratio <= 1:
            raise ValueError(
                "ideal_max_tokens_ratio must be greater than 0 and at most 1"
            )
        if (
            self.options.merge_below_tokens is None
            or self.options.merge_below_tokens < 0
        ):
            # None or negative means merging is disabled; nothing else to validate.
            pass
        elif self.options.merge_below_tokens >= self.options.max_tokens:
            raise ValueError("merge_below_tokens must be smaller than max_tokens")
        for kind, cfg in self.options.block_options.items():
            if cfg.max_tokens is not None and cfg.max_tokens <= 0:
                raise ValueError(
                    f"block_options[{kind!r}].max_tokens must be positive, got {cfg.max_tokens}"
                )

    def _measure_section(self, section: SectionNode) -> MeasuredSection:
        """Return a measured wrapper for *section* and all descendants."""
        children = tuple(self._measure_section(child) for child in section.children)

        # 1. Count body tokens
        body_token_count = 0
        for idx, block in enumerate(section.blocks):
            if not block.text:
                continue
            if idx == len(section.blocks) - 1:
                body_token_count += self.token_counter.count_text(block.text)
            else:
                body_token_count += self.token_counter.count_text(
                    block.text + SEPARATOR
                )

        # 2. Count title tokens
        if section.level > 0:
            title_token_count = self.token_counter.count_text(
                "#" * section.level + " " + section.title + SEPARATOR
            )
        else:
            title_token_count = 0

        # 3. Count subtree tokens
        subtree_token_count = title_token_count + body_token_count
        previous_tail = section.blocks[-1].text if section.blocks else ""
        prev_child: MeasuredSection | None = None
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
        return MeasuredSection(
            node=section,
            counts=SectionTokenCounts(
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
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Split a section's own blocks into fragments, then into chunk drafts."""
        node = section.node
        headings = node.path
        blocks = node.blocks
        max_tokens = self.options.ideal_max_tokens
        standalone_kinds = self.options.standalone_kinds

        # Full heading token count — kept on every draft so merge arithmetic
        # stays self-consistent (displaced heading tokens fall back into the
        # body when a merge shrinks the common prefix).
        prefix_tokens = (
            self._heading_path_token_count(headings) if node.level > 0 else 0
        )
        # Body-only budget for splitting decisions.  When render_headings=True
        # the common breadcrumb is rendered, so the heading tokens are
        # subtracted from max_tokens.  When render_headings=False the
        # breadcrumb is omitted and the full max_tokens is available for body.
        if self.options.render_headings:
            body_budget = max(0, max_tokens - prefix_tokens)
        else:
            body_budget = max_tokens

        if prefix_tokens >= max_tokens or not blocks:
            entry = self._entry_from_blocks(
                headings, blocks, body_token_count=section.counts.body
            )
            return [
                ChunkDraft(
                    entries=[entry],
                    headings=node.path,
                    headings_token_count=prefix_tokens,
                    body_token_count=entry.body_token_count,
                    token_count=prefix_tokens + entry.body_token_count,
                    split_origin="fragment",
                )
            ]

        chunks: list[ChunkDraft] = []
        current_parts: list[str] = []
        current_joined = ""
        current_body_tokens = 0
        current_start_line: int | None = None
        current_end_line: int | None = None

        budget = body_budget

        def draft_current() -> ChunkDraft:
            entry = Entry(
                headings=headings,
                body=join_markdown(current_parts),
                start_line=current_start_line,
                end_line=current_end_line,
                body_token_count=current_body_tokens,
            )
            token_count = prefix_tokens + current_body_tokens
            return ChunkDraft(
                entries=[entry],
                headings=headings,
                headings_token_count=prefix_tokens,
                body_token_count=token_count - prefix_tokens,
                token_count=token_count,
                split_origin="fragment",
            )

        for block in blocks:
            if standalone_kinds and block.kind in standalone_kinds:
                if current_parts:
                    chunks.append(draft_current())
                    current_parts = []
                    current_joined = ""
                    current_body_tokens = 0
                    current_start_line = None
                    current_end_line = None

                block_tokens = self.token_counter.count_text(block.text)
                # This chunk will only contain this block and headings.
                block_pieces = self._block_splitter.split_oversized_block(
                    block,
                    default_budget=budget,
                )
                if block_pieces is not None:
                    for piece in block_pieces:
                        piece_tokens = self.token_counter.count_text(piece)
                        entry = Entry(
                            headings=headings,
                            body=piece,
                            start_line=block.start_line,
                            end_line=block.end_line,
                            body_token_count=piece_tokens,
                        )
                        chunks.append(
                            ChunkDraft(
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
                    entry = Entry(
                        headings=headings,
                        body=block.text,
                        start_line=block.start_line,
                        end_line=block.end_line,
                        body_token_count=block_tokens,
                    )

                    chunks.append(
                        ChunkDraft(
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

            block_tokens = self.token_counter.count_text(block.text)
            if current_parts:
                # Between adjacent blocks, recount the previous block with its
                # trailing separator so the running total reflects the rendered
                # join (``last + SEPARATOR``).  Subtree/entry-group boundaries
                # use the cheaper separator-delta window; block joins do not,
                # because the previous block is already fully counted here.
                previous_block = current_parts[-1]
                candidate_body_tokens = (
                    current_body_tokens
                    - self.token_counter.count_text(previous_block)
                    + self.token_counter.count_text(f"{previous_block}{SEPARATOR}")
                    + block_tokens
                )
            else:
                candidate_body_tokens = block_tokens
            # Compare the body footprint against the body-only budget.
            # Whether or not headings render, the heading tokens are constant
            # for every fragment here (all share ``headings``), so comparing
            # body tokens against ``budget`` is equivalent to comparing the
            # full rendered footprint against ``max_tokens``.
            if current_parts and candidate_body_tokens > budget:
                chunks.append(draft_current())
                current_parts = []
                current_joined = ""
                current_body_tokens = 0
                current_start_line = None
                current_end_line = None
                candidate_body_tokens = block_tokens

            if block_tokens <= budget:
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
            # TODO: chunk.tokens should not exceed the max_tokens.
            # Special chunks can be split using a smaller tokens.
            block_pieces = self._block_splitter.split_oversized_block(
                block,
                default_budget=budget,
            )
            if block_pieces is None:
                entry = Entry(
                    headings=headings,
                    body=block.text,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    body_token_count=block_tokens,
                )
                chunks.append(
                    ChunkDraft(
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
                piece_tokens = self.token_counter.count_text(piece)
                entry = Entry(
                    headings=headings,
                    body=piece,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    body_token_count=piece_tokens,
                )
                chunks.append(
                    ChunkDraft(
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
        chunks: list[ChunkDraft],
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
            token_count = self.token_counter.count_text(body)
            # The running estimate mirrors the rendered footprint: full
            # token_count when the common breadcrumb renders, body tokens only
            # when it is omitted.  ``body_token_count`` is correct for both
            # splitters here — SectionSplitter's drafts already exclude heading
            # tokens via the budget hook, and RecursiveSplitter's merge
            # arithmetic folds any displaced (internal relative) heading tokens
            # into body_token_count — so the estimate matches the actually
            # rendered body.
            estimated = self._draft_budget_tokens(chunk)
            # Adjust the estimate for the trailing phantom \n\n in the last
            # entry.  When the last entry has empty body, its heading's
            # trailing \n\n (from heading_path_token_count) was counted in
            # the incremental estimate but is never rendered — there is no
            # next entry for it to separate from.
            if chunk.entries:
                last = chunk.entries[-1]
                if not last.body.strip():
                    relative = last.headings[len(headings) :]
                    if relative:
                        ht = render_heading_path(relative)
                        estimated -= self._separator_delta_after(ht)
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
        body_token_count: int,
    ) -> Entry:
        body = join_markdown([block.text for block in blocks])
        start_lines = [b.start_line for b in blocks if b.start_line is not None]
        end_lines = [b.end_line for b in blocks if b.end_line is not None]

        return Entry(
            headings=headings,
            body=body,
            start_line=min(start_lines) if start_lines else None,
            end_line=max(end_lines) if end_lines else None,
            body_token_count=body_token_count,
        )

    def _entry_group_tail(self, entries: list[Entry]) -> str:
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
        left_draft: ChunkDraft,
        right_draft: ChunkDraft,
        *,
        expected_common: HeadingPath | None = None,
    ) -> ChunkDraft:
        left_headings = left_draft.headings
        right_headings = right_draft.headings

        # Callers that know the merged common prefix by construction (e.g. the
        # recursive splitter packing a section's own body with its children —
        # the common prefix is always the section's path) may pass it directly
        # via ``expected_common`` to avoid recomputing the longest common
        # prefix of the two heading paths.
        if expected_common is not None:
            common_headings = expected_common
        else:
            common_headings = common_heading_path([left_headings, right_headings])
        headings_token_count = self._heading_budget_token_count(common_headings)

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

        return ChunkDraft(
            entries=[*left_draft.entries, *right_draft.entries],
            headings=common_headings,
            headings_token_count=headings_token_count,
            body_token_count=body_token_count,
            token_count=headings_token_count + body_token_count,
            split_origin="merge",
            chunk_type=left_draft.chunk_type,
        )

    def _render_body(
        self,
        entries: list[Entry],
        *,
        common_headings: HeadingPath,
    ) -> str:
        """Render entries into Markdown body content."""
        if not entries:
            return ""

        parts: list[str] = []
        if common_headings and self.options.render_headings:
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

    def _merge_small_chunks(
        self,
        chunks: list[ChunkDraft],
        *,
        parent_headings: HeadingPath | None = None,
    ) -> list[ChunkDraft]:
        """Merge adjacent same-parent chunks below *merge_below_tokens*, bottom-up."""
        merge_below = self.options.merge_below_tokens
        if merge_below is None or merge_below < 0:
            return chunks
        if not chunks:
            return chunks

        merged: list[ChunkDraft] = list(chunks)
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
                and current.token_count < merge_below
                and previous.chunk_type == "paragraph"
                and current.chunk_type == "paragraph"
            ):
                merged_draft = self._merge_drafts(previous, current)
                # Compare the rendered footprint against max_tokens.  Because
                # can_merge guarantees previous.headings == current.headings,
                # the merged common prefix is that shared path.
                if self._draft_budget_tokens(merged_draft) <= self.options.max_tokens:
                    merged[i - 1] = merged_draft
                    del merged[i]
            i -= 1
        return merged


__all__ = ["BaseSplitter"]

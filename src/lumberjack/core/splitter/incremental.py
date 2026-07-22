from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import (
    ChunkDraft,
    Entry,
    HeadingPath,
    MeasuredSection,
    SectionNode,
    SectionTokenCounts,
    ancestor_heading_path,
    common_heading_path,
    render_heading_path,
)
from ..utils import join_rendered_blocks
from .base import BaseSplitter

if TYPE_CHECKING:
    from ..models import Chunk, DocumentAST

SEPARATOR = "\n\n"


class IncrementalCountingMixin(BaseSplitter):
    """Incremental counting strategy: additive estimate + 8-char delta window.

    Sections are measured once into :class:`MeasuredSection` (with body /
    subtree / tail text / single-chunk eligibility).  Budget decisions during
    packing use a running additive estimate carried on each draft; joins
    between entries are approximated by :meth:`_separator_delta_after` (an
    8-char tail window) so the estimate stays cheap.  A full recount of the
    rendered body happens only at finalization.
    """

    _DELTA_WINDOW = 8

    def split(self, document: DocumentAST) -> list[Chunk]:
        """Measure the tree once, then split via the topology's _split_section."""
        measured_root = self._measure_section(self._root_for_splitting(document))
        drafts = self._split_section(measured_root)
        drafts = self._post_process_drafts(drafts)
        return self._finalize_chunks(drafts, document)

    def _draft_running_estimate(self, draft: ChunkDraft) -> int:
        if self.options.render_headings:
            return draft.token_count
        hidden_headings = ancestor_heading_path(
            entry.headings for entry in draft.entries
        )
        return draft.token_count - self._heading_path_token_count(hidden_headings)

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        """Rendered footprint a draft occupies — the running additive estimate."""
        return self._draft_running_estimate(draft)

    def _merge_drafts(
        self,
        left_draft: ChunkDraft,
        right_draft: ChunkDraft,
        *,
        expected_common: HeadingPath | None = None,
    ) -> ChunkDraft:
        """Merge two drafts via additive estimate + separator-delta window."""
        left_headings = left_draft.headings
        right_headings = right_draft.headings
        if expected_common is not None:
            common_headings = expected_common
        else:
            common_headings = common_heading_path([left_headings, right_headings])

        merged_entries = [*left_draft.entries, *right_draft.entries]
        headings_token_count = self._heading_budget_token_count(common_headings)

        left_body_token_count = left_draft.token_count - headings_token_count
        right_body_token_count = right_draft.token_count - headings_token_count

        body_token_count = left_body_token_count + right_body_token_count

        # Account for the \n\n separator between the last left entry and the
        # first right entry introduced by join_rendered_blocks during rendering.
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
            entries=merged_entries,
            headings=common_headings,
            headings_token_count=headings_token_count,
            body_token_count=body_token_count,
            token_count=headings_token_count + body_token_count,
            split_origin="merge",
            chunk_type=left_draft.chunk_type,
        )

    def _finalize_estimate(
        self,
        chunk: ChunkDraft,
        headings: HeadingPath,
        token_count: int,  # noqa: ARG002
    ) -> int:
        """Running estimate adjusted for the trailing phantom separator."""
        estimated_count = self._draft_running_estimate(chunk)
        # When the last entry has empty body, its heading's trailing \n\n
        # (from heading_path_token_count in _measure_section) was counted in
        # the running estimate but is never rendered — there is no next entry
        # for it to separate from.
        if chunk.entries:
            last = chunk.entries[-1]
            if not last.body.strip():
                relative = last.headings[len(headings) :]
                if relative:
                    ht = render_heading_path(relative)
                    estimated_count -= self._separator_delta_after(ht)
        return estimated_count

    def _separator_delta_after(self, text: str) -> int:
        """Estimate the token delta of appending the Markdown separator.

        Uses an 8-character tail window of text (trailing newlines stripped)
        so the two count calls stay cheap.
        """
        if not text:
            return 0
        tail = text.rstrip("\n")[-self._DELTA_WINDOW :]
        return self.tokenizer.count(tail + SEPARATOR, cache=True) - (
            self.tokenizer.count(tail, cache=True)
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
        prev_child: MeasuredSection | None = None
        for child in children:
            # When the previous child is a leaf section with no body blocks,
            # its heading's trailing \n\n (from heading_path_token_count)
            # already serves as the separator to this child.  Adding
            # sep_delta would double-count it.
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

    def _entries_from_section(self, section: MeasuredSection) -> list[Entry]:
        """Render-ready entries for a section selected as a chunk."""
        node = section.node
        entries: list[Entry] = []
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
        if self.options.render_headings:
            rendered_heading_tokens = prefix_tokens
        else:
            rendered_heading_tokens = self._heading_path_token_count(headings[-1:])
        body_budget = max(0, max_tokens - rendered_heading_tokens)

        if rendered_heading_tokens >= max_tokens or not blocks:
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
                body=join_rendered_blocks(current_parts),
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

                block_tokens = self.tokenizer.count(block.text, cache=True)
                # This chunk will only contain this block and headings.
                block_pieces = self._block_splitter.split_oversized_block(
                    block,
                    default_budget=budget,
                )
                if block_pieces is not None:
                    for piece, piece_tokens in block_pieces:
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

            block_tokens = self.tokenizer.count(block.text, cache=True)
            if current_parts:
                # Between adjacent blocks, recount the previous block with its
                # trailing separator so the running total reflects the rendered
                # join (``last + SEPARATOR``).  Subtree/entry-group boundaries
                # use the cheaper separator-delta window; block joins do not,
                # because the previous block is already fully counted here.
                previous_block = current_parts[-1]
                candidate_body_tokens = (
                    current_body_tokens
                    - self.tokenizer.count(previous_block, cache=True)
                    + self.tokenizer.count(f"{previous_block}{SEPARATOR}", cache=True)
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

            for piece, piece_tokens in block_pieces:
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
            rendered = join_rendered_blocks(current_parts)
            if rendered:
                chunks.append(draft_current())

        return chunks

    def _direct_body_drafts(self, section: MeasuredSection) -> list[ChunkDraft]:
        """Emit this section's direct body, without topology recursion."""
        node = section.node
        if not (node.blocks or node.level > 0):
            return []
        has_standalone = any(
            block.kind in self.options.standalone_kinds for block in node.blocks
        )
        if has_standalone or section.counts.body > self.options.ideal_max_tokens:
            return self._split_section_body(section)
        entry = self._entry_from_blocks(
            node.path, node.blocks, body_token_count=section.counts.body
        )
        headings_token_count = self._heading_budget_token_count(node.path)
        return [
            ChunkDraft(
                entries=[entry],
                headings=node.path,
                headings_token_count=headings_token_count,
                body_token_count=section.counts.body,
                token_count=headings_token_count + section.counts.body,
            )
        ]

    def _single_subtree_draft(self, section: MeasuredSection) -> ChunkDraft | None:
        if not section.can_emit_as_single_chunk:
            return None
        entries = self._entries_from_section(section)
        headings = common_heading_path(entry.headings for entry in entries)
        headings_tokens = self._heading_path_token_count(headings)
        token_count = (
            self._heading_path_token_count(section.node.path[:-1])
            + section.counts.subtree
        )
        return ChunkDraft(
            entries=entries,
            headings=headings,
            headings_token_count=headings_tokens,
            body_token_count=token_count - headings_tokens,
            token_count=token_count,
            split_origin="section",
        )

    def _packable_body_draft(self, section: MeasuredSection) -> ChunkDraft | None:
        node = section.node
        if not node.blocks or any(
            block.kind in self.options.standalone_kinds for block in node.blocks
        ):
            return None
        headings_tokens = self._heading_budget_token_count(node.path)
        draft = ChunkDraft(
            entries=[
                self._entry_from_blocks(
                    node.path, node.blocks, body_token_count=section.counts.body
                )
            ],
            headings=node.path,
            headings_token_count=headings_tokens,
            body_token_count=section.counts.body,
            token_count=headings_tokens + section.counts.body,
        )
        return (
            draft
            if self._draft_budget_tokens(draft) <= self.options.ideal_max_tokens
            else None
        )


__all__ = ["IncrementalCountingMixin"]

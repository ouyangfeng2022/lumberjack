from __future__ import annotations

from typing import TYPE_CHECKING

from .._internal.rendering import join_rendered_blocks
from ..models import (
    ChunkDraft,
    Entry,
    HeadingPath,
    MeasuredSection,
    SectionNode,
    SectionTokenCounts,
    common_heading_path,
    render_heading_path,
)
from .base import SEPARATOR, BaseSplitter

if TYPE_CHECKING:
    from ..models import Chunk, DocumentAST


class IncrementalCountingMixin(BaseSplitter):
    """Incremental counting strategy: additive estimate + 8-char delta window.

    Sections are measured once into :class:`MeasuredSection` (with body /
    subtree / tail text / single-chunk eligibility).  Budget decisions during
    packing use a running additive estimate carried on each draft; joins
    between entries are approximated by :meth:`_separator_delta_after` (an
    8-char tail window) so the estimate stays cheap.  Full recounts of the
    separated heading path and body happen only at finalization.
    """

    _DELTA_WINDOW = 8

    def split(self, document: DocumentAST) -> list[Chunk]:
        """Measure the tree once, then split via the topology's _split_section."""
        self._atomic_token_counts: dict[str, int] = {}
        measured_root = self._measure_section(self._root_for_splitting(document))
        drafts = self._split_section(measured_root)
        drafts = self._post_process_drafts(drafts)
        return self._finalize_chunks(drafts, document)

    def _draft_running_estimate(self, draft: ChunkDraft) -> int:
        return draft.token_count

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        """Running estimate selected by the heading-sensitivity policy."""
        return draft.token_count if self.heading_sensitive else draft.body_token_count

    def _count_once(self, text: str) -> int:
        """Count an atomic measurement once during the incremental pre-pass."""
        counts = getattr(self, "_atomic_token_counts", None)
        if counts is None:
            counts = {}
            self._atomic_token_counts = counts
        cached = counts.get(text)
        if cached is not None:
            return cached
        count = self.tokenizer.count(text, cache=True)
        counts[text] = count
        return count

    def _heading_path_token_count(self, path: HeadingPath) -> int:
        if not path:
            return 0
        return self._count_once(render_heading_path(path))

    @staticmethod
    def _draft_body_present(draft: ChunkDraft) -> bool:
        return any(
            entry.body or entry.headings != draft.headings for entry in draft.entries
        )

    def _draft_body_tail(self, draft: ChunkDraft) -> str:
        return self._entry_group_tail(draft.entries) if draft.entries else ""

    def _draft_contribution_below(
        self,
        draft: ChunkDraft,
        common_headings: HeadingPath,
    ) -> tuple[int, str, bool]:
        """Return body estimate/tail/presence after exposing a removed prefix."""
        relative_headings = draft.headings[len(common_headings) :]
        relative_text = render_heading_path(relative_headings)
        relative_tokens = self._heading_path_token_count(relative_headings)
        body_present = self._draft_body_present(draft)
        count = relative_tokens + draft.body_token_count
        if relative_text and body_present:
            count += self._separator_delta_after(relative_text)
        present = bool(relative_text) or body_present
        tail = self._draft_body_tail(draft) if body_present else relative_text
        return count, tail, present

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
        own_heading = self._merged_own_heading(left_draft, right_draft, common_headings)

        left_count, left_tail, left_present = self._draft_contribution_below(
            left_draft, common_headings
        )
        right_count, _right_tail, right_present = self._draft_contribution_below(
            right_draft, common_headings
        )
        body_token_count = left_count + right_count
        if left_present and right_present:
            body_token_count += self._separator_delta_after(left_tail)
        return ChunkDraft(
            entries=merged_entries,
            headings=common_headings,
            own_heading=own_heading,
            headings_token_count=headings_token_count,
            body_token_count=body_token_count,
            token_count=headings_token_count + body_token_count,
            split_origin="merge",
            chunk_type=left_draft.chunk_type,
        )

    def _finalize_estimate(
        self,
        chunk: ChunkDraft,
        external_headings: HeadingPath,  # noqa: ARG002
        token_count: int,  # noqa: ARG002
    ) -> int:
        """Return the separated heading-plus-body running estimate."""
        return self._draft_running_estimate(chunk)

    def _separator_delta_after(self, text: str) -> int:
        """Estimate the token delta of appending the Markdown separator.

        Uses an 8-character tail window of text (trailing newlines stripped)
        so the two count calls stay cheap.
        """
        if not text:
            return 0
        tail = text.rstrip("\n")[-self._DELTA_WINDOW :]
        return self._count_once(tail + SEPARATOR) - self._count_once(tail)

    def _measure_section(self, section: SectionNode) -> MeasuredSection:
        """Return a measured wrapper for *section* and all descendants."""
        children = tuple(self._measure_section(child) for child in section.children)

        # 1. Count body tokens
        body_token_count = 0
        body_texts = [block.text for block in section.blocks if block.text]
        for index, text in enumerate(body_texts):
            if index == len(body_texts) - 1:
                body_token_count += self._count_once(text)
            else:
                body_token_count += self._count_once(text + SEPARATOR)

        # 2. Count title tokens
        if section.level > 0:
            title_text = render_heading_path((section.heading_key,))
            title_token_count = self._count_once(title_text)
        else:
            title_token_count = 0

        # 3. Count the subtree body with this section's own title externalized.
        subtree_token_count = body_token_count
        previous_tail = body_texts[-1] if body_texts else ""
        for child in children:
            child_title = render_heading_path((child.node.heading_key,))
            child_count = child.counts.title + child.counts.subtree
            child_has_body = bool(child.node.blocks or child.children)
            if child_title and child_has_body:
                child_count += self._separator_delta_after(child_title)
            if previous_tail:
                subtree_token_count += self._separator_delta_after(previous_tail)
            subtree_token_count += child_count
            previous_tail = child.tail_text

        if previous_tail:
            tail_text = previous_tail
        elif section.level > 0:
            tail_text = "#" * section.level + " " + section.title
        else:
            tail_text = ""

        body_has_standalone = any(
            block.kind in self.standalone_kinds for block in section.blocks
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
        max_tokens = self.ideal_max_tokens
        standalone_kinds = self.standalone_kinds

        prefix_tokens = (
            self._heading_path_token_count(headings) if node.level > 0 else 0
        )
        budgeted_heading_tokens = prefix_tokens if self.heading_sensitive else 0
        budget_limit = (
            self.max_tokens
            if (
                self.heading_sensitive
                and budgeted_heading_tokens >= self.ideal_max_tokens
            )
            else max_tokens
        )
        body_budget = max(0, budget_limit - budgeted_heading_tokens)

        if budgeted_heading_tokens >= self.max_tokens or not blocks:
            entry = self._entry_from_blocks(
                headings, blocks, body_token_count=section.counts.body
            )
            return [
                ChunkDraft(
                    entries=[entry],
                    headings=node.path,
                    own_heading=node.path[-1] if node.path else None,
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
                own_heading=headings[-1] if headings else None,
                headings_token_count=prefix_tokens,
                body_token_count=current_body_tokens,
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

                block_tokens = self._count_once(block.text)
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
                                own_heading=headings[-1] if headings else None,
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
                            own_heading=headings[-1] if headings else None,
                            headings_token_count=prefix_tokens,
                            body_token_count=block_tokens,
                            token_count=prefix_tokens + block_tokens,
                            split_origin="fragment",
                            chunk_type=block.kind,
                        )
                    )
                continue

            block_tokens = self._count_once(block.text)
            if current_parts:
                # Between adjacent blocks, reuse the pre-measured previous block
                # with its trailing separator so the running total reflects the
                # rendered join. Subtree/entry-group boundaries use the cheaper
                # separator-delta window.
                previous_block = current_parts[-1]
                candidate_body_tokens = (
                    current_body_tokens
                    - self._count_once(previous_block)
                    + self._count_once(f"{previous_block}{SEPARATOR}")
                    + block_tokens
                )
            else:
                candidate_body_tokens = block_tokens
            # Compare the body estimate against the body-only budget. External
            # heading tokens are constant for every fragment here (all share
            # ``headings``), and ``budget`` already reflects heading sensitivity.
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
                        own_heading=headings[-1] if headings else None,
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
                        own_heading=headings[-1] if headings else None,
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
            block.kind in self.standalone_kinds for block in node.blocks
        )
        body_budget = max(
            0,
            self.ideal_max_tokens
            - (
                self._heading_path_token_count(node.path)
                if self.heading_sensitive
                else 0
            ),
        )
        if has_standalone or section.counts.body > body_budget:
            return self._split_section_body(section)
        entry = self._entry_from_blocks(
            node.path, node.blocks, body_token_count=section.counts.body
        )
        headings_token_count = self._heading_budget_token_count(node.path)
        return [
            ChunkDraft(
                entries=[entry],
                headings=node.path,
                own_heading=node.path[-1] if node.path else None,
                headings_token_count=headings_token_count,
                body_token_count=section.counts.body,
                token_count=headings_token_count + section.counts.body,
            )
        ]

    def _single_subtree_draft(self, section: MeasuredSection) -> ChunkDraft | None:
        if not section.can_emit_as_single_chunk:
            return None
        structural_root = section
        if (
            section.node.level == 0
            and not section.node.blocks
            and len(section.children) == 1
        ):
            structural_root = section.children[0]
        entries = self._entries_from_section(structural_root)
        headings = structural_root.node.path
        headings_tokens = self._heading_path_token_count(headings)
        token_count = headings_tokens + structural_root.counts.subtree
        return ChunkDraft(
            entries=entries,
            headings=headings,
            own_heading=headings[-1] if headings else None,
            headings_token_count=headings_tokens,
            body_token_count=structural_root.counts.subtree,
            token_count=token_count,
            split_origin="section",
        )

    def _packable_body_draft(self, section: MeasuredSection) -> ChunkDraft | None:
        node = section.node
        if not node.blocks or any(
            block.kind in self.standalone_kinds for block in node.blocks
        ):
            return None
        headings_tokens = self._heading_budget_token_count(node.path)
        entry = self._entry_from_blocks(
            node.path, node.blocks, body_token_count=section.counts.body
        )
        draft = ChunkDraft(
            entries=[entry],
            headings=node.path,
            own_heading=node.path[-1] if node.path else None,
            headings_token_count=headings_tokens,
            body_token_count=section.counts.body,
            token_count=headings_tokens + section.counts.body,
        )
        return (
            draft if self._draft_budget_tokens(draft) <= self.ideal_max_tokens else None
        )


__all__ = ["IncrementalCountingMixin"]

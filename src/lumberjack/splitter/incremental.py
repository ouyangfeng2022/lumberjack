from __future__ import annotations

from .._internal.rendering import RENDER_SEPARATOR, join_rendered_blocks
from ..models import (
    ChunkDraft,
    DocTree,
    Entry,
    HeadingPath,
    common_heading_path,
    render_heading_path,
)
from .base import BaseSplitter
from .context import IncrementalCountingContext, SectionView


class IncrementalCountingMixin(BaseSplitter):
    """Incremental counting strategy: additive estimate + 8-char delta window.

    Sections are measured once into :class:`SectionView` (with title / body /
    subtree / tail text / single-draft eligibility). Budget decisions during
    packing use a running additive estimate carried on each draft; joins
    between entries are approximated by :meth:`_separator_delta_after` (an
    8-char tail window) so the estimate stays cheap.  Full recounts of the
    separated heading path and body happen only at finalization.
    """

    _DELTA_WINDOW = 8

    def split(self, document: DocTree) -> list[ChunkDraft]:
        """Measure the tree once, then split via the topology's _split_section."""
        self._atomic_token_counts: dict[str, int] = {}
        root = IncrementalCountingContext(self).prepare(
            self._root_for_splitting(document)
        )
        return self._post_process_drafts(self._split_section(root))

    def _draft_running_estimate(self, draft: ChunkDraft) -> int:
        return draft.token_count

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        """Running estimate selected by the heading-sensitivity policy."""
        return (
            draft.token_count
            if self.heading_sensitive
            else self._body_budget_tokens(draft)
        )

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
            token_count=self._chunk_token_count(headings_token_count, body_token_count),
            split_origin="merge",
            chunk_type=left_draft.chunk_type,
        )

    def _finalize_estimate(
        self,
        draft: ChunkDraft,
        external_headings: HeadingPath,  # noqa: ARG002
        token_count: int,  # noqa: ARG002
    ) -> int:
        """Return the separated heading-plus-body running estimate."""
        return self._draft_running_estimate(draft)

    def _separator_delta_after(self, text: str) -> int:
        """Estimate the token delta of appending the Markdown separator.

        Uses an 8-character tail window of text (trailing newlines stripped)
        so the two count calls stay cheap.
        """
        if not text:
            return 0
        tail = text.rstrip("\n")[-self._DELTA_WINDOW :]
        return self._count_once(tail + RENDER_SEPARATOR) - self._count_once(tail)

    @staticmethod
    def _view_body_tokens(section: SectionView) -> int:
        if section.body_tokens is None:
            raise TypeError("incremental section view is missing body_tokens")
        return section.body_tokens

    @staticmethod
    def _view_subtree_tokens(section: SectionView) -> int:
        if section.subtree_tokens is None:
            raise TypeError("incremental section view is missing subtree_tokens")
        return section.subtree_tokens

    @staticmethod
    def _view_can_emit_as_single_chunk(section: SectionView) -> bool:
        if section.can_emit_as_single_chunk is None:
            raise TypeError(
                "incremental section view is missing can_emit_as_single_chunk"
            )
        return section.can_emit_as_single_chunk

    def _entries_from_section(self, section: SectionView) -> list[Entry]:
        """Render-ready entries for a section selected as a draft."""
        node = section.node
        entries: list[Entry] = []
        if node.blocks or (not section.children and node.level > 0):
            entries.append(
                self._entry_from_blocks(
                    node.path,
                    node.blocks,
                    body_token_count=self._view_body_tokens(section),
                )
            )

        for child in section.children:
            entries.extend(self._entries_from_section(child))

        return entries

    def _split_section_body(
        self,
        section: SectionView,
    ) -> list[ChunkDraft]:
        """Split a section's own blocks into fragments, then into draft drafts."""
        node = section.node
        headings = node.path
        blocks = node.blocks
        max_tokens = self.ideal_max_tokens
        standalone_kinds = self.standalone_kinds
        body_tokens = self._view_body_tokens(section)

        prefix_tokens = (
            self._heading_path_token_count(headings) if node.level > 0 else 0
        )
        budgeted_heading_tokens = prefix_tokens if self.heading_sensitive else 0
        fixed_tokens = budgeted_heading_tokens + self.separator_token_count
        budget_limit = (
            self.max_tokens
            if self.heading_sensitive and fixed_tokens >= self.ideal_max_tokens
            else max_tokens
        )
        body_budget = max(0, budget_limit - fixed_tokens)

        if fixed_tokens >= self.max_tokens or not blocks:
            entry = self._entry_from_blocks(
                headings, blocks, body_token_count=body_tokens
            )
            return [
                ChunkDraft(
                    entries=[entry],
                    headings=node.path,
                    own_heading=node.path[-1] if node.path else None,
                    headings_token_count=prefix_tokens,
                    body_token_count=entry.body_token_count,
                    token_count=self._chunk_token_count(
                        prefix_tokens, entry.body_token_count
                    ),
                    split_origin="fragment",
                )
            ]

        drafts: list[ChunkDraft] = []
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
            token_count = self._chunk_token_count(prefix_tokens, current_body_tokens)
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
                    drafts.append(draft_current())
                    current_parts = []
                    current_joined = ""
                    current_body_tokens = 0
                    current_start_line = None
                    current_end_line = None

                block_tokens = self._count_once(block.text)
                # This draft will only contain this block and headings.
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
                        drafts.append(
                            ChunkDraft(
                                entries=[entry],
                                headings=headings,
                                own_heading=headings[-1] if headings else None,
                                headings_token_count=prefix_tokens,
                                body_token_count=piece_tokens,
                                token_count=self._chunk_token_count(
                                    prefix_tokens, piece_tokens
                                ),
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

                    drafts.append(
                        ChunkDraft(
                            entries=[entry],
                            headings=headings,
                            own_heading=headings[-1] if headings else None,
                            headings_token_count=prefix_tokens,
                            body_token_count=block_tokens,
                            token_count=self._chunk_token_count(
                                prefix_tokens, block_tokens
                            ),
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
                    + self._count_once(f"{previous_block}{RENDER_SEPARATOR}")
                    + block_tokens
                )
            else:
                candidate_body_tokens = block_tokens
            # Compare the body estimate against the body-only budget. External
            # heading tokens are constant for every fragment here (all share
            # ``headings``), and ``budget`` already reflects heading sensitivity.
            if current_parts and candidate_body_tokens > budget:
                drafts.append(draft_current())
                current_parts = []
                current_joined = ""
                current_body_tokens = 0
                current_start_line = None
                current_end_line = None
                candidate_body_tokens = block_tokens

            if block_tokens <= budget:
                current_parts.append(block.text)
                candidate_text = (
                    current_joined + RENDER_SEPARATOR + block.text
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
            # TODO: draft.tokens should not exceed the max_tokens.
            # Special drafts can be split using a smaller tokens.
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
                drafts.append(
                    ChunkDraft(
                        entries=[entry],
                        headings=headings,
                        own_heading=headings[-1] if headings else None,
                        headings_token_count=prefix_tokens,
                        body_token_count=block_tokens,
                        token_count=self._chunk_token_count(
                            prefix_tokens, block_tokens
                        ),
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
                drafts.append(
                    ChunkDraft(
                        entries=[entry],
                        headings=headings,
                        own_heading=headings[-1] if headings else None,
                        headings_token_count=prefix_tokens,
                        body_token_count=piece_tokens,
                        token_count=self._chunk_token_count(
                            prefix_tokens, piece_tokens
                        ),
                        split_origin="text_piece",
                        chunk_type="paragraph",
                    )
                )

        if current_parts:
            rendered = join_rendered_blocks(current_parts)
            if rendered:
                drafts.append(draft_current())

        return drafts

    def _direct_body_drafts(self, section: SectionView) -> list[ChunkDraft]:
        """Emit this section's direct body, without topology recursion."""
        node = section.node
        body_tokens = self._view_body_tokens(section)
        if not (node.blocks or node.level > 0):
            return []
        has_standalone = any(
            block.kind in self.standalone_kinds for block in node.blocks
        )
        body_budget = max(
            0,
            self.ideal_max_tokens
            - self.separator_token_count
            - (
                self._heading_path_token_count(node.path)
                if self.heading_sensitive
                else 0
            ),
        )
        if has_standalone or body_tokens > body_budget:
            return self._split_section_body(section)
        entry = self._entry_from_blocks(
            node.path, node.blocks, body_token_count=body_tokens
        )
        headings_token_count = self._heading_budget_token_count(node.path)
        return [
            ChunkDraft(
                entries=[entry],
                headings=node.path,
                own_heading=node.path[-1] if node.path else None,
                headings_token_count=headings_token_count,
                body_token_count=body_tokens,
                token_count=self._chunk_token_count(headings_token_count, body_tokens),
            )
        ]

    def _single_subtree_draft(self, section: SectionView) -> ChunkDraft | None:
        if not self._view_can_emit_as_single_chunk(section):
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
        subtree_tokens = self._view_subtree_tokens(structural_root)
        token_count = self._chunk_token_count(headings_tokens, subtree_tokens)
        return ChunkDraft(
            entries=entries,
            headings=headings,
            own_heading=headings[-1] if headings else None,
            headings_token_count=headings_tokens,
            body_token_count=subtree_tokens,
            token_count=token_count,
            split_origin="section",
        )

    def _packable_body_draft(self, section: SectionView) -> ChunkDraft | None:
        node = section.node
        body_tokens = self._view_body_tokens(section)
        if not node.blocks or any(
            block.kind in self.standalone_kinds for block in node.blocks
        ):
            return None
        headings_tokens = self._heading_budget_token_count(node.path)
        entry = self._entry_from_blocks(
            node.path, node.blocks, body_token_count=body_tokens
        )
        draft = ChunkDraft(
            entries=[entry],
            headings=node.path,
            own_heading=node.path[-1] if node.path else None,
            headings_token_count=headings_tokens,
            body_token_count=body_tokens,
            token_count=self._chunk_token_count(headings_tokens, body_tokens),
        )
        return (
            draft if self._draft_budget_tokens(draft) <= self.ideal_max_tokens else None
        )


__all__ = ["IncrementalCountingMixin"]

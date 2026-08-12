from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .._internal.rendering import join_rendered_blocks
from ..models import (
    ChunkDraft,
    DocumentBlock,
    Entry,
    HeadingKey,
    HeadingPath,
    SectionNode,
    common_heading_path,
)
from .base import BaseSplitter

if TYPE_CHECKING:
    from ..models import Chunk, DocumentAST


class ExactCountingMixin(BaseSplitter):
    """Exact counting strategy: full recount at every budget decision.

    Every budget decision fully recounts the actually-rendered candidate text
    via :meth:`_rendered_token_count`.  No additive arithmetic, no
    :meth:`_measure_section` pre-pass, no separator-delta window.  The
    ``SectionNode`` tree is walked directly.
    """

    def split(self, document: DocumentAST) -> list[Chunk]:
        """Split by walking the raw ``SectionNode`` tree (no pre-measure)."""
        drafts = self._split_section(self._root_for_splitting(document))
        drafts = self._post_process_drafts(drafts)
        return self._finalize_chunks(drafts, document)

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        """Exact logical footprint selected by the heading-sensitivity policy."""
        return draft.token_count if self.heading_sensitive else draft.body_token_count

    def _merge_drafts(
        self,
        left_draft: ChunkDraft,
        right_draft: ChunkDraft,
        *,
        expected_common: HeadingPath | None = None,
    ) -> ChunkDraft:
        """Merge two drafts by fully recounting separated headings and body."""
        left_headings = left_draft.headings
        right_headings = right_draft.headings
        if expected_common is not None:
            common_headings = expected_common
        else:
            common_headings = common_heading_path([left_headings, right_headings])
        merged_entries = [*left_draft.entries, *right_draft.entries]
        own_heading = self._merged_own_heading(left_draft, right_draft, common_headings)
        return self._draft_from_entries(
            merged_entries,
            common_headings,
            own_heading=own_heading,
            origin="merge",
            chunk_type=left_draft.chunk_type,
        )

    def _finalize_estimate(
        self,
        chunk: ChunkDraft,  # noqa: ARG002
        external_headings: HeadingPath,  # noqa: ARG002
        token_count: int,
    ) -> int:
        """Exact path: the split-time estimate already equals the full recount."""
        return token_count

    def _exact_body_budget(self, headings: HeadingPath) -> int:
        """Body-only token budget for exact-path body splitting."""
        if not self.heading_sensitive:
            return self.ideal_max_tokens
        prefix_tokens = self._heading_path_token_count(headings)
        limit = (
            self.max_tokens
            if prefix_tokens >= self.ideal_max_tokens
            else self.ideal_max_tokens
        )
        return max(0, limit - prefix_tokens)

    def _draft_from_entries(
        self,
        entries: list[Entry],
        headings: HeadingPath,
        *,
        own_heading: HeadingKey | None,
        origin: Literal["section", "fragment", "text_piece", "merge"],
        chunk_type: str = "paragraph",
    ) -> ChunkDraft:
        """Build a draft by fully recounting its separated public fields."""
        body = self._render_body(entries, external_headings=headings)
        body_tokens = self.tokenizer.count(body, cache=True)
        prefix_tokens = self._heading_path_token_count(headings)
        token_count = prefix_tokens + body_tokens
        return ChunkDraft(
            entries=entries,
            headings=headings,
            own_heading=own_heading,
            headings_token_count=prefix_tokens,
            body_token_count=body_tokens,
            token_count=token_count,
            split_origin=origin,
            chunk_type=chunk_type,
        )

    def _entries_from_section(self, section: SectionNode) -> list[Entry]:
        """Render-ready entries for a section selected as a chunk."""
        entries: list[Entry] = []
        if section.blocks or (not section.children and section.level > 0):
            body = join_rendered_blocks([b.text for b in section.blocks])
            entries.append(
                Entry(
                    headings=section.path,
                    body=body,
                    start_line=self._min_start_lines(section.blocks),
                    end_line=self._max_end_lines(section.blocks),
                    body_token_count=self.tokenizer.count(body, cache=True),
                )
            )

        for child in section.children:
            entries.extend(self._entries_from_section(child))

        return entries

    def _split_section_body(
        self,
        section: SectionNode,
    ) -> list[ChunkDraft]:
        """Split a section's own blocks via full rendered counts.

        Each budget decision recounts the actually-rendered candidate body.
        No additive arithmetic, no separator-delta window.
        """
        headings = section.path
        blocks = section.blocks
        budget = self._exact_body_budget(headings)

        if (
            self.heading_sensitive
            and self._heading_path_token_count(headings) >= self.max_tokens
        ) or not blocks:
            body = join_rendered_blocks([block.text for block in blocks])
            entry = self._entry_from_blocks(
                headings,
                blocks,
                body_token_count=self.tokenizer.count(body, cache=True),
            )
            return [
                self._draft_from_entries(
                    [entry],
                    headings,
                    own_heading=headings[-1] if headings else None,
                    origin="fragment",
                )
            ]

        chunks: list[ChunkDraft] = []
        current_entries: list[Entry] = []
        standalone_kinds = self.standalone_kinds

        def flush_current() -> None:
            if not current_entries:
                return
            entries = list(current_entries)
            chunks.append(
                self._draft_from_entries(
                    entries,
                    headings,
                    own_heading=headings[-1] if headings else None,
                    origin="fragment",
                )
            )
            current_entries.clear()

        def make_entry(block: DocumentBlock, body: str, body_tokens: int) -> Entry:
            return Entry(
                headings=headings,
                body=body,
                start_line=block.start_line,
                end_line=block.end_line,
                body_token_count=body_tokens,
            )

        for block in blocks:
            if standalone_kinds and block.kind in standalone_kinds:
                flush_current()
                block_pieces = self._block_splitter.split_oversized_block(
                    block,
                    default_budget=budget,
                )
                if block_pieces is not None:
                    for piece, piece_tokens in block_pieces:
                        entry = make_entry(block, piece, piece_tokens)
                        chunks.append(
                            self._draft_from_entries(
                                [entry],
                                headings,
                                own_heading=headings[-1] if headings else None,
                                origin="text_piece",
                                chunk_type=block.kind,
                            )
                        )
                else:
                    entry = make_entry(
                        block, block.text, self.tokenizer.count(block.text, cache=True)
                    )
                    chunks.append(
                        self._draft_from_entries(
                            [entry],
                            headings,
                            own_heading=headings[-1] if headings else None,
                            origin="fragment",
                            chunk_type=block.kind,
                        )
                    )
                continue

            entry = make_entry(
                block, block.text, self.tokenizer.count(block.text, cache=True)
            )
            block_draft = self._draft_from_entries(
                [entry],
                headings,
                own_heading=headings[-1] if headings else None,
                origin="fragment",
                chunk_type="paragraph",
            )

            if (
                block.text
                and self._draft_budget_tokens(block_draft) > self.ideal_max_tokens
            ):
                flush_current()
                block_pieces = self._block_splitter.split_oversized_block(
                    block,
                    default_budget=budget,
                )
                if block_pieces is None:
                    chunks.append(block_draft)
                else:
                    for piece, piece_tokens in block_pieces:
                        pe = make_entry(block, piece, piece_tokens)
                        chunks.append(
                            self._draft_from_entries(
                                [pe],
                                headings,
                                own_heading=headings[-1] if headings else None,
                                origin="text_piece",
                                chunk_type="paragraph",
                            )
                        )
                continue

            candidate_entries = [*current_entries, entry]
            candidate_draft = self._draft_from_entries(
                candidate_entries,
                headings,
                own_heading=headings[-1] if headings else None,
                origin="fragment",
            )
            if (
                current_entries
                and self._draft_budget_tokens(candidate_draft) > self.ideal_max_tokens
            ):
                flush_current()

            current_entries.append(entry)

        flush_current()
        return chunks

    def _section_has_standalone(self, section: SectionNode) -> bool:
        """Whether this section's subtree contains any standalone block."""
        standalone_kinds = self.standalone_kinds
        if any(b.kind in standalone_kinds for b in section.blocks):
            return True
        return any(self._section_has_standalone(c) for c in section.children)

    def _direct_body_drafts(self, section: SectionNode) -> list[ChunkDraft]:
        """Emit this section's direct body, without topology recursion."""
        if not (section.blocks or section.level > 0):
            return []
        body = join_rendered_blocks([block.text for block in section.blocks])
        body_tokens = self.tokenizer.count(body, cache=True)
        has_standalone = any(
            block.kind in self.standalone_kinds for block in section.blocks
        )
        entry = Entry(
            headings=section.path,
            body=body,
            start_line=self._min_start_lines(section.blocks),
            end_line=self._max_end_lines(section.blocks),
            body_token_count=body_tokens,
        )
        draft = self._draft_from_entries(
            [entry],
            section.path,
            own_heading=section.path[-1] if section.path else None,
            origin="section",
        )
        if has_standalone or self._draft_budget_tokens(draft) > self.ideal_max_tokens:
            return self._split_section_body(section)
        return [draft]

    def _single_subtree_draft(self, section: SectionNode) -> ChunkDraft | None:
        if self._section_has_standalone(section):
            return None
        structural_root = section
        if section.level == 0 and not section.blocks and len(section.children) == 1:
            structural_root = section.children[0]
        entries = self._entries_from_section(structural_root)
        return self._draft_from_entries(
            entries,
            structural_root.path,
            own_heading=(structural_root.path[-1] if structural_root.path else None),
            origin="section",
        )

    def _packable_body_draft(self, section: SectionNode) -> ChunkDraft | None:
        if not section.blocks or any(
            block.kind in self.standalone_kinds for block in section.blocks
        ):
            return None
        entry = self._entry_from_blocks(
            section.path,
            section.blocks,
            body_token_count=self.tokenizer.count(
                join_rendered_blocks([block.text for block in section.blocks]),
                cache=True,
            ),
        )
        draft = self._draft_from_entries(
            [entry],
            section.path,
            own_heading=section.path[-1] if section.path else None,
            origin="section",
        )
        return (
            draft if self._draft_budget_tokens(draft) <= self.ideal_max_tokens else None
        )


__all__ = ["ExactCountingMixin"]

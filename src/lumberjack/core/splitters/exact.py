from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ..models import (
    ChunkDraft,
    Entry,
    HeadingPath,
    MarkdownBlock,
    SectionNode,
    common_heading_path,
)
from ..utils import join_markdown
from .base import BaseSplitter

if TYPE_CHECKING:
    from ..models import Chunk, DocumentAST

SEPARATOR = "\n\n"


class ExactCountingMixin(BaseSplitter):
    """Exact counting strategy: full recount at every budget decision.

    Every budget decision fully recounts the actually-rendered candidate text
    via :meth:`_rendered_token_count`.  No additive arithmetic, no
    :meth:`_measure_section` pre-pass, no separator-delta window.  The
    ``SectionNode`` tree is walked directly.
    """

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def split(self, document: DocumentAST) -> list[Chunk]:
        """Split by walking the raw ``SectionNode`` tree (no pre-measure)."""
        drafts = self._split_section(document.root)
        drafts = self._post_process_drafts(drafts)
        return self._finalize_chunks(drafts, document)

    # ------------------------------------------------------------------
    # Strategy primitives used by topology classes
    # ------------------------------------------------------------------

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        """Rendered footprint a draft occupies — full recount of the body."""
        return self._rendered_token_count(draft.entries)

    def _merge_drafts(
        self,
        left_draft: ChunkDraft,
        right_draft: ChunkDraft,
        *,
        expected_common: HeadingPath | None = None,
    ) -> ChunkDraft:
        """Merge two drafts by deriving token counts from the rendered body."""
        left_headings = left_draft.headings
        right_headings = right_draft.headings
        if expected_common is not None:
            common_headings = expected_common
        else:
            common_headings = common_heading_path([left_headings, right_headings])
        merged_entries = [*left_draft.entries, *right_draft.entries]
        return self._draft_from_entries(
            merged_entries,
            common_headings,
            origin="merge",
            chunk_type=left_draft.chunk_type,
        )

    def _finalize_estimate(
        self,
        chunk: ChunkDraft,  # noqa: ARG002
        headings: HeadingPath,  # noqa: ARG002
        token_count: int,
    ) -> int:
        """Exact path: the split-time estimate already equals the full recount."""
        return token_count

    # ------------------------------------------------------------------
    # Exact-path helpers
    # ------------------------------------------------------------------

    def _exact_body_budget(self, headings: HeadingPath) -> int:
        """Body-only token budget for exact-path body splitting."""
        max_tokens = self.options.ideal_max_tokens
        if self.options.render_headings:
            prefix_tokens = self._heading_path_token_count(headings)
        else:
            prefix_tokens = self._heading_path_token_count(headings[-1:])
        return max(0, max_tokens - prefix_tokens)

    def _draft_from_entries(
        self,
        entries: list[Entry],
        headings: HeadingPath,
        *,
        origin: Literal["section", "fragment", "text_piece", "merge"],
        chunk_type: str = "paragraph",
    ) -> ChunkDraft:
        """Build a ChunkDraft from entries, deriving token counts from render."""
        body_tokens = self._rendered_token_count(entries)
        prefix_tokens = self._heading_path_token_count(headings)
        return ChunkDraft(
            entries=entries,
            headings=headings,
            headings_token_count=prefix_tokens,
            body_token_count=body_tokens,
            token_count=body_tokens,
            split_origin=origin,
            chunk_type=chunk_type,
        )

    def _entries_from_section(self, section: SectionNode) -> list[Entry]:
        """Render-ready entries for a section selected as a chunk."""
        entries: list[Entry] = []
        if section.blocks or (not section.children and section.level > 0):
            body = join_markdown([b.text for b in section.blocks])
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

        if not blocks:
            entry = self._entry_from_blocks(headings, blocks, body_token_count=0)
            prefix_tokens = self._heading_path_token_count(headings)
            return [
                ChunkDraft(
                    entries=[entry],
                    headings=headings,
                    headings_token_count=prefix_tokens,
                    body_token_count=0,
                    token_count=prefix_tokens,
                    split_origin="fragment",
                )
            ]

        chunks: list[ChunkDraft] = []
        current_entries: list[Entry] = []
        standalone_kinds = self.options.standalone_kinds

        def flush_current() -> None:
            if not current_entries:
                return
            entries = list(current_entries)
            chunks.append(
                self._draft_from_entries(
                    entries,
                    common_heading_path(e.headings for e in entries),
                    origin="fragment",
                )
            )
            current_entries.clear()

        def make_entry(block: MarkdownBlock, body: str, body_tokens: int) -> Entry:
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
                    for piece in block_pieces:
                        entry = make_entry(
                            block, piece, self.tokenizer.count(piece, cache=True)
                        )
                        chunks.append(
                            self._draft_from_entries(
                                [entry],
                                headings,
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
                            origin="fragment",
                            chunk_type=block.kind,
                        )
                    )
                continue

            entry = make_entry(
                block, block.text, self.tokenizer.count(block.text, cache=True)
            )

            if block.text and self.tokenizer.count(block.text, cache=True) > budget:
                flush_current()
                block_pieces = self._block_splitter.split_oversized_block(
                    block,
                    default_budget=budget,
                )
                if block_pieces is None:
                    chunks.append(
                        self._draft_from_entries(
                            [entry],
                            headings,
                            origin="fragment",
                            chunk_type="paragraph",
                        )
                    )
                else:
                    for piece in block_pieces:
                        pe = make_entry(
                            block, piece, self.tokenizer.count(piece, cache=True)
                        )
                        chunks.append(
                            self._draft_from_entries(
                                [pe],
                                headings,
                                origin="text_piece",
                                chunk_type="paragraph",
                            )
                        )
                continue

            candidate_entries = [*current_entries, entry]
            if (
                current_entries
                and self._rendered_token_count(candidate_entries)
                > self.options.ideal_max_tokens
            ):
                flush_current()

            current_entries.append(entry)

        flush_current()
        return chunks

    def _section_has_standalone(self, section: SectionNode) -> bool:
        """Whether this section's subtree contains any standalone block."""
        standalone_kinds = self.options.standalone_kinds
        if any(b.kind in standalone_kinds for b in section.blocks):
            return True
        return any(self._section_has_standalone(c) for c in section.children)


__all__ = ["ExactCountingMixin"]

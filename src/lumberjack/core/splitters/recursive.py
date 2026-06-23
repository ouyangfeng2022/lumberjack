from __future__ import annotations

from .base import _BaseSplitter
from .drafts import ChunkDraft, Entry, MeasuredSection
from .headings import common_heading_path


class RecursiveSplitter(_BaseSplitter):
    """Recursively split a document into token-bounded chunks.

    Unlike SectionSplitter which keeps each heading section intact, this splitter
    recursively breaks down oversized sections and merges small adjacent chunks
    to stay within the configured max_tokens budget.

    ``render_headings`` caveat: this splitter budgets with heading tokens
    included regardless of ``SplitOptions.render_headings``.  When the flag is
    False the common heading breadcrumb is omitted from ``Chunk.body`` but the
    split budget still reserves tokens for it — the resulting body is therefore
    shorter than ``max_tokens`` would otherwise allow.  This is a known
    limitation caused by the structural coupling between a section's title and
    its role as either chunk-prefix or internal-relative-heading (which is only
    determined after pack/merge).  Reconciling the budget requires a deeper
    refactor and is deferred to a later revision.
    """

    def _split_section(
        self,
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
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
                ChunkDraft(
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
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Split a section's body blocks and child sections, packing adjacent entries that fit."""
        node = section.node
        chunks: list[ChunkDraft] = []
        current_draft: ChunkDraft | None = None
        standalone_kinds = self.options.standalone_kinds

        common_heading_token_count = self._heading_path_token_count(node.path)
        budget_token_count = self.options.ideal_max_tokens - common_heading_token_count

        def flush_current() -> None:
            nonlocal current_draft

            if not current_draft:
                return

            chunks.append(current_draft)
            current_draft = ChunkDraft(
                entries=[],
                headings=node.path,
                headings_token_count=common_heading_token_count,
                body_token_count=0,
                token_count=common_heading_token_count,
            )

        def add_packable(new_draft: ChunkDraft) -> None:
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
                draft = ChunkDraft(
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

                    draft = ChunkDraft(
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


__all__ = ["RecursiveSplitter"]

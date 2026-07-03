from __future__ import annotations

from ..models import (
    ChunkDraft,
    Entry,
    MeasuredSection,
    SectionNode,
    common_heading_path,
)
from ..utils import join_markdown
from .base import BaseSplitter
from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin


class ExactRecursiveSplitter(ExactCountingMixin, BaseSplitter):
    """Recursively split a document into token-bounded chunks (exact counting).

    Walks the raw :class:`SectionNode` tree.  Oversized sections are broken
    down by descending into children and packing adjacent body/child entries
    that fit the budget; small adjacent chunks are merged.  Every budget
    decision fully recounts the rendered candidate text — no pre-measure, no
    incremental arithmetic, no separator-delta window.

    Registered as ``"recursive"`` (the default) and ``"exact-recursive"``.
    Works with any tokenizer.
    """

    def _split_section(self, section: SectionNode) -> list[ChunkDraft]:
        """Recursively split a section via full rendered token counts."""
        if not (section.blocks or section.children or section.level > 0):
            return []

        entries = self._entries_from_section(section)
        common_headings = common_heading_path(entry.headings for entry in entries)

        standalone_kinds = self.options.standalone_kinds
        body_has_standalone = any(b.kind in standalone_kinds for b in section.blocks)
        child_has_standalone = any(
            self._section_has_standalone(child) for child in section.children
        )
        can_emit_as_single_chunk = not body_has_standalone and not child_has_standalone

        if can_emit_as_single_chunk:
            single = self._draft_from_entries(
                entries,
                common_headings,
                origin="section",
            )
            if self._draft_budget_tokens(single) <= self.options.ideal_max_tokens:
                return [single]

        if section.children:
            return self._split_section_children(section)

        chunks = self._split_section_body(section)
        return self._merge_small_chunks(chunks, parent_headings=section.path)

    def _split_section_children(
        self,
        section: SectionNode,
    ) -> list[ChunkDraft]:
        """Pack a section's body entries and child drafts by full rendered counts."""
        node = section
        chunks: list[ChunkDraft] = []
        current_draft: ChunkDraft | None = None
        standalone_kinds = self.options.standalone_kinds

        def flush_current() -> None:
            nonlocal current_draft
            if not current_draft:
                return
            chunks.append(current_draft)
            current_draft = None

        def add_packable(new_draft: ChunkDraft) -> None:
            nonlocal current_draft
            if not current_draft:
                current_draft = new_draft
                return

            temp_merged = self._merge_drafts(
                current_draft, new_draft, expected_common=node.path
            )
            if self._draft_budget_tokens(temp_merged) > self.options.ideal_max_tokens:
                flush_current()
                current_draft = new_draft
                return
            current_draft = temp_merged

        if node.blocks:
            body_has_standalone = any(b.kind in standalone_kinds for b in node.blocks)
            if body_has_standalone:
                flush_current()
                chunks.extend(self._split_section_body(node))
            else:
                body = join_markdown([b.text for b in node.blocks])
                body_tokens = self.tokenizer.count(body, cache=True)
                entry = Entry(
                    headings=node.path,
                    body=body,
                    start_line=self._min_start_lines(node.blocks),
                    end_line=self._max_end_lines(node.blocks),
                    body_token_count=body_tokens,
                )
                draft = self._draft_from_entries(
                    [entry],
                    node.path,
                    origin="section",
                )
                if self._draft_budget_tokens(draft) <= self.options.ideal_max_tokens:
                    add_packable(draft)
                else:
                    flush_current()
                    chunks.extend(self._split_section_body(node))

        for child in section.children:
            if not (child.blocks or child.children or child.level > 0):
                continue

            child_entries = self._entries_from_section(child)
            if not child_entries:
                continue
            child_common = common_heading_path(
                entry.headings for entry in child_entries
            )
            child_single = self._draft_from_entries(
                child_entries,
                child_common,
                origin="section",
            )

            # If the child subtree fits as one chunk within budget, pack it.
            if (
                self._section_has_standalone(child)
                or self._draft_budget_tokens(child_single)
                > self.options.ideal_max_tokens
            ):
                flush_current()
                chunks.extend(self._split_section(child))
            else:
                add_packable(child_single)

        flush_current()
        return self._merge_small_chunks(chunks, parent_headings=node.path)


class IncrementalRecursiveSplitter(IncrementalCountingMixin, BaseSplitter):
    """Recursive topology with the additive incremental estimate path.

    Sections are pre-measured once into :class:`MeasuredSection`; budget
    decisions use a running estimate and an 8-char separator-delta window
    for joins; a full recount happens only at finalization.

    Registered as ``"incremental-recursive"``.  Works with any tokenizer.
    """

    def _split_section(
        self,
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Recursively split a measured section into chunk drafts."""
        if not (section.node.blocks or section.children or section.node.level > 0):
            return []
        entries = self._entries_from_section(section)
        common_headings = common_heading_path(entry.headings for entry in entries)
        headings_token_count = self._heading_path_token_count(common_headings)

        chunk_token_count = (
            self._heading_path_token_count(section.node.path[:-1])
            + section.counts.subtree
        )

        # Build the single-chunk draft but tag it with the entries' actual
        # common prefix (not necessarily section.node.path when the section
        # has no body and asymmetric children).  Keeping draft.headings equal
        # to the true common prefix makes finalize's recompute a no-op.
        single_chunk_draft = ChunkDraft(
            entries=entries,
            headings=common_headings,
            headings_token_count=headings_token_count,
            body_token_count=chunk_token_count - headings_token_count,
            token_count=chunk_token_count,
        )

        if (
            self._draft_budget_tokens(single_chunk_draft)
            <= self.options.ideal_max_tokens
            and section.can_emit_as_single_chunk
        ):
            return [single_chunk_draft]

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

        # Full heading token count — kept on every draft so merge arithmetic
        # stays self-consistent (displaced heading tokens fall back into the
        # body when a merge shrinks the common prefix).
        common_heading_token_count = self._heading_path_token_count(node.path)
        # Body/child budget for the packing decision.  When render_headings=
        # False the common breadcrumb is not rendered, so the full
        # ideal_max_tokens is available for body and child content.
        if self.options.render_headings:
            budget_token_count = (
                self.options.ideal_max_tokens - common_heading_token_count
            )
        else:
            budget_token_count = self.options.ideal_max_tokens

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

            # The merged common prefix is always node.path by construction:
            # every packable candidate is either this section's own body draft
            # (headings == node.path) or a direct child's draft (headings starts
            # with node.path).  Passing it directly avoids recomputing the
            # longest common prefix of the two heading paths.
            temp_merged_draft = self._merge_drafts(
                current_draft, new_draft, expected_common=node.path
            )

            # Render-aware budget check: when render_headings=False the common
            # breadcrumb (node.path) is not rendered, so only the body counts.
            if (
                self._draft_budget_tokens(temp_merged_draft)
                > self.options.ideal_max_tokens
            ):
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

            if child.can_emit_as_single_chunk:
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
                    headings=child_common_headings,
                    headings_token_count=child_common_headings_token_count,
                    body_token_count=child_body_token_count,
                    token_count=child_chunk_token_count,
                )
                if self._draft_budget_tokens(draft) <= budget_token_count:
                    add_packable(draft)
                    continue

            if child.counts.subtree <= budget_token_count:
                flush_current()
                chunks.extend(self._split_section(child))
                continue

            flush_current()
            chunks.extend(self._split_section(child))

        flush_current()
        return self._merge_small_chunks(chunks, parent_headings=node.path)


# Backward-compatible alias: the default ``recursive`` splitter is the exact one.
RecursiveSplitter = ExactRecursiveSplitter

__all__ = [
    "ExactRecursiveSplitter",
    "IncrementalRecursiveSplitter",
    "RecursiveSplitter",
]

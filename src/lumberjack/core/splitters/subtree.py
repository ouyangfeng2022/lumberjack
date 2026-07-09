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


class ExactSubtreeSplitter(ExactCountingMixin, BaseSplitter):
    """Subtree-first splitter (exact counting).

    First attempts to collapse an entire subtree (own body + all descendants)
    into a single chunk when it fits ``ideal_max_tokens`` and contains no
    standalone block.  Otherwise emits one chunk per heading section's direct
    body and recurses into children (no cross-section merging).  Oversized
    section bodies are further split by token budget respecting
    ``block_options`` (standalone isolation, splittable kinds, per-block
    budgets).  Every budget decision fully recounts the rendered candidate
    text — no pre-measure, no incremental arithmetic.

    Registered as ``"subtree"`` (the default) and ``"exact-subtree"``.
    Works with any tokenizer.
    """

    def _split_section(self, section: SectionNode) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children.

        Short-circuit: if the entire subtree (own body + all descendants) fits
        within ``ideal_max_tokens`` and contains no standalone block, collapse
        it into a single chunk.  Otherwise fall through to the per-section
        split path below (unchanged).
        """
        if not (section.blocks or section.children or section.level > 0):
            return []

        body_has_standalone = any(
            b.kind in self.options.standalone_kinds for b in section.blocks
        )
        child_has_standalone = any(
            self._section_has_standalone(child) for child in section.children
        )
        if not body_has_standalone and not child_has_standalone:
            entries = self._entries_from_section(section)
            common = common_heading_path(entry.headings for entry in entries)
            single = self._draft_from_entries(entries, common, origin="section")
            if self._draft_budget_tokens(single) <= self.options.ideal_max_tokens:
                return [single]

        chunks: list[ChunkDraft] = []
        standalone_kinds = self.options.standalone_kinds

        if section.blocks or section.level > 0:
            body_has_standalone = any(
                b.kind in standalone_kinds for b in section.blocks
            )
            body = join_markdown([b.text for b in section.blocks])
            body_tokens = self.tokenizer.count(body, cache=True)
            # SubtreeSplitter emits one chunk per section, so the heading
            # breadcrumb is the only heading context and is constant for this
            # draft — comparing body tokens against the body-only budget is
            # equivalent to comparing the full rendered footprint against
            # ideal_max_tokens.
            body_budget = self._exact_body_budget(section.path)
            should_split_body = body_has_standalone or body_tokens > body_budget
            if should_split_body:
                body_chunks = self._split_section_body(section)
                chunks.extend(
                    self._merge_small_chunks(body_chunks, parent_headings=section.path)
                )
            else:
                entry = Entry(
                    headings=section.path,
                    body=body,
                    start_line=self._min_start_lines(section.blocks),
                    end_line=self._max_end_lines(section.blocks),
                    body_token_count=body_tokens,
                )
                headings_token_count = self._heading_budget_token_count(section.path)
                chunks.append(
                    ChunkDraft(
                        entries=[entry],
                        headings=section.path,
                        headings_token_count=headings_token_count,
                        body_token_count=body_tokens,
                        token_count=headings_token_count + body_tokens,
                    )
                )

        for child in section.children:
            chunks.extend(self._split_section(child))

        return chunks


class IncrementalSubtreeSplitter(IncrementalCountingMixin, BaseSplitter):
    """Subtree-first splitter with the additive incremental estimate path.

    Same subtree-first packing as :class:`ExactSubtreeSplitter` (collapse a
    fitting subtree into one chunk, otherwise per-section), but the subtree is
    pre-measured and budget decisions use a running estimate rather than full
    rendered recounts.

    Registered as ``"incremental-subtree"``.  Works with any tokenizer.
    """

    def _split_section(
        self,
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children.

        Short-circuit: if the pre-measured subtree fits within
        ``ideal_max_tokens`` and ``can_emit_as_single_chunk`` is True, collapse
        it into a single chunk.  Otherwise fall through to the per-section
        split path below (unchanged).
        """
        node = section.node
        if not (node.blocks or section.children or node.level > 0):
            return []

        if section.can_emit_as_single_chunk:
            entries = self._entries_from_section(section)
            common = common_heading_path(entry.headings for entry in entries)
            headings_token_count = self._heading_path_token_count(common)
            chunk_token_count = (
                self._heading_path_token_count(node.path[:-1]) + section.counts.subtree
            )
            single = ChunkDraft(
                entries=entries,
                headings=common,
                headings_token_count=headings_token_count,
                body_token_count=chunk_token_count - headings_token_count,
                token_count=chunk_token_count,
                split_origin="section",
            )
            if self._draft_budget_tokens(single) <= self.options.ideal_max_tokens:
                return [single]

        chunks: list[ChunkDraft] = []

        if node.blocks or node.level > 0:
            body_has_standalone = any(
                b.kind in self.options.standalone_kinds for b in node.blocks
            )
            if (
                body_has_standalone
                or section.counts.body > self.options.ideal_max_tokens
            ):
                body_chunks = self._split_section_body(section)
                chunks.extend(
                    self._merge_small_chunks(body_chunks, parent_headings=node.path)
                )
            else:
                entry = self._entry_from_blocks(
                    node.path,
                    node.blocks,
                    body_token_count=section.counts.body,
                )
                headings_token_count = self._heading_budget_token_count(node.path)
                chunks.append(
                    ChunkDraft(
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


# Backward-compatible alias: the default ``subtree`` splitter is the exact one.
SubtreeSplitter = ExactSubtreeSplitter

__all__ = [
    "ExactSubtreeSplitter",
    "IncrementalSubtreeSplitter",
    "SubtreeSplitter",
]

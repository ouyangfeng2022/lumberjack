from __future__ import annotations

from ..models import (
    ChunkDraft,
    Entry,
    MeasuredSection,
    SectionNode,
)
from ..utils import join_markdown
from .base import BaseSplitter
from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin


class ExactSectionSplitter(ExactCountingMixin, BaseSplitter):
    """Per-heading section splitter without subtree-collapse or tail merging.

    Emits one chunk per heading section's direct body and recurses into
    children.  This variant:

    1. Never collapses an entire subtree into a single chunk (no
       subtree-collapse short-circuit — see :class:`ExactSubtreeSplitter` for
       that topology).
    2. Never calls :meth:`_merge_small_chunks` — tail-fragment merging is
       fully disabled in this variant, regardless of ``merge_below_ratio``.

    Oversized section bodies are still split by token budget respecting
    ``block_options`` (standalone isolation, splittable kinds, per-block
    budgets).  Every budget decision fully recounts the rendered candidate
    text.

    Registered as ``"section"`` (the default) and ``"exact-section"``.
    Works with any tokenizer.
    """

    def _split_section(self, section: SectionNode) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children.

        No subtree-collapse short-circuit and no tail-fragment merging.
        """
        if not (section.blocks or section.children or section.level > 0):
            return []

        chunks: list[ChunkDraft] = []
        standalone_kinds = self.options.standalone_kinds

        if section.blocks or section.level > 0:
            body_has_standalone = any(
                b.kind in standalone_kinds for b in section.blocks
            )
            body = join_markdown([b.text for b in section.blocks])
            body_tokens = self.tokenizer.count(body, cache=True)
            body_budget = self._exact_body_budget(section.path)
            should_split_body = body_has_standalone or body_tokens > body_budget
            if should_split_body:
                body_chunks = self._split_section_body(section)
                chunks.extend(body_chunks)
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


class IncrementalSectionSplitter(IncrementalCountingMixin, BaseSplitter):
    """Per-heading section splitter (incremental estimate) without subtree-collapse or tail merging.

    Same per-section topology as :class:`ExactSectionSplitter`, but uses
    the additive incremental estimate path: the subtree is pre-measured and
    budget decisions use a running estimate rather than full rendered
    recounts.

    No subtree-collapse short-circuit and no tail-fragment merging.

    Registered as ``"incremental-section"``.  Works with any tokenizer.
    """

    def _split_section(
        self,
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children.

        No subtree-collapse short-circuit and no tail-fragment merging.
        """
        node = section.node
        if not (node.blocks or section.children or node.level > 0):
            return []

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
                chunks.extend(body_chunks)
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


# Backward-compatible alias: the default ``section`` splitter is the exact one.
SectionSplitter = ExactSectionSplitter

__all__ = [
    "ExactSectionSplitter",
    "IncrementalSectionSplitter",
    "SectionSplitter",
]

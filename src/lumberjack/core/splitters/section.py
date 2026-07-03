from __future__ import annotations

from ..models import ChunkDraft, Entry, MeasuredSection, SectionNode
from ..utils import join_markdown
from .base import BaseSplitter
from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin


class ExactSectionSplitter(ExactCountingMixin, BaseSplitter):
    """One chunk per heading section (exact counting).

    Each heading-defined section becomes its own chunk.  Oversized section
    bodies are further split by token budget respecting ``block_options``
    (standalone isolation, splittable kinds, per-block budgets).  Every
    budget decision fully recounts the rendered candidate text — no
    pre-measure, no incremental arithmetic.

    Registered as ``"section"`` (the default) and ``"exact-section"``.
    Works with any tokenizer.
    """

    def _split_section(self, section: SectionNode) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children."""
        chunks: list[ChunkDraft] = []
        standalone_kinds = self.options.standalone_kinds

        if section.blocks or section.level > 0:
            body_has_standalone = any(
                b.kind in standalone_kinds for b in section.blocks
            )
            body = join_markdown([b.text for b in section.blocks])
            body_tokens = self.tokenizer.count(body, cache=True)
            # SectionSplitter emits one chunk per section, so the heading
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


class IncrementalSectionSplitter(IncrementalCountingMixin, BaseSplitter):
    """Section topology with the additive incremental estimate path.

    Same one-chunk-per-section packing as :class:`ExactSectionSplitter`, but
    the subtree is pre-measured and budget decisions use a running estimate
    rather than full rendered recounts.

    Registered as ``"incremental-section"``.  Works with any tokenizer.
    """

    def _split_section(
        self,
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children."""
        chunks: list[ChunkDraft] = []
        node = section.node

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


# Backward-compatible alias: the default ``section`` splitter is the exact one.
SectionSplitter = ExactSectionSplitter

__all__ = ["ExactSectionSplitter", "IncrementalSectionSplitter", "SectionSplitter"]

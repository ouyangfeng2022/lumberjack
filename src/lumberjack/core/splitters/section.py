from __future__ import annotations

from ..models import ChunkDraft, HeadingPath, MeasuredSection
from .base import BaseSplitter


class SectionSplitter(BaseSplitter):
    """Split a document into non-overlapping chunks by heading section.

    Each heading-defined section becomes its own chunk.  Oversized
    section bodies are further split by token budget respecting
    ``block_options`` (standalone isolation, splittable kinds, per-block
    budgets).

    Budget semantics with ``render_headings=False``: because every entry in
    a SectionSplitter chunk shares the chunk's common heading path (there are
    no internal relative headings), the heading breadcrumb contributes zero
    tokens to the rendered body.  This class therefore excludes heading
    tokens from the split budget when headings are not rendered, so
    ``max_tokens`` faithfully bounds the rendered ``Chunk.body``.
    """

    def _heading_budget_token_count(self, path: HeadingPath) -> int:
        """Exclude heading tokens from the budget when they are not rendered.

        SectionSplitter chunks never contain internal relative headings, so
        the common heading path is the only heading context and it is omitted
        from ``Chunk.body`` when ``render_headings=False``.
        """
        if not self.options.render_headings:
            return 0
        return self._heading_path_token_count(path)

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


__all__ = ["SectionSplitter"]

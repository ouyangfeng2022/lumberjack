from __future__ import annotations

from .base import _BaseSplitter
from .drafts import _ChunkDraft, _MeasuredSection


class SectionSplitter(_BaseSplitter):
    """Split a document into non-overlapping chunks by heading section.

    Each heading-defined section becomes its own chunk.  Oversized
    section bodies are further split by token budget respecting
    ``block_options`` (standalone isolation, splittable kinds, per-block
    budgets).
    """

    def _split_section(
        self,
        section: _MeasuredSection,
    ) -> list[_ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children."""
        chunks: list[_ChunkDraft] = []
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
                headings_token_count = self._heading_path_token_count(node.path)
                chunks.append(
                    _ChunkDraft(
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

from __future__ import annotations

from typing import Any

from ...models import ChunkDraft


class SectionTopologyMixin:
    """Strict per-section traversal, independent of the counting strategy."""

    def _direct_body_drafts(self, section: Any) -> list[ChunkDraft]:
        raise NotImplementedError

    def _split_section(self, section: Any) -> list[ChunkDraft]:
        node = getattr(section, "node", section)
        children = section.children
        if not (node.blocks or children or node.level > 0):
            return []
        chunks = self._direct_body_drafts(section)
        for child in children:
            chunks.extend(self._split_section(child))
        return chunks

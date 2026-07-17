from __future__ import annotations

from typing import Any

from ...models import ChunkDraft
from ..base import BaseSplitter


class SubtreeTopologyMixin(BaseSplitter):
    """Collapse a fitting subtree, otherwise split direct bodies then recurse."""

    options: Any

    def _direct_body_drafts(self, section: Any) -> list[ChunkDraft]:
        raise NotImplementedError

    def _single_subtree_draft(self, section: Any) -> ChunkDraft | None:
        raise NotImplementedError

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        raise NotImplementedError

    def _split_section(self, section: Any) -> list[ChunkDraft]:
        node = getattr(section, "node", section)
        children = section.children
        if not (node.blocks or children or node.level > 0):
            return []
        single = self._single_subtree_draft(section)
        if (
            single is not None
            and self._draft_budget_tokens(single) <= self.options.ideal_max_tokens
        ):
            return [single]
        chunks = self._merge_small_chunks(
            self._direct_body_drafts(section), parent_headings=node.path
        )
        for child in children:
            chunks.extend(self._split_section(child))
        return chunks

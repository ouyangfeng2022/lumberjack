from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lumberjack.block import BlockOption

from ...models import ChunkDraft
from ...protocols import TokenizerProtocol
from ..base import BaseSplitter


class SubtreeTopologyMixin(BaseSplitter):
    """Collapse a fitting subtree, otherwise split direct bodies then recurse."""

    def __init__(
        self,
        tokenizer: TokenizerProtocol,
        *,
        max_tokens: int = 1200,
        ideal_max_tokens_ratio: float = 0.8,
        merge_below_ratio: float = 0.125,
        skip_empty_sections: bool = True,
        render_headings: bool = True,
        max_heading_level: int | None = None,
        block_options: Iterable[BlockOption] | None = None,
    ) -> None:
        super().__init__(
            tokenizer,
            max_tokens=max_tokens,
            ideal_max_tokens_ratio=ideal_max_tokens_ratio,
            skip_empty_sections=skip_empty_sections,
            render_headings=render_headings,
            max_heading_level=max_heading_level,
            block_options=block_options,
            _merge_below_ratio=merge_below_ratio,
        )

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
            and self._draft_budget_tokens(single) <= self.ideal_max_tokens
        ):
            return [single]
        chunks = self._merge_small_chunks(
            self._direct_body_drafts(section), parent_headings=node.path
        )
        for child in children:
            chunks.extend(self._split_section(child))
        return chunks

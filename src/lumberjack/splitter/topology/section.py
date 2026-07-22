from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lumberjack.block import BlockOption

from ...models import ChunkDraft
from ...protocols import TokenizerProtocol
from ..base import BaseSplitter


class SectionTopologyMixin(BaseSplitter):
    """Strict per-section traversal, independent of the counting strategy."""

    def __init__(
        self,
        tokenizer: TokenizerProtocol,
        *,
        max_tokens: int = 1200,
        ideal_max_tokens_ratio: float = 0.8,
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
            _merge_below_ratio=0.0,
        )

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

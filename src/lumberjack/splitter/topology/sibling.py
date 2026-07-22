from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lumberjack.block import BlockOption

from ...models import ChunkDraft, HeadingPath
from ...protocols import TokenizerProtocol
from ..base import BaseSplitter


class SiblingTopologyMixin(BaseSplitter):
    """Greedily pack a section body and fitting sibling subtrees."""

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

    def _single_subtree_draft(self, section: Any) -> ChunkDraft | None:
        raise NotImplementedError

    def _packable_body_draft(self, section: Any) -> ChunkDraft | None:
        raise NotImplementedError

    def _direct_body_drafts(self, section: Any) -> list[ChunkDraft]:
        raise NotImplementedError

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        raise NotImplementedError

    def _merge_drafts(
        self,
        left_draft: ChunkDraft,
        right_draft: ChunkDraft,
        *,
        expected_common: HeadingPath | None = None,
    ) -> ChunkDraft:
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
        if not children:
            return self._merge_small_chunks(
                self._direct_body_drafts(section),
                parent_headings=node.path,
            )
        chunks: list[ChunkDraft] = []
        current: ChunkDraft | None = None

        def flush() -> None:
            nonlocal current
            if current is not None:
                chunks.append(current)
                current = None

        def add(draft: ChunkDraft) -> None:
            nonlocal current
            if current is None:
                current = draft
                return
            merged = self._merge_drafts(current, draft, expected_common=node.path)
            if self._draft_budget_tokens(merged) <= self.ideal_max_tokens:
                current = merged
            else:
                chunks.append(current)
                current = draft

        body = self._packable_body_draft(section)
        if body is not None:
            add(body)
        elif node.blocks:
            flush()
            chunks.extend(self._direct_body_drafts(section))
        for child in children:
            draft = self._single_subtree_draft(child)
            if (
                draft is not None
                and self._draft_budget_tokens(draft) <= self.ideal_max_tokens
            ):
                add(draft)
            else:
                flush()
                chunks.extend(self._split_section(child))
        flush()
        return self._merge_small_chunks(chunks, parent_headings=node.path)

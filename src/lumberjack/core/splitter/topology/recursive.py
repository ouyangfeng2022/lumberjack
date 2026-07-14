from __future__ import annotations

from typing import Any, cast

from ...models import ChunkDraft
from ..base import BaseSplitter


class RecursiveTopologyMixin:
    """Recursive sibling packing, independent of exact/incremental counting."""

    options: Any

    def _single_subtree_draft(self, section: Any) -> ChunkDraft | None:
        raise NotImplementedError

    def _packable_body_draft(self, section: Any) -> ChunkDraft | None:
        raise NotImplementedError

    def _direct_body_drafts(self, section: Any) -> list[ChunkDraft]:
        raise NotImplementedError

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        raise NotImplementedError

    def _merge_drafts(
        self, left: ChunkDraft, right: ChunkDraft, *, expected_common: Any = None
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
            and self._draft_budget_tokens(single) <= self.options.ideal_max_tokens
        ):
            return [single]
        if not children:
            return BaseSplitter._merge_small_chunks(
                cast(BaseSplitter, self),
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
            if self._draft_budget_tokens(merged) <= self.options.ideal_max_tokens:
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
                and self._draft_budget_tokens(draft) <= self.options.ideal_max_tokens
            ):
                add(draft)
            else:
                flush()
                chunks.extend(self._split_section(child))
        flush()
        return BaseSplitter._merge_small_chunks(
            cast(BaseSplitter, self), chunks, parent_headings=node.path
        )

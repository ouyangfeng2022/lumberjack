"""Flat record-aware splitting without synthetic heading semantics."""

from __future__ import annotations

from collections.abc import Iterable

from ..block import BlockOption
from ..models import ChunkDraft, DocTree, Entry, render_draft_body
from ..protocols import TokenizerProtocol
from .base import BaseSplitter


class RecordSplitter(BaseSplitter):
    """Pack complete root-level records while preserving their input order.

    A record is atomic: when it alone exceeds the budget, the emitted draft is
    marked ``protected`` instead of splitting its text or claiming compliance.
    """

    supported_topologies = frozenset({"records"})

    def __init__(
        self,
        tokenizer: TokenizerProtocol,
        *,
        record_kinds: Iterable[str] = ("record", "tabular_row"),
        max_tokens: int = 1200,
        ideal_max_tokens_ratio: float = 0.8,
        skip_empty_sections: bool = True,
        block_options: Iterable[BlockOption] | None = None,
    ) -> None:
        super().__init__(
            tokenizer,
            max_tokens=max_tokens,
            ideal_max_tokens_ratio=ideal_max_tokens_ratio,
            skip_empty_sections=skip_empty_sections,
            heading_sensitive=False,
            block_options=block_options,
        )
        self.record_kinds = frozenset(kind.strip().lower() for kind in record_kinds)
        if not self.record_kinds or "" in self.record_kinds:
            raise ValueError("record_kinds must contain non-empty block kinds")

    def split(self, document: DocTree) -> list[ChunkDraft]:
        self._validate_document_topology(document)
        invalid_kinds = {
            str(block.kind).lower()
            for block in document.root.blocks
            if str(block.kind).lower() not in self.record_kinds
        }
        if invalid_kinds:
            kinds = ", ".join(sorted(invalid_kinds))
            raise ValueError(
                f"record document contains non-record block kinds: {kinds}"
            )

        drafts: list[ChunkDraft] = []
        current: list[Entry] = []

        def emit(entries: list[Entry], *, protected: bool = False) -> None:
            if not entries:
                return
            body = render_draft_body(entries, ())
            body_tokens = self.tokenizer.count(body, cache=True)
            drafts.append(
                ChunkDraft(
                    entries=list(entries),
                    headings=(),
                    own_heading=None,
                    headings_token_count=0,
                    body_token_count=body_tokens,
                    token_count=self._chunk_token_count(0, body_tokens),
                    chunk_type="record",
                    counting_mode="exact",
                    protected=protected,
                )
            )

        for block in document.root.blocks:
            entry = Entry(
                headings=(),
                body=block.text,
                start_line=block.start_line,
                end_line=block.end_line,
                body_token_count=self.tokenizer.count(block.text, cache=True),
                source_locations=block.source_locations,
            )
            candidate = [*current, entry]
            candidate_body = render_draft_body(candidate, ())
            candidate_tokens = self._chunk_token_count(
                0, self.tokenizer.count(candidate_body, cache=True)
            )
            if current and candidate_tokens > self.ideal_max_tokens:
                emit(current)
                current = [entry]
                candidate_tokens = self._chunk_token_count(
                    0, self.tokenizer.count(block.text, cache=True)
                )
            if not current:
                current = [entry]
            elif candidate_tokens <= self.ideal_max_tokens:
                current = candidate
            if len(current) == 1 and candidate_tokens > self.max_tokens:
                emit(current, protected=True)
                current = []

        emit(current)
        return drafts


__all__ = ["RecordSplitter"]

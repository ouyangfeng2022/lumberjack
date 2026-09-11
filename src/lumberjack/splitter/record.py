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

    Counting is exact but cache-free: like the exact splitters, identical
    strings within one split (the emitted body re-counted after packing) are
    deduplicated by a per-split memo instead of the tokenizer cache.  The
    part-sum join bound assumes the join-counting property documented on
    ``TokenizerProtocol``.
    """

    use_tokenizer_cache = False

    supported_topologies = frozenset({"records"})

    _memoized_count = BaseSplitter._memo_count

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
        self._count_memo = {}
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
            body_tokens = self._memo_count(body)
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

        def flush(*, protected: bool = False) -> None:
            """Emit the running group and reset it together with its count."""
            nonlocal current, current_tokens
            if not current:
                return
            emit(current, protected=protected)
            current = []
            current_tokens = 0

        current_tokens = 0
        for block in document.root.blocks:
            entry_tokens = self._memo_count(block.text)
            entry = Entry(
                headings=(),
                body=block.text,
                start_line=block.start_line,
                end_line=block.end_line,
                body_token_count=entry_tokens,
                source_locations=block.source_locations,
            )
            single_tokens = self._chunk_token_count(0, entry_tokens)
            if current and current_tokens + entry_tokens - 2 > self.ideal_max_tokens:
                # Sound rejection: the candidate renders both groups as
                # contiguous blocks joined by one separator, so its count is
                # at least the current body + entry - 2 for tokenizers
                # honoring the join-counting property documented on
                # TokenizerProtocol — encoding it would be wasted work.
                flush()
            if current:
                candidate = [*current, entry]
                candidate_tokens = self._chunk_token_count(
                    0, self._memo_count(render_draft_body(candidate, ()))
                )
                if candidate_tokens <= self.ideal_max_tokens:
                    current = candidate
                    current_tokens = candidate_tokens
                    continue
                flush()
            current = [entry]
            current_tokens = single_tokens
            if single_tokens > self.max_tokens:
                # A lone record that not even max_tokens accommodates is
                # reported as protected, never split or faked into compliance.
                flush(protected=True)

        flush()
        return drafts


__all__ = ["RecordSplitter"]

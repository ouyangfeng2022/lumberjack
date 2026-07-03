from __future__ import annotations

from ..block import BlockSplitter
from ..models import (
    Chunk,
    ChunkDraft,
    DocumentAST,
    Entry,
    HeadingPath,
    MarkdownBlock,
    SplitOptions,
    ancestor_heading_path,
    common_heading_path,
    render_heading_path,
)
from ..protocols import SplitterProtocol, TokenizerProtocol
from ..tokenizers import ApproxCharTokenizer
from ..utils import join_markdown

SEPARATOR = "\n\n"


class BaseSplitter(SplitterProtocol):
    """Shared state and helpers for splitter strategies.

    Concrete splitters combine this base with one counting-strategy mixin:

    * :class:`ExactCountingMixin` — full recount at every budget decision
      (walks the raw ``SectionNode`` tree, no pre-measure).
    * :class:`IncrementalCountingMixin` — additive running estimate +
      8-char separator-delta window (walks a pre-measured
      :class:`MeasuredSection` tree).

    Each mixin owns :meth:`split`, :meth:`_draft_budget_tokens`,
    :meth:`_merge_drafts`, :meth:`_finalize_estimate`, body splitting, and
    section entry rendering.  This class holds only the pieces that are
    independent of both topology and counting strategy: tokenizer/options
    wiring, rendering helpers, finalization shell, and small-chunk merging.
    """

    def __init__(
        self,
        tokenizer: TokenizerProtocol | None = None,
        options: SplitOptions | None = None,
    ):
        self.tokenizer = tokenizer or ApproxCharTokenizer()
        self.options = options or SplitOptions()
        self._validate_options()
        self._block_splitter = BlockSplitter(self.tokenizer, self.options)

    def split(self, document: DocumentAST) -> list[Chunk]:  # pragma: no cover
        raise NotImplementedError(
            "split() is provided by a counting-strategy mixin "
            "(ExactCountingMixin or IncrementalCountingMixin)"
        )

    # ------------------------------------------------------------------
    # Rendering helpers (strategy-agnostic)
    # ------------------------------------------------------------------

    def _heading_path_token_count(self, path: HeadingPath) -> int:
        if not path:
            return 0
        tokens = 0
        for level, title in path:
            if title:
                tokens = tokens + self.tokenizer.count(
                    "#" * level + " " + title + SEPARATOR, cache=True
                )
        return tokens

    def _render_body(
        self,
        entries: list[Entry],
        *,
        ancestor_headings: HeadingPath,
    ) -> str:
        """Render entries into Markdown body content."""
        if not entries:
            return ""

        parts: list[str] = []
        if ancestor_headings and self.options.render_headings:
            parts.append(render_heading_path(ancestor_headings))

        previous_headings = ancestor_headings
        for entry in entries:
            shared_headings = common_heading_path((previous_headings, entry.headings))
            if len(shared_headings) < len(ancestor_headings):
                shared_headings = ancestor_headings
            relative_headings = entry.headings[len(shared_headings) :]

            entry_parts: list[str] = []
            if relative_headings:
                entry_parts.append(render_heading_path(relative_headings))
            if entry.body:
                entry_parts.append(entry.body)
            rendered = join_markdown(entry_parts)
            if rendered:
                parts.append(rendered)
            previous_headings = entry.headings

        return join_markdown(parts)

    def _rendered_token_count(
        self,
        entries: list[Entry],
        *,
        ancestor_headings: HeadingPath | None = None,
    ) -> int:
        """Full token count of the rendered body for *entries*."""
        if ancestor_headings is None:
            ancestor_headings = ancestor_heading_path(
                entry.headings for entry in entries
            )
        return self.tokenizer.count(
            self._render_body(entries, ancestor_headings=ancestor_headings), cache=True
        )

    # ------------------------------------------------------------------
    # Budget hooks (overridden by topology classes if needed)
    # ------------------------------------------------------------------

    def _heading_budget_token_count(self, path: HeadingPath) -> int:
        """Full heading token count for a draft's internal common prefix."""
        return self._heading_path_token_count(path)

    # ------------------------------------------------------------------
    # Strategy hooks (provided by the counting-strategy mixin)
    # ------------------------------------------------------------------

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        """Rendered footprint of a draft, used for budget decisions.

        Provided by :class:`ExactCountingMixin` (full recount) or
        :class:`IncrementalCountingMixin` (running estimate).
        """
        raise NotImplementedError

    def _merge_drafts(
        self,
        left_draft: ChunkDraft,
        right_draft: ChunkDraft,
        *,
        expected_common: HeadingPath | None = None,
    ) -> ChunkDraft:
        """Merge two drafts; provided by the counting-strategy mixin."""
        raise NotImplementedError

    def _finalize_estimate(
        self,
        chunk: ChunkDraft,
        headings: HeadingPath,
        token_count: int,
    ) -> int:
        """Estimated token count carried onto the final Chunk; mixin-provided."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Topology hook (overridden by concrete splitters)
    # ------------------------------------------------------------------

    def _split_section(self, section) -> list[ChunkDraft]:
        """Topology + counting-strategy specific section splitter."""
        raise NotImplementedError

    def _post_process_drafts(self, drafts: list[ChunkDraft]) -> list[ChunkDraft]:
        return drafts

    def _validate_options(self) -> None:
        if self.options.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")
        if not 0 < self.options.ideal_max_tokens_ratio <= 1:
            raise ValueError(
                "ideal_max_tokens_ratio must be greater than 0 and at most 1"
            )
        if (
            self.options.merge_below_tokens is None
            or self.options.merge_below_tokens < 0
        ):
            # None or negative means merging is disabled; nothing else to validate.
            pass
        elif self.options.merge_below_tokens >= self.options.max_tokens:
            raise ValueError("merge_below_tokens must be smaller than max_tokens")
        for kind, cfg in self.options.block_options.items():
            if cfg.max_tokens is not None and cfg.max_tokens <= 0:
                raise ValueError(
                    f"block_options[{kind!r}].max_tokens must be positive, got {cfg.max_tokens}"
                )

    # ------------------------------------------------------------------
    # Finalize (shared shell; estimate delegated to the strategy mixin)
    # ------------------------------------------------------------------

    def _finalize_chunks(
        self,
        chunks: list[ChunkDraft],
        document: DocumentAST,
    ) -> list[Chunk]:
        """Convert chunk drafts into final ``Chunk`` objects with rendered body and metadata."""
        finalized: list[Chunk] = []
        doc_path = document.metadata.get("path")
        document_path = str(doc_path) if doc_path is not None else None
        index = 0
        for chunk in chunks:
            headings = ancestor_heading_path(entry.headings for entry in chunk.entries)
            body = self._render_body(chunk.entries, ancestor_headings=headings)
            if not body:
                continue
            if self.options.skip_empty_sections and not any(
                entry.body.strip() for entry in chunk.entries
            ):
                continue
            index += 1
            # token_count: always a full recount of the rendered body.
            token_count = self.tokenizer.count(body, cache=True)
            estimated = self._finalize_estimate(chunk, headings, token_count)
            section_level = max(
                (level for entry in chunk.entries for level, _title in entry.headings),
                default=0,
            )
            finalized.append(
                Chunk(
                    chunk_id=f"chunk-{index:04d}",
                    chunk_type=chunk.chunk_type,
                    body=body,
                    token_count=token_count,
                    estimated_token_count=estimated,
                    headings=headings,
                    section_level=section_level,
                    document_title=document.title,
                    document_path=document_path,
                    start_line=min(
                        (
                            entry.start_line
                            for entry in chunk.entries
                            if entry.start_line is not None
                        ),
                        default=None,
                    ),
                    end_line=max(
                        (
                            entry.end_line
                            for entry in chunk.entries
                            if entry.end_line is not None
                        ),
                        default=None,
                    ),
                )
            )
        return finalized

    def _entry_from_blocks(
        self,
        headings: HeadingPath,
        blocks: list[MarkdownBlock],
        *,
        body_token_count: int,
    ) -> Entry:
        body = join_markdown([block.text for block in blocks])
        start_lines = [b.start_line for b in blocks if b.start_line is not None]
        end_lines = [b.end_line for b in blocks if b.end_line is not None]

        return Entry(
            headings=headings,
            body=body,
            start_line=min(start_lines) if start_lines else None,
            end_line=max(end_lines) if end_lines else None,
            body_token_count=body_token_count,
        )

    def _entry_group_tail(self, entries: list[Entry]) -> str:
        if not entries:
            return ""
        last = entries[-1]
        if last.body:
            return last.body
        if last.headings:
            level, title = last.headings[-1]
            return "#" * level + " " + title
        return ""

    def _merge_small_chunks(
        self,
        chunks: list[ChunkDraft],
        *,
        parent_headings: HeadingPath | None = None,
    ) -> list[ChunkDraft]:
        """Merge adjacent same-parent chunks below *merge_below_tokens*, bottom-up."""
        merge_below = self.options.merge_below_tokens
        if merge_below is None or merge_below < 0:
            return chunks
        if not chunks:
            return chunks

        merged: list[ChunkDraft] = list(chunks)
        i = len(merged) - 1
        while i > 0:
            current = merged[i]
            previous = merged[i - 1]
            can_merge = (
                (parent_headings is None or previous.headings == parent_headings)
                and previous.headings == current.headings
                and current.entries
            )
            if (
                can_merge
                and self._draft_budget_tokens(current) < merge_below
                and previous.chunk_type == "paragraph"
                and current.chunk_type == "paragraph"
            ):
                merged_draft = self._merge_drafts(previous, current)
                # Compare the rendered footprint against max_tokens.  Because
                # can_merge guarantees previous.headings == current.headings,
                # the merged common prefix is that shared path.
                if self._draft_budget_tokens(merged_draft) <= self.options.max_tokens:
                    merged[i - 1] = merged_draft
                    del merged[i]
            i -= 1
        return merged

    @staticmethod
    def _min_start(entries: list[Entry]) -> int | None:
        vals = [e.start_line for e in entries if e.start_line is not None]
        return min(vals) if vals else None

    @staticmethod
    def _max_end(entries: list[Entry]) -> int | None:
        vals = [e.end_line for e in entries if e.end_line is not None]
        return max(vals) if vals else None

    @staticmethod
    def _min_start_lines(blocks: list[MarkdownBlock]) -> int | None:
        vals = [b.start_line for b in blocks if b.start_line is not None]
        return min(vals) if vals else None

    @staticmethod
    def _max_end_lines(blocks: list[MarkdownBlock]) -> int | None:
        vals = [b.end_line for b in blocks if b.end_line is not None]
        return max(vals) if vals else None


__all__ = ["BaseSplitter"]

from __future__ import annotations

from ..block import BlockSplitter
from ..models import (
    Chunk,
    DocumentAST,
    HeadingPath,
    MarkdownBlock,
    SectionNode,
    SplitOptions,
)
from ..protocols import SplitterProtocol, TokenizerProtocol
from ..tokenizers import SimpleCharTokenizer
from ..utils import join_markdown
from .drafts import ChunkDraft, Entry, MeasuredSection, SectionTokenCounts
from .headings import common_heading_path, render_heading_path

SEPARATOR = "\n\n"
SEPARATOR_DELTA_WINDOW_CHARS = 8


class _BaseSplitter(SplitterProtocol):
    """Shared state and helpers for splitter strategies."""

    def __init__(
        self,
        tokenizer: TokenizerProtocol | None = None,
        options: SplitOptions | None = None,
    ):
        self.tokenizer = tokenizer or SimpleCharTokenizer()
        self.options = options or SplitOptions()
        self._validate_options()
        self._block_splitter = BlockSplitter(self.tokenizer, self.options)

    def split(self, document: DocumentAST) -> list[Chunk]:
        measured_root = self._measure_section(document.root)
        drafts = self._split_section(measured_root)
        drafts = self._post_process_drafts(drafts)
        return self._finalize_chunks(drafts, document)

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

    def _split_section(self, section: MeasuredSection) -> list[ChunkDraft]:
        raise NotImplementedError

    def _post_process_drafts(self, drafts: list[ChunkDraft]) -> list[ChunkDraft]:
        return drafts

    def _separator_delta_after(self, text: str) -> int:
        """Estimate the token delta caused by appending the Markdown separator."""
        if not text:
            return 0
        tail = text.rstrip("\n")[-SEPARATOR_DELTA_WINDOW_CHARS:]
        return self.tokenizer.count(
            f"{tail}{SEPARATOR}", cache=True
        ) - self.tokenizer.count(tail, cache=True)

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

    def _measure_section(self, section: SectionNode) -> MeasuredSection:
        """Return a measured wrapper for *section* and all descendants."""
        children = tuple(self._measure_section(child) for child in section.children)

        # 1. Count body tokens
        body_token_count = 0
        for idx, block in enumerate(section.blocks):
            if idx == len(section.blocks) - 1:
                body_token_count += self.tokenizer.count(block.text, cache=True)
            else:
                body_token_count += self.tokenizer.count(
                    block.text + SEPARATOR, cache=True
                )

        # 2. Count title tokens
        if section.level > 0:
            title_token_count = self.tokenizer.count(
                "#" * section.level + " " + section.title + SEPARATOR, cache=True
            )
        else:
            title_token_count = 0

        # 3. Count subtree tokens
        subtree_token_count = title_token_count + body_token_count
        previous_tail = section.blocks[-1].text if section.blocks else ""
        prev_child: MeasuredSection | None = None
        for child in children:
            # When the previous child is a leaf section with no body
            # blocks, its heading's trailing \n\n (from
            # heading_path_token_count) already serves as the separator
            # to this child.  Adding sep_delta would double-count it.
            if previous_tail and not (
                prev_child is not None
                and not prev_child.node.blocks
                and not prev_child.children
            ):
                subtree_token_count += self._separator_delta_after(previous_tail)
            subtree_token_count += child.counts.subtree
            previous_tail = child.tail_text
            prev_child = child

        if previous_tail:
            tail_text = previous_tail
        elif section.level > 0:
            tail_text = "#" * section.level + " " + section.title
        else:
            tail_text = ""

        body_has_standalone = any(
            block.kind in self.options.standalone_kinds for block in section.blocks
        )
        can_emit_as_single_chunk = not body_has_standalone and all(
            child.can_emit_as_single_chunk for child in children
        )
        return MeasuredSection(
            node=section,
            counts=SectionTokenCounts(
                title=title_token_count,
                body=body_token_count,
                subtree=subtree_token_count,
            ),
            tail_text=tail_text,
            can_emit_as_single_chunk=can_emit_as_single_chunk,
            children=children,
        )

    def _split_section_body(
        self,
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Split a section's own blocks into fragments, then into chunk drafts."""
        node = section.node
        headings = node.path
        blocks = node.blocks
        max_tokens = self.options.ideal_max_tokens
        standalone_kinds = self.options.standalone_kinds

        prefix_tokens = (
            self._heading_path_token_count(headings) if node.level > 0 else 0
        )
        if prefix_tokens >= max_tokens or not blocks:
            entry = self._entry_from_blocks(
                headings, blocks, body_token_count=section.counts.body
            )
            return [
                ChunkDraft(
                    entries=[entry],
                    headings=node.path,
                    headings_token_count=prefix_tokens,
                    body_token_count=entry.body_token_count,
                    token_count=prefix_tokens + entry.body_token_count,
                    split_origin="fragment",
                )
            ]

        chunks: list[ChunkDraft] = []
        current_parts: list[str] = []
        current_joined = ""
        current_body_tokens = 0
        current_start_line: int | None = None
        current_end_line: int | None = None

        budget = max(0, max_tokens - prefix_tokens) if prefix_tokens > 0 else max_tokens

        def draft_current() -> ChunkDraft:
            entry = Entry(
                headings=headings,
                body=join_markdown(current_parts),
                start_line=current_start_line,
                end_line=current_end_line,
                body_token_count=current_body_tokens,
            )
            token_count = prefix_tokens + current_body_tokens
            return ChunkDraft(
                entries=[entry],
                headings=headings,
                headings_token_count=prefix_tokens,
                body_token_count=token_count - prefix_tokens,
                token_count=token_count,
                split_origin="fragment",
            )

        for block in blocks:
            if standalone_kinds and block.kind in standalone_kinds:
                if current_parts:
                    chunks.append(draft_current())
                    current_parts = []
                    current_joined = ""
                    current_body_tokens = 0
                    current_start_line = None
                    current_end_line = None

                block_tokens = self.tokenizer.count(block.text, cache=True)
                # This chunk will only contain this block and headings.
                block_pieces = self._block_splitter.split_oversized_block(
                    block,
                    default_budget=budget,
                )
                if block_pieces is not None:
                    for piece in block_pieces:
                        piece_tokens = self.tokenizer.count(piece)
                        entry = Entry(
                            headings=headings,
                            body=piece,
                            start_line=block.start_line,
                            end_line=block.end_line,
                            body_token_count=piece_tokens,
                        )
                        chunks.append(
                            ChunkDraft(
                                entries=[entry],
                                headings=headings,
                                headings_token_count=prefix_tokens,
                                body_token_count=piece_tokens,
                                token_count=prefix_tokens + piece_tokens,
                                split_origin="text_piece",
                                chunk_type=block.kind,
                            )
                        )
                else:
                    entry = Entry(
                        headings=headings,
                        body=block.text,
                        start_line=block.start_line,
                        end_line=block.end_line,
                        body_token_count=block_tokens,
                    )

                    chunks.append(
                        ChunkDraft(
                            entries=[entry],
                            headings=headings,
                            headings_token_count=prefix_tokens,
                            body_token_count=block_tokens,
                            token_count=prefix_tokens + block_tokens,
                            split_origin="fragment",
                            chunk_type=block.kind,
                        )
                    )
                continue

            block_tokens = self.tokenizer.count(block.text, cache=True)
            candidate_body_tokens = (
                current_body_tokens
                - self.tokenizer.count(current_parts[-1], cache=True)
                + self.tokenizer.count(f"{current_parts[-1]}{SEPARATOR}", cache=True)
                + block_tokens
                if current_parts
                else block_tokens
            )
            candidate_total = prefix_tokens + candidate_body_tokens
            if current_parts and candidate_total > max_tokens:
                chunks.append(draft_current())
                current_parts = []
                current_joined = ""
                current_body_tokens = 0
                current_start_line = None
                current_end_line = None
                candidate_body_tokens = block_tokens

            single_block_total = prefix_tokens + block_tokens
            if single_block_total <= max_tokens:
                current_parts.append(block.text)
                candidate_text = (
                    current_joined + SEPARATOR + block.text
                    if current_joined
                    else block.text
                )
                current_body_tokens = candidate_body_tokens
                current_joined = candidate_text
                if block.start_line is not None and (
                    current_start_line is None or block.start_line < current_start_line
                ):
                    current_start_line = block.start_line
                if block.end_line is not None and (
                    current_end_line is None or block.end_line > current_end_line
                ):
                    current_end_line = block.end_line
                continue
            # TODO: chunk.tokens should not exceed the max_tokens.
            # Special chunks can be split using a smaller tokens.
            block_pieces = self._block_splitter.split_oversized_block(
                block,
                default_budget=budget,
            )
            if block_pieces is None:
                entry = Entry(
                    headings=headings,
                    body=block.text,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    body_token_count=block_tokens,
                )
                chunks.append(
                    ChunkDraft(
                        entries=[entry],
                        headings=headings,
                        headings_token_count=prefix_tokens,
                        body_token_count=block_tokens,
                        token_count=prefix_tokens + block_tokens,
                        split_origin="fragment",
                        chunk_type="paragraph",
                    )
                )
                current_parts = []
                current_joined = ""
                current_body_tokens = 0
                current_start_line = None
                current_end_line = None
                continue

            for piece in block_pieces:
                piece_tokens = self.tokenizer.count(piece)
                entry = Entry(
                    headings=headings,
                    body=piece,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    body_token_count=piece_tokens,
                )
                chunks.append(
                    ChunkDraft(
                        entries=[entry],
                        headings=headings,
                        headings_token_count=prefix_tokens,
                        body_token_count=piece_tokens,
                        token_count=prefix_tokens + piece_tokens,
                        split_origin="text_piece",
                        chunk_type="paragraph",
                    )
                )

        if current_parts:
            rendered = join_markdown(current_parts)
            if rendered:
                chunks.append(draft_current())

        return chunks

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
            headings = common_heading_path(entry.headings for entry in chunk.entries)
            body = self._render_body(chunk.entries, common_headings=headings)
            if not body:
                continue
            if self.options.skip_empty_sections and not any(
                entry.body.strip() for entry in chunk.entries
            ):
                continue
            index += 1
            token_count = self.tokenizer.count(body)
            estimated = self._estimated_token_count(chunk, headings)
            finalized.append(
                Chunk(
                    chunk_id=f"chunk-{index:04d}",
                    chunk_type=chunk.chunk_type,
                    body=body,
                    token_count=token_count,
                    estimated_token_count=estimated,
                    headings=headings,
                    section_level=headings[-1][0] if headings else 0,
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

    def _merge_drafts(
        self,
        left_draft: ChunkDraft,
        right_draft: ChunkDraft,
    ) -> ChunkDraft:
        left_headings = left_draft.headings
        right_headings = right_draft.headings

        common_headings = common_heading_path([left_headings, right_headings])
        headings_token_count = self._heading_path_token_count(common_headings)

        left_body_token_count = left_draft.token_count - headings_token_count
        right_body_token_count = right_draft.token_count - headings_token_count

        body_token_count = left_body_token_count + right_body_token_count

        # Account for the \n\n separator between the last left entry and
        # the first right entry introduced by join_markdown during rendering.
        #
        # When the last left entry has empty body, its heading's trailing
        # \n\n (from heading_path_token_count in _measure_section) already
        # serves as the separator to the next entry.  Adding sep_delta here
        # would double-count that separator.
        if left_draft.entries and right_draft.entries:
            last_left = left_draft.entries[-1]
            if last_left.body:
                left_tail = self._entry_group_tail(left_draft.entries)
                body_token_count += self._separator_delta_after(left_tail)

        return ChunkDraft(
            entries=[*left_draft.entries, *right_draft.entries],
            headings=common_headings,
            headings_token_count=headings_token_count,
            body_token_count=body_token_count,
            token_count=headings_token_count + body_token_count,
            split_origin="merge",
            chunk_type=left_draft.chunk_type,
        )

    def _render_body(
        self,
        entries: list[Entry],
        *,
        common_headings: HeadingPath,
    ) -> str:
        """Render entries into Markdown body content.

        When ``SplitOptions.render_headings`` is True, the chunk's common
        heading breadcrumb is rendered once at the top.  When False, the
        common prefix (already available as ``chunk.headings`` metadata) is
        omitted from the body.  In both modes each entry's own relative
        headings are rendered and de-duplicated against the previous entry
        so the chunk's internal structure is preserved.
        """
        if not entries:
            return ""

        parts: list[str] = []
        # The common prefix breadcrumb is only emitted when headings are
        # rendered; when disabled, it is already available as
        # ``chunk.headings`` metadata.
        if self.options.render_headings and common_headings:
            parts.append(render_heading_path(common_headings))

        previous_headings = common_headings
        prefix_len = len(common_headings)
        for entry in entries:
            shared_headings = common_heading_path((previous_headings, entry.headings))
            if len(shared_headings) < prefix_len:
                shared_headings = common_headings
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

    def _estimated_token_count(
        self,
        chunk: ChunkDraft,
        headings: HeadingPath,
    ) -> int:
        """Return the token estimate aligned with the actually rendered body.

        ``chunk.token_count`` is the draft estimate, which counts every
        heading in every entry *with* a trailing ``\\n\\n`` separator.  The
        rendered body differs from this estimate in two ways, and the
        estimate is adjusted here so ``estimated_token_count`` always equals
        the true ``tokenizer.count(body)``:

        - The common prefix breadcrumb is only emitted when
          ``render_headings`` is True.  When disabled, drop its tokens.
        - The estimate attaches a trailing ``\\n\\n`` to *every* heading,
          but a heading at the very end of the rendered body (i.e. the last
          entry has empty body) is never followed by anything, so that
          phantom separator must be removed.  The trailing heading may be
          the common prefix itself (when the whole body is a breadcrumb) or
          the last entry's relative heading.
        """
        estimated = chunk.token_count

        # 1. Common prefix tokens (with its trailing separator) are only in the
        #    body when headings are rendered.  Skip the lookup entirely when
        #    the prefix is actually emitted.
        if headings and not self.options.render_headings:
            estimated -= self._heading_path_token_count(headings)

        # 2. Phantom trailing separator after the last rendered unit when the
        #    chunk ends on a heading rather than body text.
        if chunk.entries:
            last = chunk.entries[-1]
            if not last.body.strip():
                trailing_heading = self._rendered_trailing_heading(
                    chunk.entries, headings
                )
                if trailing_heading:
                    estimated -= self._trailing_separator_delta(trailing_heading)

        return estimated

    def _rendered_trailing_heading(
        self,
        entries: list[Entry],
        common_headings: HeadingPath,
    ) -> str:
        """Return the heading string the renderer emits at the very tail.

        Mirrors the logic in :meth:`_render_body` for the last entry: the
        rendered tail is the last entry's relative heading path (relative to
        the running shared-prefix tracked across entries).  When the last
        entry has a non-empty body there is no trailing heading; the caller
        only invokes this when the last entry's body is empty.

        - When ``render_headings`` is True and every entry is empty, the
          common prefix breadcrumb may itself be the trailing heading.
        - When ``render_headings`` is False, the common prefix is never
          emitted, so a body-only-common-prefix chunk renders nothing
          (handled upstream by skip / empty filtering).
        """
        # Recompute the shared-prefix length the renderer would use for the
        # last entry by replaying the dedup walk across all entries.
        previous_headings = common_headings
        prefix_len = len(common_headings)
        for entry in entries:
            shared = common_heading_path((previous_headings, entry.headings))
            if len(shared) < prefix_len:
                shared = common_headings
            relative = entry.headings[len(shared) :]
            previous_headings = entry.headings
        # `relative` is now the last entry's relative heading path.
        if relative:
            return render_heading_path(relative)

        # No relative heading on the last entry: the trailing unit is the
        # common prefix breadcrumb, but only when it is actually rendered.
        if self.options.render_headings and common_headings:
            return render_heading_path(common_headings)
        return ""

    def _trailing_separator_delta(self, text: str) -> int:
        """Tokens added by appending ``SEPARATOR`` to *text* (a phantom correction)."""
        if not text:
            return 0
        return self.tokenizer.count(
            text + SEPARATOR, cache=True
        ) - self.tokenizer.count(text, cache=True)

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
                and current.token_count < merge_below
                and previous.chunk_type == "paragraph"
                and current.chunk_type == "paragraph"
            ):
                merged_draft = self._merge_drafts(previous, current)
                if merged_draft.token_count <= self.options.max_tokens:
                    merged[i - 1] = merged_draft
                    del merged[i]
            i -= 1
        return merged


__all__ = ["_BaseSplitter"]

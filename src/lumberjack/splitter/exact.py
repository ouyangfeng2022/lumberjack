from __future__ import annotations

from typing import Literal

from .._internal.rendering import join_rendered_blocks
from ..models import (
    ChunkDraft,
    DocTree,
    DocumentBlock,
    Entry,
    HeadingKey,
    HeadingPath,
    SectionNode,
    common_heading_path,
    render_draft_body,
    render_heading_path,
    source_locations_for_blocks,
)
from .base import BaseSplitter
from .context import ExactCountingContext, SectionView


class ExactCountingMixin(BaseSplitter):
    """Exact counting strategy: full recount at every budget decision.

    Every budget decision fully recounts the actually-rendered candidate text
    via :meth:`_rendered_token_count`.  No additive arithmetic, no
    :meth:`_measure_section` pre-pass, no separator-delta window.  The
    ``SectionNode`` tree is walked directly.

    Counting runs cache-free: every split starts from a zero tokenizer cache
    and caches are never reused across documents. Identical strings within
    one split (repeated heading paths, bodies counted at both the call site
    and the draft builder, oversized-block pieces counted inside
    BlockSplitter) are deduplicated by a per-split memo instead, so only
    genuinely distinct candidates — the ever-growing rendered
    concatenations — pay full encoding.

    Budget pruning relies on the join-counting property documented on
    :class:`~lumberjack.protocols.TokenizerProtocol`: part-sum lower bounds
    (two tokens of slack per join) skip candidates that provably cannot
    fit. For tokenizers honoring the contract this never changes output;
    a contract-violating tokenizer may see differently grouped chunks.
    """

    use_tokenizer_cache = False

    def split(self, document: DocTree) -> list[ChunkDraft]:
        """Split by walking the raw ``SectionNode`` tree (no pre-measure)."""
        self._validate_document_topology(document)
        self._count_memo: dict[str, int] = {}
        root = ExactCountingContext().prepare(self._root_for_splitting(document))
        drafts = self._post_process_drafts(self._split_section(root))
        for draft in drafts:
            draft.counting_mode = "exact"
        return drafts

    _memoized_count = BaseSplitter._memo_count

    def _merge_bound_exceeds(
        self,
        left_draft: ChunkDraft,
        right_draft: ChunkDraft,
        common_headings: HeadingPath,
        limit: int,
    ) -> bool:
        """Exact drafts carry full body recounts, so their sum bounds the merge.

        Relative to the shared prefix both drafts render as contiguous chunks
        joined by one separator: the merged body is at least
        ``left.body + right.body - 2`` tokens for tokenizers honoring the
        join-counting property documented on ``TokenizerProtocol``.
        """
        head = (
            self._heading_path_token_count(common_headings)
            if self.heading_sensitive
            else 0
        )
        bound = (
            head
            + self.separator_token_count
            + max(
                0,
                left_draft.body_token_count + right_draft.body_token_count - 2,
            )
        )
        return bound > limit

    def _heading_path_token_count(self, path: HeadingPath) -> int:
        if not path:
            return 0
        return self._memo_count(render_heading_path(path))

    def _draft_budget_tokens(self, draft: ChunkDraft) -> int:
        """Exact logical footprint selected by the heading-sensitivity policy."""
        return (
            draft.token_count
            if self.heading_sensitive
            else self._body_budget_tokens(draft)
        )

    def _merge_drafts(
        self,
        left_draft: ChunkDraft,
        right_draft: ChunkDraft,
        *,
        expected_common: HeadingPath | None = None,
    ) -> ChunkDraft:
        """Merge two drafts by fully recounting separated headings and body."""
        left_headings = left_draft.headings
        right_headings = right_draft.headings
        if expected_common is not None:
            common_headings = expected_common
        else:
            common_headings = common_heading_path([left_headings, right_headings])
        merged_entries = [*left_draft.entries, *right_draft.entries]
        own_heading = self._merged_own_heading(left_draft, right_draft, common_headings)
        return self._draft_from_entries(
            merged_entries,
            common_headings,
            own_heading=own_heading,
            origin="merge",
            chunk_type=left_draft.chunk_type,
        )

    def _finalize_estimate(
        self,
        draft: ChunkDraft,  # noqa: ARG002
        external_headings: HeadingPath,  # noqa: ARG002
        token_count: int,
    ) -> int:
        """Exact path: the split-time estimate already equals the full recount."""
        return token_count

    def _exact_body_budget(self, headings: HeadingPath) -> int:
        """Body-only token budget for exact-path body splitting."""
        prefix_tokens = (
            self._heading_path_token_count(headings) if self.heading_sensitive else 0
        )
        fixed_tokens = prefix_tokens + self.separator_token_count
        limit = (
            self.max_tokens
            if fixed_tokens >= self.ideal_max_tokens
            else self.ideal_max_tokens
        )
        return max(0, limit - fixed_tokens)

    def _draft_from_entries(
        self,
        entries: list[Entry],
        headings: HeadingPath,
        *,
        own_heading: HeadingKey | None,
        origin: Literal["section", "fragment", "text_piece", "merge"],
        chunk_type: str = "paragraph",
    ) -> ChunkDraft:
        """Build a draft by fully recounting its separated public fields."""
        body = render_draft_body(entries, headings)
        body_tokens = self._memo_count(body)
        prefix_tokens = self._heading_path_token_count(headings)
        token_count = self._chunk_token_count(prefix_tokens, body_tokens)
        return ChunkDraft(
            entries=entries,
            headings=headings,
            own_heading=own_heading,
            headings_token_count=prefix_tokens,
            body_token_count=body_tokens,
            token_count=token_count,
            split_origin=origin,
            chunk_type=chunk_type,
        )

    def _entries_from_section(self, section: SectionNode) -> list[Entry]:
        """Render-ready entries for a section selected as a draft.

        Entry-level ``body_token_count`` is left at 0 here: exact drafts are
        measured through one full recount of the rendered body, and per-entry
        counts would encode every section body a second time without feeding
        any budget decision.
        """
        entries: list[Entry] = []
        if section.blocks or (not section.children and section.level > 0):
            body = join_rendered_blocks([b.text for b in section.blocks])
            entries.append(
                Entry(
                    headings=section.path,
                    body=body,
                    start_line=self._min_start_lines(section.blocks),
                    end_line=self._max_end_lines(section.blocks),
                    source_locations=source_locations_for_blocks(section.blocks),
                )
            )

        for child in section.children:
            entries.extend(self._entries_from_section(child))

        return entries

    def _subtree_parts(self, section: SectionNode) -> tuple[int, int]:
        """Raw (part-count sum, part count) for the body render below a node.

        Parts are the node's own block texts plus every descendant heading
        and block text; the node's own heading is excluded because it lands
        in the draft's external heading prefix, not its body.
        """
        total = 0
        parts = 0
        for block in section.blocks:
            if block.text:
                total += self._memo_count(block.text)
                parts += 1
        for child in section.children:
            if child.level > 0 and child.title:
                total += self._memo_count(render_heading_path((child.heading_key,)))
                parts += 1
            child_total, child_parts = self._subtree_parts(child)
            total += child_total
            parts += child_parts
        return total, parts

    def _subtree_body_token_bound(self, section: SectionNode) -> int:
        """Sound lower bound of the rendered subtree body cost.

        The render joins every part with ``RENDER_SEPARATOR``; for tokenizers
        honoring the join-counting property documented on
        ``TokenizerProtocol``, each join adds at least one separator token
        while boundary merges save at most a token or two, so two tokens of
        slack per join keeps the bound below the true rendered count.
        """
        total, parts = self._subtree_parts(section)
        return total - 2 * max(0, parts - 1)

    def _split_section_body(
        self,
        section: SectionNode,
    ) -> list[ChunkDraft]:
        """Split a section's own blocks via full rendered counts.

        Each budget decision recounts the actually-rendered candidate body.
        No additive arithmetic, no separator-delta window.
        """
        headings = section.path
        blocks = section.blocks
        budget = self._exact_body_budget(headings)

        if (
            self.heading_sensitive
            and self._heading_path_token_count(headings) + self.separator_token_count
            >= self.max_tokens
        ) or not blocks:
            body = join_rendered_blocks([block.text for block in blocks])
            entry = self._entry_from_blocks(
                headings,
                blocks,
                body_token_count=self._memo_count(body),
            )
            return [
                self._draft_from_entries(
                    [entry],
                    headings,
                    own_heading=headings[-1] if headings else None,
                    origin="fragment",
                )
            ]

        drafts: list[ChunkDraft] = []
        current_entries: list[Entry] = []
        standalone_kinds = self.standalone_kinds

        def flush_current() -> None:
            if not current_entries:
                return
            entries = list(current_entries)
            drafts.append(
                self._draft_from_entries(
                    entries,
                    headings,
                    own_heading=headings[-1] if headings else None,
                    origin="fragment",
                )
            )
            current_entries.clear()

        def make_entry(block: DocumentBlock, body: str, body_tokens: int) -> Entry:
            return Entry(
                headings=headings,
                body=body,
                start_line=block.start_line,
                end_line=block.end_line,
                body_token_count=body_tokens,
                source_locations=block.source_locations,
            )

        for block in blocks:
            if standalone_kinds and block.kind in standalone_kinds:
                flush_current()
                block_pieces = self._block_splitter.split_oversized_block(
                    block,
                    default_budget=budget,
                )
                if block_pieces is not None:
                    for piece, piece_tokens in block_pieces:
                        entry = make_entry(block, piece, piece_tokens)
                        drafts.append(
                            self._draft_from_entries(
                                [entry],
                                headings,
                                own_heading=headings[-1] if headings else None,
                                origin="text_piece",
                                chunk_type=block.kind,
                            )
                        )
                else:
                    entry = make_entry(
                        block,
                        block.text,
                        self._memo_count(block.text),
                    )
                    drafts.append(
                        self._draft_from_entries(
                            [entry],
                            headings,
                            own_heading=headings[-1] if headings else None,
                            origin="fragment",
                            chunk_type=block.kind,
                        )
                    )
                continue

            entry = make_entry(block, block.text, self._memo_count(block.text))
            block_draft = self._draft_from_entries(
                [entry],
                headings,
                own_heading=headings[-1] if headings else None,
                origin="fragment",
                chunk_type="paragraph",
            )

            if (
                block.text
                and self._draft_budget_tokens(block_draft) > self.ideal_max_tokens
            ):
                flush_current()
                block_pieces = self._block_splitter.split_oversized_block(
                    block,
                    default_budget=budget,
                )
                if block_pieces is None:
                    drafts.append(block_draft)
                else:
                    for piece, piece_tokens in block_pieces:
                        pe = make_entry(block, piece, piece_tokens)
                        drafts.append(
                            self._draft_from_entries(
                                [pe],
                                headings,
                                own_heading=headings[-1] if headings else None,
                                origin="text_piece",
                                chunk_type="paragraph",
                            )
                        )
                continue

            candidate_entries = [*current_entries, entry]
            candidate_draft = self._draft_from_entries(
                candidate_entries,
                headings,
                own_heading=headings[-1] if headings else None,
                origin="fragment",
            )
            if (
                current_entries
                and self._draft_budget_tokens(candidate_draft) > self.ideal_max_tokens
            ):
                flush_current()

            current_entries.append(entry)

        flush_current()
        return drafts

    def _section_has_standalone(self, section: SectionNode) -> bool:
        """Whether this section's subtree contains any standalone block."""
        standalone_kinds = self.standalone_kinds
        if any(b.kind in standalone_kinds for b in section.blocks):
            return True
        return any(self._section_has_standalone(c) for c in section.children)

    def _direct_body_drafts(self, section: SectionView) -> list[ChunkDraft]:
        """Emit this section's direct body, without topology recursion."""
        node = section.node
        if not (node.blocks or node.level > 0):
            return []
        body = join_rendered_blocks([block.text for block in node.blocks])
        body_tokens = self._memo_count(body)
        has_standalone = any(
            block.kind in self.standalone_kinds for block in node.blocks
        )
        entry = Entry(
            headings=node.path,
            body=body,
            start_line=self._min_start_lines(node.blocks),
            end_line=self._max_end_lines(node.blocks),
            body_token_count=body_tokens,
            source_locations=source_locations_for_blocks(node.blocks),
        )
        draft = self._draft_from_entries(
            [entry],
            node.path,
            own_heading=node.path[-1] if node.path else None,
            origin="section",
        )
        if has_standalone or self._draft_budget_tokens(draft) > self.ideal_max_tokens:
            return self._split_section_body(node)
        return [draft]

    def _single_subtree_draft(self, section: SectionView) -> ChunkDraft | None:
        if self._section_has_standalone(section.node):
            return None
        structural_root = section
        if (
            section.node.level == 0
            and not section.node.blocks
            and len(section.children) == 1
        ):
            structural_root = section.children[0]
        node = structural_root.node
        head_tokens = (
            self._heading_path_token_count(node.path) if self.heading_sensitive else 0
        )
        if (
            head_tokens
            + self.separator_token_count
            + self._subtree_body_token_bound(node)
            > self.ideal_max_tokens
        ):
            return None
        entries = self._entries_from_section(node)
        return self._draft_from_entries(
            entries,
            node.path,
            own_heading=(node.path[-1] if node.path else None),
            origin="section",
        )

    def _packable_body_draft(self, section: SectionView) -> ChunkDraft | None:
        node = section.node
        if not node.blocks or any(
            block.kind in self.standalone_kinds for block in node.blocks
        ):
            return None
        entry = self._entry_from_blocks(
            node.path,
            node.blocks,
            body_token_count=self._memo_count(
                join_rendered_blocks([block.text for block in node.blocks])
            ),
        )
        draft = self._draft_from_entries(
            [entry],
            node.path,
            own_heading=node.path[-1] if node.path else None,
            origin="section",
        )
        return (
            draft if self._draft_budget_tokens(draft) <= self.ideal_max_tokens else None
        )


__all__ = ["ExactCountingMixin"]

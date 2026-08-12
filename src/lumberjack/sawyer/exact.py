from __future__ import annotations

from typing import Literal

from .._internal.rendering import join_rendered_blocks
from ..models import (
    Bundle,
    DocumentBlock,
    Entry,
    HeadingKey,
    HeadingPath,
    Log,
    SectionNode,
    common_heading_path,
)
from .base import BaseSawyer
from .context import ExactCountingContext, SectionView


class ExactCountingMixin(BaseSawyer):
    """Exact counting strategy: full recount at every budget decision.

    Every budget decision fully recounts the actually-rendered candidate text
    via :meth:`_rendered_token_count`.  No additive arithmetic, no
    :meth:`_measure_section` pre-pass, no separator-delta window.  The
    ``SectionNode`` tree is walked directly.
    """

    def saw(self, log: Log) -> list[Bundle]:
        """Split by walking the raw ``SectionNode`` tree (no pre-measure)."""
        root = ExactCountingContext().prepare(self._root_for_splitting(log))
        bundles = self._post_process_bundles(self._split_section(root))
        for bundle in bundles:
            bundle.counting_mode = "exact"
        return bundles

    def _bundle_budget_tokens(self, bundle: Bundle) -> int:
        """Exact logical footprint selected by the heading-sensitivity policy."""
        return bundle.token_count if self.heading_sensitive else bundle.body_token_count

    def _merge_bundles(
        self,
        left_bundle: Bundle,
        right_bundle: Bundle,
        *,
        expected_common: HeadingPath | None = None,
    ) -> Bundle:
        """Merge two bundles by fully recounting separated headings and body."""
        left_headings = left_bundle.headings
        right_headings = right_bundle.headings
        if expected_common is not None:
            common_headings = expected_common
        else:
            common_headings = common_heading_path([left_headings, right_headings])
        merged_entries = [*left_bundle.entries, *right_bundle.entries]
        own_heading = self._merged_own_heading(
            left_bundle, right_bundle, common_headings
        )
        return self._bundle_from_entries(
            merged_entries,
            common_headings,
            own_heading=own_heading,
            origin="merge",
            chunk_type=left_bundle.chunk_type,
        )

    def _finalize_estimate(
        self,
        bundle: Bundle,  # noqa: ARG002
        external_headings: HeadingPath,  # noqa: ARG002
        token_count: int,
    ) -> int:
        """Exact path: the split-time estimate already equals the full recount."""
        return token_count

    def _exact_body_budget(self, headings: HeadingPath) -> int:
        """Body-only token budget for exact-path body splitting."""
        if not self.heading_sensitive:
            return self.ideal_max_tokens
        prefix_tokens = self._heading_path_token_count(headings)
        limit = (
            self.max_tokens
            if prefix_tokens >= self.ideal_max_tokens
            else self.ideal_max_tokens
        )
        return max(0, limit - prefix_tokens)

    def _bundle_from_entries(
        self,
        entries: list[Entry],
        headings: HeadingPath,
        *,
        own_heading: HeadingKey | None,
        origin: Literal["section", "fragment", "text_piece", "merge"],
        chunk_type: str = "paragraph",
    ) -> Bundle:
        """Build a bundle by fully recounting its separated public fields."""
        body = self._render_body(entries, external_headings=headings)
        body_tokens = self.scaler.scale(body, cache=True)
        prefix_tokens = self._heading_path_token_count(headings)
        token_count = prefix_tokens + body_tokens
        return Bundle(
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
        """Render-ready entries for a section selected as a bundle."""
        entries: list[Entry] = []
        if section.blocks or (not section.children and section.level > 0):
            body = join_rendered_blocks([b.text for b in section.blocks])
            entries.append(
                Entry(
                    headings=section.path,
                    body=body,
                    start_line=self._min_start_lines(section.blocks),
                    end_line=self._max_end_lines(section.blocks),
                    body_token_count=self.scaler.scale(body, cache=True),
                )
            )

        for child in section.children:
            entries.extend(self._entries_from_section(child))

        return entries

    def _split_section_body(
        self,
        section: SectionNode,
    ) -> list[Bundle]:
        """Split a section's own blocks via full rendered counts.

        Each budget decision recounts the actually-rendered candidate body.
        No additive arithmetic, no separator-delta window.
        """
        headings = section.path
        blocks = section.blocks
        budget = self._exact_body_budget(headings)

        if (
            self.heading_sensitive
            and self._heading_path_token_count(headings) >= self.max_tokens
        ) or not blocks:
            body = join_rendered_blocks([block.text for block in blocks])
            entry = self._entry_from_blocks(
                headings,
                blocks,
                body_token_count=self.scaler.scale(body, cache=True),
            )
            return [
                self._bundle_from_entries(
                    [entry],
                    headings,
                    own_heading=headings[-1] if headings else None,
                    origin="fragment",
                )
            ]

        bundles: list[Bundle] = []
        current_entries: list[Entry] = []
        standalone_kinds = self.standalone_kinds

        def flush_current() -> None:
            if not current_entries:
                return
            entries = list(current_entries)
            bundles.append(
                self._bundle_from_entries(
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
            )

        for block in blocks:
            if standalone_kinds and block.kind in standalone_kinds:
                flush_current()
                block_pieces = self._block_saw.split_oversized_block(
                    block,
                    default_budget=budget,
                )
                if block_pieces is not None:
                    for piece, piece_tokens in block_pieces:
                        entry = make_entry(block, piece, piece_tokens)
                        bundles.append(
                            self._bundle_from_entries(
                                [entry],
                                headings,
                                own_heading=headings[-1] if headings else None,
                                origin="text_piece",
                                chunk_type=block.kind,
                            )
                        )
                else:
                    entry = make_entry(
                        block, block.text, self.scaler.scale(block.text, cache=True)
                    )
                    bundles.append(
                        self._bundle_from_entries(
                            [entry],
                            headings,
                            own_heading=headings[-1] if headings else None,
                            origin="fragment",
                            chunk_type=block.kind,
                        )
                    )
                continue

            entry = make_entry(
                block, block.text, self.scaler.scale(block.text, cache=True)
            )
            block_bundle = self._bundle_from_entries(
                [entry],
                headings,
                own_heading=headings[-1] if headings else None,
                origin="fragment",
                chunk_type="paragraph",
            )

            if (
                block.text
                and self._bundle_budget_tokens(block_bundle) > self.ideal_max_tokens
            ):
                flush_current()
                block_pieces = self._block_saw.split_oversized_block(
                    block,
                    default_budget=budget,
                )
                if block_pieces is None:
                    bundles.append(block_bundle)
                else:
                    for piece, piece_tokens in block_pieces:
                        pe = make_entry(block, piece, piece_tokens)
                        bundles.append(
                            self._bundle_from_entries(
                                [pe],
                                headings,
                                own_heading=headings[-1] if headings else None,
                                origin="text_piece",
                                chunk_type="paragraph",
                            )
                        )
                continue

            candidate_entries = [*current_entries, entry]
            candidate_bundle = self._bundle_from_entries(
                candidate_entries,
                headings,
                own_heading=headings[-1] if headings else None,
                origin="fragment",
            )
            if (
                current_entries
                and self._bundle_budget_tokens(candidate_bundle) > self.ideal_max_tokens
            ):
                flush_current()

            current_entries.append(entry)

        flush_current()
        return bundles

    def _section_has_standalone(self, section: SectionNode) -> bool:
        """Whether this section's subtree contains any standalone block."""
        standalone_kinds = self.standalone_kinds
        if any(b.kind in standalone_kinds for b in section.blocks):
            return True
        return any(self._section_has_standalone(c) for c in section.children)

    def _direct_body_bundles(self, section: SectionView) -> list[Bundle]:
        """Emit this section's direct body, without topology recursion."""
        node = section.node
        if not (node.blocks or node.level > 0):
            return []
        body = join_rendered_blocks([block.text for block in node.blocks])
        body_tokens = self.scaler.scale(body, cache=True)
        has_standalone = any(
            block.kind in self.standalone_kinds for block in node.blocks
        )
        entry = Entry(
            headings=node.path,
            body=body,
            start_line=self._min_start_lines(node.blocks),
            end_line=self._max_end_lines(node.blocks),
            body_token_count=body_tokens,
        )
        bundle = self._bundle_from_entries(
            [entry],
            node.path,
            own_heading=node.path[-1] if node.path else None,
            origin="section",
        )
        if has_standalone or self._bundle_budget_tokens(bundle) > self.ideal_max_tokens:
            return self._split_section_body(node)
        return [bundle]

    def _single_subtree_bundle(self, section: SectionView) -> Bundle | None:
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
        entries = self._entries_from_section(node)
        return self._bundle_from_entries(
            entries,
            node.path,
            own_heading=(node.path[-1] if node.path else None),
            origin="section",
        )

    def _packable_body_bundle(self, section: SectionView) -> Bundle | None:
        node = section.node
        if not node.blocks or any(
            block.kind in self.standalone_kinds for block in node.blocks
        ):
            return None
        entry = self._entry_from_blocks(
            node.path,
            node.blocks,
            body_token_count=self.scaler.scale(
                join_rendered_blocks([block.text for block in node.blocks]),
                cache=True,
            ),
        )
        bundle = self._bundle_from_entries(
            [entry],
            node.path,
            own_heading=node.path[-1] if node.path else None,
            origin="section",
        )
        return (
            bundle
            if self._bundle_budget_tokens(bundle) <= self.ideal_max_tokens
            else None
        )


__all__ = ["ExactCountingMixin"]

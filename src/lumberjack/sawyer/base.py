from __future__ import annotations

from collections.abc import Iterable

from lumberjack.block import BlockKind, BlockOption, normalize_block_options

from .._internal.block_saw import BlockSaw
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
    render_heading_path,
)
from ..protocols import ScalerProtocol
from .context import SectionView


class BaseSawyer:
    """Shared state and helpers for sawyer strategies.

    Concrete sawyers combine this base with one counting-strategy mixin:

    * :class:`ExactCountingMixin` — full recount at every budget decision
      (walks the raw ``SectionNode`` tree, no pre-measure).
    * :class:`IncrementalCountingMixin` — additive running estimate +
      8-char separator-delta window (walks a pre-measured
      :class:`SectionView` tree).

    Each mixin owns :meth:`saw`, :meth:`_bundle_budget_tokens`,
    :meth:`_merge_bundles`, :meth:`_finalize_estimate`, body splitting, and
    section entry rendering.  This class holds only the pieces that are
    independent of both topology and counting strategy: scaler/options
    wiring, rendering helpers, and small-bundle merging.
    """

    def __init__(
        self,
        scaler: ScalerProtocol,
        *,
        max_tokens: int = 1200,
        ideal_max_tokens_ratio: float = 0.8,
        skip_empty_sections: bool = True,
        heading_sensitive: bool = True,
        max_heading_level: int | None = None,
        block_options: Iterable[BlockOption] | None = None,
        _merge_below_ratio: float = 0.0,
    ) -> None:
        self.scaler = scaler
        self.max_tokens = max_tokens
        self.ideal_max_tokens_ratio = ideal_max_tokens_ratio
        self.ideal_max_tokens = max(1, int(max_tokens * ideal_max_tokens_ratio))
        self.merge_below_ratio = _merge_below_ratio
        self.skip_empty_sections = skip_empty_sections
        self.heading_sensitive = heading_sensitive
        self.max_heading_level = max_heading_level
        self.block_options = normalize_block_options(block_options)
        self.standalone_kinds = frozenset(
            kind for kind, config in self.block_options.items() if config.isolated
        )
        self._validate_options()
        self._block_saw = BlockSaw(
            scaler,
            max_tokens=self.max_tokens,
            block_options=self.block_options,
        )

    def saw(self, log: Log) -> list[Bundle]:  # pragma: no cover
        raise NotImplementedError(
            "saw() is provided by a counting-strategy mixin "
            "(ExactCountingMixin or IncrementalCountingMixin)"
        )

    def _heading_path_token_count(self, path: HeadingPath) -> int:
        if not path:
            return 0
        return self.scaler.scale(render_heading_path(path), cache=True)

    def _render_body(
        self,
        entries: list[Entry],
        *,
        external_headings: HeadingPath,
    ) -> str:
        """Render entries into Markdown body content."""
        if not entries:
            return ""

        parts: list[str] = []
        previous_headings = external_headings
        for entry in entries:
            shared_headings = common_heading_path((previous_headings, entry.headings))
            if len(shared_headings) < len(external_headings):
                shared_headings = external_headings
            relative_headings = entry.headings[len(shared_headings) :]

            entry_parts: list[str] = []
            if relative_headings:
                entry_parts.append(render_heading_path(relative_headings))
            if entry.body:
                entry_parts.append(entry.body)
            rendered = join_rendered_blocks(entry_parts)
            if rendered:
                parts.append(rendered)
            previous_headings = entry.headings

        return join_rendered_blocks(parts)

    def _rendered_token_count(
        self,
        entries: list[Entry],
        *,
        external_headings: HeadingPath | None = None,
    ) -> int:
        """Full token count of the rendered body for *entries*."""
        if external_headings is None:
            external_headings = common_heading_path(entry.headings for entry in entries)
        return self.scaler.scale(
            self._render_body(entries, external_headings=external_headings), cache=True
        )

    def _heading_budget_token_count(self, path: HeadingPath) -> int:
        """Canonical Markdown token count for a bundle's external heading path."""
        return self._heading_path_token_count(path)

    def _root_for_splitting(self, log: Log) -> SectionNode:
        """Return the section tree used by sawyers after option-level shaping."""
        if self.max_heading_level is None:
            return log.root
        return self._limit_heading_depth(log.root, self.max_heading_level)

    def _limit_heading_depth(
        self,
        root: SectionNode,
        max_heading_level: int,
    ) -> SectionNode:
        """Clone *root*, demoting deeper sections into paragraph blocks."""
        limited_root = SectionNode(
            level=root.level,
            title=root.title,
            path=root.path,
            blocks=list(root.blocks),
            index=root.index,
            start_line=root.start_line,
            title_inlines=root.title_inlines,
        )

        def demote_section(target: SectionNode, section: SectionNode) -> None:
            target.blocks.append(
                DocumentBlock(
                    kind=BlockKind.PARAGRAPH,
                    text=render_heading_path((section.heading_key,)),
                    start_line=section.start_line,
                    end_line=section.start_line,
                    inlines=section.title_inlines,
                    attrs={"demoted_heading_level": section.level},
                )
            )
            target.blocks.extend(section.blocks)
            for child in section.children:
                demote_section(target, child)

        def clone_allowed(parent: SectionNode, section: SectionNode) -> None:
            if section.level > max_heading_level:
                demote_section(parent, section)
                return

            cloned = SectionNode(
                level=section.level,
                title=section.title,
                path=(*parent.path, section.heading_key),
                blocks=list(section.blocks),
                index=len(parent.children),
                start_line=section.start_line,
                title_inlines=section.title_inlines,
            )
            parent.add_child(cloned)
            for child in section.children:
                clone_allowed(cloned, child)

        for child in root.children:
            clone_allowed(limited_root, child)

        return limited_root

    def _bundle_budget_tokens(self, bundle: Bundle) -> int:  # pragma: no cover
        """Rendered footprint of a bundle, used for budget decisions.

        Provided by :class:`ExactCountingMixin` (full recount) or
        :class:`IncrementalCountingMixin` (running estimate).
        """
        raise NotImplementedError

    def _merge_bundles(
        self,
        left_bundle: Bundle,
        right_bundle: Bundle,
        *,
        expected_common: HeadingPath | None = None,
    ) -> Bundle:
        """Merge two bundles; provided by the counting-strategy mixin."""
        raise NotImplementedError

    @staticmethod
    def _merged_own_heading(
        left_bundle: Bundle,
        right_bundle: Bundle,
        common_headings: HeadingPath,
    ) -> HeadingKey | None:
        """Keep a structural root only when one input owns the merged prefix."""
        for bundle in (left_bundle, right_bundle):
            if (
                common_headings
                and bundle.headings == common_headings
                and bundle.own_heading is not None
                and bundle.own_heading == common_headings[-1]
            ):
                return bundle.own_heading
        return None

    def _finalize_estimate(
        self,
        bundle: Bundle,
        external_headings: HeadingPath,
        token_count: int,
    ) -> int:
        """Estimated token count carried onto the final Chunk; mixin-provided."""
        raise NotImplementedError

    def _split_section(self, section: SectionView) -> list[Bundle]:  # pragma: no cover
        """Saw one section using the selected topology and counting strategy."""
        raise NotImplementedError

    def _post_process_bundles(self, bundles: list[Bundle]) -> list[Bundle]:
        return bundles

    def _validate_options(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")
        if not 0 < self.ideal_max_tokens_ratio <= 1:
            raise ValueError(
                "ideal_max_tokens_ratio must be greater than 0 and at most 1"
            )
        if not (0.0 <= self.merge_below_ratio < 1.0):
            raise ValueError(
                f"merge_below_ratio must be in [0.0, 1.0), got {self.merge_below_ratio}"
            )
        if self.max_heading_level is not None and self.max_heading_level < 0:
            raise ValueError("max_heading_level must be greater than or equal to 0")

    def _entry_from_blocks(
        self,
        headings: HeadingPath,
        blocks: list[DocumentBlock],
        *,
        body_token_count: int,
    ) -> Entry:
        body = join_rendered_blocks([block.text for block in blocks])
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
        bundles: list[Bundle],
        *,
        parent_headings: HeadingPath | None = None,
    ) -> list[Bundle]:
        """Merge adjacent same-parent bundles below the merge threshold, bottom-up.

        Threshold = ``int(max_tokens * merge_below_ratio)``;
        ``merge_below_ratio == 0`` disables merging entirely.
        """
        merge_below = int(self.max_tokens * self.merge_below_ratio)
        if merge_below <= 0:
            return bundles
        if not bundles:
            return bundles

        merged: list[Bundle] = list(bundles)
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
                and self._bundle_budget_tokens(current) < merge_below
                and previous.chunk_type == "paragraph"
                and current.chunk_type == "paragraph"
            ):
                merged_bundle = self._merge_bundles(previous, current)
                # Compare the policy-selected footprint against max_tokens.
                # Because can_merge guarantees matching heading paths, the
                # merged common prefix is that shared path.
                if self._bundle_budget_tokens(merged_bundle) <= self.max_tokens:
                    merged[i - 1] = merged_bundle
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
    def _min_start_lines(blocks: list[DocumentBlock]) -> int | None:
        vals = [b.start_line for b in blocks if b.start_line is not None]
        return min(vals) if vals else None

    @staticmethod
    def _max_end_lines(blocks: list[DocumentBlock]) -> int | None:
        vals = [b.end_line for b in blocks if b.end_line is not None]
        return max(vals) if vals else None


__all__ = ["BaseSawyer"]

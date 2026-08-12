from __future__ import annotations

from collections.abc import Iterable

from lumberjack.block import BlockOption

from ...models import Bundle, HeadingPath
from ...protocols import ScalerProtocol
from ..base import BaseSawyer
from ..context import SectionView


class SiblingTopologyMixin(BaseSawyer):
    """Greedily pack a section body and fitting sibling subtrees."""

    def __init__(
        self,
        scaler: ScalerProtocol,
        *,
        max_tokens: int = 1200,
        ideal_max_tokens_ratio: float = 0.8,
        merge_below_ratio: float = 0.125,
        skip_empty_sections: bool = True,
        heading_sensitive: bool = True,
        max_heading_level: int | None = None,
        block_options: Iterable[BlockOption] | None = None,
    ) -> None:
        super().__init__(
            scaler,
            max_tokens=max_tokens,
            ideal_max_tokens_ratio=ideal_max_tokens_ratio,
            skip_empty_sections=skip_empty_sections,
            heading_sensitive=heading_sensitive,
            max_heading_level=max_heading_level,
            block_options=block_options,
            _merge_below_ratio=merge_below_ratio,
        )

    def _single_subtree_bundle(self, section: SectionView) -> Bundle | None:
        raise NotImplementedError

    def _packable_body_bundle(self, section: SectionView) -> Bundle | None:
        raise NotImplementedError

    def _direct_body_bundles(self, section: SectionView) -> list[Bundle]:
        raise NotImplementedError

    def _bundle_budget_tokens(self, bundle: Bundle) -> int:
        raise NotImplementedError

    def _merge_bundles(
        self,
        left_bundle: Bundle,
        right_bundle: Bundle,
        *,
        expected_common: HeadingPath | None = None,
    ) -> Bundle:
        raise NotImplementedError

    def _split_section(self, section: SectionView) -> list[Bundle]:
        node = section.node
        children = section.children
        if not (node.blocks or children or node.level > 0):
            return []
        single = self._single_subtree_bundle(section)
        if (
            single is not None
            and self._bundle_budget_tokens(single) <= self.ideal_max_tokens
        ):
            return [single]
        if not children:
            return self._merge_small_chunks(
                self._direct_body_bundles(section),
                parent_headings=node.path,
            )
        bundles: list[Bundle] = []
        current: Bundle | None = None

        def flush() -> None:
            nonlocal current
            if current is not None:
                bundles.append(current)
                current = None

        def add(bundle: Bundle) -> None:
            nonlocal current
            if current is None:
                current = bundle
                return
            merged = self._merge_bundles(current, bundle, expected_common=node.path)
            if self._bundle_budget_tokens(merged) <= self.ideal_max_tokens:
                current = merged
            else:
                bundles.append(current)
                current = bundle

        body = self._packable_body_bundle(section)
        if body is not None:
            add(body)
        elif node.blocks:
            flush()
            bundles.extend(self._direct_body_bundles(section))
        for child in children:
            bundle = self._single_subtree_bundle(child)
            if (
                bundle is not None
                and self._bundle_budget_tokens(bundle) <= self.ideal_max_tokens
            ):
                add(bundle)
            else:
                flush()
                bundles.extend(self._split_section(child))
        flush()
        return self._merge_small_chunks(bundles, parent_headings=node.path)

from __future__ import annotations

from collections.abc import Iterable

from lumberjack.block import BlockOption

from ...models import Bundle
from ...protocols import ScalerProtocol
from ..base import BaseSawyer
from ..context import SectionView


class SubtreeTopologyMixin(BaseSawyer):
    """Collapse a fitting subtree, otherwise split direct bodies then recurse."""

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

    def _direct_body_bundles(self, section: SectionView) -> list[Bundle]:
        raise NotImplementedError

    def _single_subtree_bundle(self, section: SectionView) -> Bundle | None:
        raise NotImplementedError

    def _bundle_budget_tokens(self, bundle: Bundle) -> int:
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
        bundles = self._merge_small_chunks(
            self._direct_body_bundles(section), parent_headings=node.path
        )
        for child in children:
            bundles.extend(self._split_section(child))
        return bundles

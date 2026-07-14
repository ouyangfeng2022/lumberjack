from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ..models import MeasuredSection, SectionNode

if TYPE_CHECKING:
    from .base import BaseSplitter


class _IncrementalOwner(Protocol):
    def _measure_section(self, section: SectionNode) -> MeasuredSection: ...


@dataclass(frozen=True)
class SectionView:
    """Topology-facing view of either a raw or pre-measured section."""

    node: SectionNode
    children: tuple[SectionView, ...]
    body_tokens: int | None = None
    subtree_tokens: int | None = None
    can_emit_as_single_chunk: bool | None = None


class ExactCountingContext:
    """Adapt raw sections for exact-counting topology code."""

    def __init__(self, splitter: BaseSplitter) -> None:
        self.splitter = splitter

    def prepare(self, section: SectionNode) -> SectionView:
        return SectionView(
            node=section,
            children=tuple(self.prepare(child) for child in section.children),
        )


class IncrementalCountingContext:
    """Adapt the existing measured tree for incremental topology code."""

    def __init__(self, splitter: _IncrementalOwner) -> None:
        self.splitter = splitter

    def prepare(self, section: SectionNode) -> SectionView:
        return self._view(self.splitter._measure_section(section))

    def _view(self, section: MeasuredSection) -> SectionView:
        return SectionView(
            node=section.node,
            children=tuple(self._view(child) for child in section.children),
            body_tokens=section.counts.body,
            subtree_tokens=section.counts.subtree,
            can_emit_as_single_chunk=section.can_emit_as_single_chunk,
        )


__all__ = ["ExactCountingContext", "IncrementalCountingContext", "SectionView"]

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lumberjack.block import BlockKind

from .._internal.rendering import RENDER_SEPARATOR
from ..models import SectionNode, render_heading_path


@dataclass(frozen=True, slots=True)
class SectionView:
    """Topology-facing view of either a raw or pre-measured section."""

    node: SectionNode
    children: tuple[SectionView, ...]
    title_tokens: int | None = None
    body_tokens: int | None = None
    subtree_tokens: int | None = None
    tail_text: str | None = None
    can_emit_as_single_chunk: bool | None = None


class _IncrementalOwner(Protocol):
    @property
    def standalone_kinds(self) -> frozenset[BlockKind]: ...

    def _count_once(self, text: str) -> int: ...

    def _separator_delta_after(self, text: str) -> int: ...


class ExactCountingContext:
    """Adapt raw sections for exact-counting topology code."""

    def prepare(self, section: SectionNode) -> SectionView:
        return SectionView(
            node=section,
            children=tuple(self.prepare(child) for child in section.children),
        )


class IncrementalCountingContext:
    """Measure sections once while building the topology-facing view."""

    def __init__(self, sawyer: _IncrementalOwner) -> None:
        self.sawyer = sawyer

    def prepare(self, section: SectionNode) -> SectionView:
        children = tuple(self.prepare(child) for child in section.children)

        body_tokens = 0
        body_texts = [block.text for block in section.blocks if block.text]
        for index, text in enumerate(body_texts):
            if index == len(body_texts) - 1:
                body_tokens += self.sawyer._count_once(text)
            else:
                body_tokens += self.sawyer._count_once(text + RENDER_SEPARATOR)

        if section.level > 0:
            title_text = render_heading_path((section.heading_key,))
            title_tokens = self.sawyer._count_once(title_text)
        else:
            title_tokens = 0

        subtree_tokens = body_tokens
        previous_tail = body_texts[-1] if body_texts else ""
        for child in children:
            child_title_tokens = child.title_tokens
            child_subtree_tokens = child.subtree_tokens
            child_tail = child.tail_text
            if (
                child_title_tokens is None
                or child_subtree_tokens is None
                or child_tail is None
            ):
                raise TypeError("incremental child view is missing measurements")

            child_title = render_heading_path((child.node.heading_key,))
            child_tokens = child_title_tokens + child_subtree_tokens
            child_has_body = bool(child.node.blocks or child.children)
            if child_title and child_has_body:
                child_tokens += self.sawyer._separator_delta_after(child_title)
            if previous_tail:
                subtree_tokens += self.sawyer._separator_delta_after(previous_tail)
            subtree_tokens += child_tokens
            previous_tail = child_tail

        if previous_tail:
            tail_text = previous_tail
        elif section.level > 0:
            tail_text = "#" * section.level + " " + section.title
        else:
            tail_text = ""

        body_has_standalone = any(
            block.kind in self.sawyer.standalone_kinds for block in section.blocks
        )
        child_eligibility = tuple(child.can_emit_as_single_chunk for child in children)
        if any(eligible is None for eligible in child_eligibility):
            raise TypeError(
                "incremental child view is missing single-bundle eligibility"
            )
        can_emit_as_single_chunk = not body_has_standalone and all(child_eligibility)

        return SectionView(
            node=section,
            children=children,
            title_tokens=title_tokens,
            body_tokens=body_tokens,
            subtree_tokens=subtree_tokens,
            tail_text=tail_text,
            can_emit_as_single_chunk=can_emit_as_single_chunk,
        )


__all__ = ["ExactCountingContext", "IncrementalCountingContext", "SectionView"]

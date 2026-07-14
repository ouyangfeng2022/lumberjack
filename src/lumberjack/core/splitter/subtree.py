from __future__ import annotations

from .base import BaseSplitter
from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin
from .topology.subtree import SubtreeTopologyMixin


class ExactSubtreeSplitter(ExactCountingMixin, SubtreeTopologyMixin, BaseSplitter):
    """Subtree-first splitter using exact rendered-text budget decisions."""


class IncrementalSubtreeSplitter(
    IncrementalCountingMixin, SubtreeTopologyMixin, BaseSplitter
):
    """Subtree-first splitter using additive incremental estimates."""


SubtreeSplitter = ExactSubtreeSplitter

__all__ = [
    "ExactSubtreeSplitter",
    "IncrementalSubtreeSplitter",
    "SubtreeSplitter",
]

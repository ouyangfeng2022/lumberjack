from __future__ import annotations

from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin
from .topology.subtree import SubtreeTopologyMixin


class ExactSubtreeSplitter(ExactCountingMixin, SubtreeTopologyMixin):
    """Subtree-first splitter using exact rendered-text budget decisions."""


class IncrementalSubtreeSplitter(IncrementalCountingMixin, SubtreeTopologyMixin):
    """Subtree-first splitter using additive incremental estimates."""


SubtreeSplitter = IncrementalSubtreeSplitter

__all__ = [
    "ExactSubtreeSplitter",
    "IncrementalSubtreeSplitter",
    "SubtreeSplitter",
]

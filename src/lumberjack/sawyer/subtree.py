from __future__ import annotations

from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin
from .topology.subtree import SubtreeTopologyMixin


class ExactSubtreeSawyer(ExactCountingMixin, SubtreeTopologyMixin):
    """Subtree-first sawyer using exact rendered-text budget decisions."""


class IncrementalSubtreeSawyer(IncrementalCountingMixin, SubtreeTopologyMixin):
    """Subtree-first sawyer using additive incremental estimates."""


SubtreeSawyer = IncrementalSubtreeSawyer

__all__ = [
    "ExactSubtreeSawyer",
    "IncrementalSubtreeSawyer",
    "SubtreeSawyer",
]

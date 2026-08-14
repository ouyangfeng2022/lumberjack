from __future__ import annotations

from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin
from .topology.sibling import SiblingTopologyMixin


class ExactSiblingSplitter(ExactCountingMixin, SiblingTopologyMixin):
    pass


class IncrementalSiblingSplitter(IncrementalCountingMixin, SiblingTopologyMixin):
    pass


SiblingSplitter = IncrementalSiblingSplitter
__all__ = [
    "ExactSiblingSplitter",
    "IncrementalSiblingSplitter",
    "SiblingSplitter",
]

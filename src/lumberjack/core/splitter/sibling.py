from __future__ import annotations

from .base import BaseSplitter
from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin
from .topology.sibling import SiblingTopologyMixin


class ExactSiblingSplitter(ExactCountingMixin, SiblingTopologyMixin, BaseSplitter):
    pass


class IncrementalSiblingSplitter(
    IncrementalCountingMixin, SiblingTopologyMixin, BaseSplitter
):
    pass


SiblingSplitter = ExactSiblingSplitter
__all__ = [
    "ExactSiblingSplitter",
    "IncrementalSiblingSplitter",
    "SiblingSplitter",
]

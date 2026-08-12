from __future__ import annotations

from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin
from .topology.sibling import SiblingTopologyMixin


class ExactSiblingSawyer(ExactCountingMixin, SiblingTopologyMixin):
    pass


class IncrementalSiblingSawyer(IncrementalCountingMixin, SiblingTopologyMixin):
    pass


SiblingSawyer = IncrementalSiblingSawyer
__all__ = [
    "ExactSiblingSawyer",
    "IncrementalSiblingSawyer",
    "SiblingSawyer",
]

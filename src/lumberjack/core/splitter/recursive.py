from __future__ import annotations

from .base import BaseSplitter
from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin
from .topology.recursive import RecursiveTopologyMixin


class ExactRecursiveSplitter(ExactCountingMixin, RecursiveTopologyMixin, BaseSplitter):
    pass


class IncrementalRecursiveSplitter(
    IncrementalCountingMixin, RecursiveTopologyMixin, BaseSplitter
):
    pass


RecursiveSplitter = ExactRecursiveSplitter
__all__ = [
    "ExactRecursiveSplitter",
    "IncrementalRecursiveSplitter",
    "RecursiveSplitter",
]

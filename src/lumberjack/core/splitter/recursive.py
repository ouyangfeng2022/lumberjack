"""Compatibility aliases for the renamed sibling-packing splitter."""

from .sibling import (
    ExactSiblingSplitter,
    IncrementalSiblingSplitter,
    SiblingSplitter,
)

ExactRecursiveSplitter = ExactSiblingSplitter
IncrementalRecursiveSplitter = IncrementalSiblingSplitter
RecursiveSplitter = SiblingSplitter

__all__ = [
    "ExactRecursiveSplitter",
    "IncrementalRecursiveSplitter",
    "RecursiveSplitter",
]

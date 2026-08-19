"""Optional competitor adapters; none are Lumberjack runtime dependencies."""

from .base import AdapterUnavailable, BenchmarkAdapter
from .competitors import (
    ChonkieRecursiveAdapter,
    DoclingHierarchicalAdapter,
    UnstructuredBasicAdapter,
    UnstructuredByTitleAdapter,
)
from .lumberjack import LumberjackAdapter

__all__ = [
    "AdapterUnavailable",
    "BenchmarkAdapter",
    "ChonkieRecursiveAdapter",
    "DoclingHierarchicalAdapter",
    "LumberjackAdapter",
    "UnstructuredBasicAdapter",
    "UnstructuredByTitleAdapter",
]

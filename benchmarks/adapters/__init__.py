"""Optional competitor adapters; none are Lumberjack runtime dependencies."""

from .base import AdapterUnavailable, BenchmarkAdapter
from .competitors import (
    ChonkieRecursiveAdapter,
    ChonkieTableAdapter,
    DoclingHierarchicalAdapter,
    DoclingHybridAdapter,
    UnstructuredBasicAdapter,
    UnstructuredByTitleAdapter,
)
from .langchain import (
    LangChainHTMLAdapter,
    LangChainMarkdownAdapter,
    LangChainRecursiveAdapter,
)
from .lumberjack import LumberjackAdapter

__all__ = [
    "AdapterUnavailable",
    "BenchmarkAdapter",
    "ChonkieRecursiveAdapter",
    "ChonkieTableAdapter",
    "DoclingHierarchicalAdapter",
    "DoclingHybridAdapter",
    "LangChainHTMLAdapter",
    "LangChainMarkdownAdapter",
    "LangChainRecursiveAdapter",
    "LumberjackAdapter",
    "UnstructuredBasicAdapter",
    "UnstructuredByTitleAdapter",
]

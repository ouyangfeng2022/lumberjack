"""Optional adapters from Lumberjack chunks to RAG framework objects.

The eager exports are the chunk-conversion helpers, which never import a
framework at import time. Native pipeline components (node parsers, text
splitters, splitter components) live in dedicated modules that do import
their framework and are exposed lazily via module ``__getattr__``:

- ``lumberjack.integrations.llama_index_pipeline``: LumberjackNodeParser,
  LumberjackReader
- ``lumberjack.integrations.langchain_splitter``: LumberjackTextSplitter,
  LumberjackDocumentTransformer
- ``lumberjack.integrations.haystack_splitter``: LumberjackDocumentSplitter
"""

from types import ModuleType
from typing import Any

from ._metadata import chunk_metadata
from .haystack import (
    build_haystack_document_store,
    to_haystack_document,
    to_haystack_documents,
)
from .langchain import (
    build_langchain_vectorstore,
    to_langchain_document,
    to_langchain_documents,
)
from .llama_index import build_llamaindex_index, to_llamaindex_node, to_llamaindex_nodes

_LAZY_EXPORTS = {
    "LumberjackDocumentSplitter": "haystack_splitter",
    "LumberjackDocumentTransformer": "langchain_splitter",
    "LumberjackNodeParser": "llama_index_pipeline",
    "LumberjackReader": "llama_index_pipeline",
    "LumberjackTextSplitter": "langchain_splitter",
}

__all__ = [
    "build_haystack_document_store",
    "build_langchain_vectorstore",
    "build_llamaindex_index",
    "chunk_metadata",
    "to_haystack_document",
    "to_haystack_documents",
    "to_langchain_document",
    "to_langchain_documents",
    "to_llamaindex_node",
    "to_llamaindex_nodes",
    *_LAZY_EXPORTS,
]


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module: ModuleType = importlib.import_module(f".{module_name}", __package__)
    return getattr(module, name)

"""Conversions to LlamaIndex nodes without a core LlamaIndex dependency."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lumberjack.models import Chunk

from ._metadata import chunk_metadata, metadata_keys


def to_llamaindex_node(chunk: Chunk) -> Any:
    """Convert one chunk to a ``llama_index.core.schema.TextNode``.

    Metadata is retained for filters and provenance but excluded from both
    embedding and LLM text, leaving ``Chunk.body`` as the sole main content.
    """
    try:
        from llama_index.core.schema import TextNode
    except ModuleNotFoundError as error:
        raise ImportError(
            "LlamaIndex integration requires `pip install lumberjack-py[llama-index]`."
        ) from error
    metadata = chunk_metadata(chunk)
    excluded_keys = metadata_keys(metadata)
    return TextNode(
        id_=chunk.chunk_id,
        text=chunk.body,
        metadata=metadata,
        excluded_embed_metadata_keys=excluded_keys,
        excluded_llm_metadata_keys=excluded_keys,
    )


def to_llamaindex_nodes(chunks: Iterable[Chunk]) -> list[Any]:
    """Convert chunks to LlamaIndex nodes in input order."""
    return [to_llamaindex_node(chunk) for chunk in chunks]


def build_llamaindex_index(chunks: Iterable[Chunk], **kwargs: Any) -> Any:
    """Build a real ``VectorStoreIndex`` directly from Lumberjack chunks.

    Forward LlamaIndex construction options such as ``embed_model``,
    ``storage_context``, and ``transformations`` through ``kwargs``.  This
    keeps embedding, storage, and query-engine choices under the caller's
    normal LlamaIndex configuration while providing a ready-to-retrieve index.
    """
    try:
        from llama_index.core import VectorStoreIndex
    except ModuleNotFoundError as error:
        raise ImportError(
            "LlamaIndex integration requires `pip install lumberjack-py[llama-index]`."
        ) from error
    return VectorStoreIndex(nodes=to_llamaindex_nodes(chunks), **kwargs)

"""Conversions to Haystack documents without a core Haystack dependency."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lumberjack.models import Chunk

from ._metadata import chunk_metadata


def to_haystack_document(chunk: Chunk) -> Any:
    """Convert one chunk to a ``haystack.Document``."""
    try:
        from haystack import Document
    except ModuleNotFoundError as error:
        raise ImportError(
            "Haystack integration requires `pip install lumberjack-py[haystack]`."
        ) from error
    return Document(id=chunk.chunk_id, content=chunk.body, meta=chunk_metadata(chunk))


def to_haystack_documents(chunks: Iterable[Chunk]) -> list[Any]:
    """Convert chunks to Haystack documents in input order."""
    return [to_haystack_document(chunk) for chunk in chunks]


def build_haystack_document_store(chunks: Iterable[Chunk]) -> Any:
    """Write Lumberjack chunks to a ready-to-query Haystack document store."""
    try:
        from haystack.document_stores.in_memory import InMemoryDocumentStore
    except ModuleNotFoundError as error:
        raise ImportError(
            "Haystack integration requires `pip install lumberjack-py[haystack]`."
        ) from error
    document_store = InMemoryDocumentStore()
    document_store.write_documents(to_haystack_documents(chunks))
    return document_store

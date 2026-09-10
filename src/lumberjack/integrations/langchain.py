"""Conversions to LangChain documents without a core LangChain dependency."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lumberjack.models import Chunk

from ._metadata import chunk_metadata


def to_langchain_document(chunk: Chunk) -> Any:
    """Convert one chunk to ``langchain_core.documents.Document``."""
    try:
        from langchain_core.documents import Document
    except ModuleNotFoundError as error:
        raise ImportError(
            "LangChain integration requires `pip install lumberjack-py[langchain]`."
        ) from error
    return Document(
        id=chunk.chunk_id,
        page_content=chunk.body,
        metadata=chunk_metadata(chunk),
    )


def to_langchain_documents(chunks: Iterable[Chunk]) -> list[Any]:
    """Convert chunks to LangChain documents in input order."""
    return [to_langchain_document(chunk) for chunk in chunks]


def build_langchain_vectorstore(chunks: Iterable[Chunk], *, embeddings: Any) -> Any:
    """Build an in-memory LangChain vector store from Lumberjack chunks."""
    try:
        from langchain_core.vectorstores import InMemoryVectorStore
    except ModuleNotFoundError as error:
        raise ImportError(
            "LangChain integration requires `pip install lumberjack-py[langchain]`."
        ) from error
    vectorstore = InMemoryVectorStore(embedding=embeddings)
    vectorstore.add_documents(to_langchain_documents(chunks))
    return vectorstore

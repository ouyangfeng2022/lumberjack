from __future__ import annotations

import pytest

from lumberjack import Lumberjack
from lumberjack.models import Chunk


@pytest.fixture
def chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk-0001",
        body="Body only",
        ancestor_headings=((1, "Guide"),),
        own_heading=(2, "Adapters"),
    )


def test_langchain_conversion(chunk: Chunk) -> None:
    pytest.importorskip("langchain_core")
    from lumberjack.integrations import to_langchain_document, to_langchain_documents

    document = to_langchain_document(chunk)
    assert document.id == chunk.chunk_id
    assert document.page_content == chunk.body
    assert document.metadata["own_heading"] == [2, "Adapters"]
    assert to_langchain_documents([chunk])[0] == document


def test_langchain_vectorstore_retrieves_lumberjack_chunks() -> None:
    pytest.importorskip("langchain_core")
    from langchain_core.embeddings import DeterministicFakeEmbedding

    from lumberjack.integrations import build_langchain_vectorstore

    chunk = (
        Lumberjack().saw("# Guide\n\nLumberjack preserves source provenance.").chunks[0]
    )
    vectorstore = build_langchain_vectorstore(
        [chunk], embeddings=DeterministicFakeEmbedding(size=8)
    )

    retrieved = vectorstore.similarity_search("source provenance", k=1)
    assert retrieved[0].id == chunk.chunk_id
    assert retrieved[0].page_content == chunk.body
    assert retrieved[0].metadata["source_locations"][0]["line_start"] == 3


def test_llamaindex_conversion(chunk: Chunk) -> None:
    pytest.importorskip("llama_index.core")
    from lumberjack.integrations import to_llamaindex_node, to_llamaindex_nodes

    node = to_llamaindex_node(chunk)
    assert node.node_id == chunk.chunk_id
    assert node.text == chunk.body
    assert node.metadata["ancestor_headings"] == [[1, "Guide"]]
    assert node.excluded_embed_metadata_keys == list(node.metadata)
    assert node.excluded_llm_metadata_keys == list(node.metadata)
    assert to_llamaindex_nodes([chunk])[0] == node


def test_llamaindex_index_retrieval_and_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("llama_index.core")
    from llama_index.core.embeddings import MockEmbedding
    from llama_index.core.llms.mock import MockLLM

    from lumberjack.integrations import build_llamaindex_index

    class Encoding:
        def encode(self, text: str, **kwargs: object) -> list[int]:  # noqa: ARG002
            return list(text.encode("utf-8"))

    import tiktoken

    monkeypatch.setattr(tiktoken, "encoding_for_model", lambda _model: Encoding())

    chunk = (
        Lumberjack().saw("# Guide\n\nLumberjack preserves source provenance.").chunks[0]
    )
    index = build_llamaindex_index([chunk], embed_model=MockEmbedding(embed_dim=8))

    retrieved = index.as_retriever(similarity_top_k=1).retrieve("source provenance")
    assert [item.node_id for item in retrieved] == [chunk.chunk_id]
    assert retrieved[0].text == chunk.body

    response = index.as_query_engine(llm=MockLLM(), similarity_top_k=1).query(
        "What does Lumberjack preserve?"
    )
    assert chunk.body in str(response)


def test_haystack_conversion(
    chunk: Chunk, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    pytest.importorskip("haystack")
    from lumberjack.integrations import to_haystack_document, to_haystack_documents

    document = to_haystack_document(chunk)
    assert document.id == chunk.chunk_id
    assert document.content == chunk.body
    assert document.meta["chunk_id"] == chunk.chunk_id
    assert to_haystack_documents([chunk])[0] == document


def test_haystack_document_store_retrieves_lumberjack_chunks(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    pytest.importorskip("haystack")
    from haystack.components.retrievers.in_memory import InMemoryBM25Retriever

    from lumberjack.integrations import build_haystack_document_store

    chunk = (
        Lumberjack().saw("# Guide\n\nLumberjack preserves source provenance.").chunks[0]
    )
    document_store = build_haystack_document_store([chunk])
    retrieved = InMemoryBM25Retriever(document_store=document_store).run(
        query="source provenance"
    )["documents"]

    assert retrieved[0].id == chunk.chunk_id
    assert retrieved[0].content == chunk.body
    assert retrieved[0].meta["source_locations"][0]["line_start"] == 3

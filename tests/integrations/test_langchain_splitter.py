"""Native LangChain splitting components (TextSplitter + transformer)."""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_text_splitters")

from langchain_core.documents import Document as LangchainDocument

from lumberjack.integrations import (
    LumberjackDocumentTransformer,
    LumberjackTextSplitter,
)

MARKDOWN = "# Guide\n\nAlpha intro.\n\n## Setup\n\nInstall first."


def test_split_text_returns_structure_aware_chunks() -> None:
    splitter = LumberjackTextSplitter(max_tokens=64)
    assert splitter.split_text(MARKDOWN) == ["Alpha intro.", "Install first."]


def test_split_text_heading_context_prefixes_breadcrumbs() -> None:
    splitter = LumberjackTextSplitter(max_tokens=64, heading_context=True)
    assert splitter.split_text(MARKDOWN) == [
        "# Guide\n\nAlpha intro.",
        "# Guide\n\n## Setup\n\nInstall first.",
    ]


def test_create_documents_attaches_provenance_metadata() -> None:
    splitter = LumberjackTextSplitter(max_tokens=64)
    documents = splitter.create_documents(
        [MARKDOWN], metadatas=[{"file_path": "docs/x.md"}]
    )
    assert [document.page_content for document in documents] == [
        "Alpha intro.",
        "Install first.",
    ]
    assert documents[0].metadata["file_path"] == "docs/x.md"
    assert documents[0].metadata["own_heading"] == [1, "Guide"]
    assert documents[1].metadata["start_line"] == 7


def test_split_documents_preserves_source_metadata() -> None:
    splitter = LumberjackTextSplitter(max_tokens=64)
    documents = splitter.split_documents(
        [LangchainDocument(page_content=MARKDOWN, metadata={"source": "manual"})]
    )
    assert all(document.metadata["source"] == "manual" for document in documents)
    assert documents[1].metadata["own_heading"] == [2, "Setup"]


def test_transformer_emits_deterministic_incremental_ids() -> None:
    transformer = LumberjackDocumentTransformer(max_tokens=64)
    source = LangchainDocument(
        id="doc-1", page_content=MARKDOWN, metadata={"file_path": "x.md"}
    )
    documents = transformer.transform_documents([source])
    assert [document.id for document in documents] == [
        "doc-1:chunk-0001",
        "doc-1:chunk-0002",
    ]
    assert documents[0].metadata["file_path"] == "x.md"

    rerun = LumberjackDocumentTransformer(max_tokens=64).transform_documents([source])
    assert [document.id for document in rerun] == [
        "doc-1:chunk-0001",
        "doc-1:chunk-0002",
    ]


def test_components_reject_unknown_splitter_eagerly() -> None:
    with pytest.raises(ValueError, match="Unsupported splitter"):
        LumberjackTextSplitter(splitter="nonexistent")
    with pytest.raises(ValueError, match="Unsupported splitter"):
        LumberjackDocumentTransformer(splitter="nonexistent")


def test_transformer_supports_async_interface() -> None:
    import asyncio

    transformer = LumberjackDocumentTransformer(max_tokens=64)
    documents = asyncio.run(
        transformer.atransform_documents([LangchainDocument(page_content=MARKDOWN)])
    )
    assert [document.page_content for document in documents] == [
        "Alpha intro.",
        "Install first.",
    ]

"""Native Haystack splitting component."""

from __future__ import annotations

import pytest

pytest.importorskip("haystack")

from haystack import Pipeline
from haystack.dataclasses import Document as HaystackDocument

from lumberjack.integrations import LumberjackDocumentSplitter

MARKDOWN = "# Guide\n\nAlpha intro.\n\n## Setup\n\nInstall first."


def test_splitter_emits_chunks_with_merged_metadata() -> None:
    splitter = LumberjackDocumentSplitter(max_tokens=64)
    result = splitter.run(
        documents=[
            HaystackDocument(
                id="h1", content=MARKDOWN, meta={"file_path": "x.md", "lang": "en"}
            )
        ]
    )
    documents = result["documents"]
    assert [document.content for document in documents] == [
        "Alpha intro.",
        "Install first.",
    ]
    assert [document.id for document in documents] == [
        "h1:chunk-0001",
        "h1:chunk-0002",
    ]
    assert documents[0].meta["lang"] == "en"
    assert documents[0].meta["file_path"] == "x.md"
    assert documents[0].meta["own_heading"] == [1, "Guide"]
    assert documents[1].meta["start_line"] == 7


def test_splitter_heading_context_prefixes_breadcrumbs() -> None:
    splitter = LumberjackDocumentSplitter(max_tokens=64, heading_context=True)
    documents = splitter.run(
        documents=[HaystackDocument(id="h1", content=MARKDOWN, meta={})]
    )["documents"]
    assert documents[1].content == "# Guide\n\n## Setup\n\nInstall first."


def test_splitter_passes_contentless_documents_through() -> None:
    source = HaystackDocument(id="h2", content=None, meta={"kind": "route"})
    documents = LumberjackDocumentSplitter(max_tokens=64).run(documents=[source])[
        "documents"
    ]
    assert documents == [source]


def test_splitter_runs_inside_haystack_pipeline() -> None:
    pipeline = Pipeline()
    pipeline.add_component("split", LumberjackDocumentSplitter(max_tokens=64))
    result = pipeline.run(
        {"split": {"documents": [HaystackDocument(id="p1", content=MARKDOWN, meta={})]}}
    )
    assert [document.content for document in result["split"]["documents"]] == [
        "Alpha intro.",
        "Install first.",
    ]


def test_splitter_rejects_unknown_splitter_eagerly() -> None:
    with pytest.raises(ValueError, match="Unsupported splitter"):
        LumberjackDocumentSplitter(splitter="nonexistent")

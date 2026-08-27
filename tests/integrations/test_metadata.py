from __future__ import annotations

import json
from builtins import __import__ as builtin_import
from collections.abc import Callable
from functools import partial
from typing import Any

import pytest

from lumberjack.integrations import (
    build_haystack_document_store,
    build_langchain_vectorstore,
    build_llamaindex_index,
    chunk_metadata,
    to_haystack_document,
    to_langchain_document,
    to_llamaindex_node,
)
from lumberjack.models import Chunk, SourceLocation


@pytest.fixture
def chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk-0001",
        chunk_type="paragraph",
        body="Body only",
        token_count=12,
        estimated_token_count=11,
        headings_token_count=5,
        body_token_count=6,
        ancestor_headings=((1, "Guide"),),
        own_heading=(2, "Adapters"),
        section_level=2,
        document_title="Example",
        document_path="example.md",
        start_line=3,
        end_line=5,
        source_locations=(
            SourceLocation(source="example.md", line_start=3, line_end=5),
        ),
    )


def test_chunk_metadata_is_json_safe_and_preserves_provenance(chunk: Chunk) -> None:
    metadata = chunk_metadata(chunk)

    assert "body" not in metadata
    assert metadata["chunk_id"] == "chunk-0001"
    assert metadata["ancestor_headings"] == [[1, "Guide"]]
    assert metadata["own_heading"] == [2, "Adapters"]
    assert metadata["source_locations"] == [
        {
            "source": "example.md",
            "byte_start": None,
            "byte_end": None,
            "line_start": 3,
            "line_end": 5,
            "page_start": None,
            "page_end": None,
            "sheet": None,
            "row_start": None,
            "row_end": None,
            "column_start": None,
            "column_end": None,
            "json_path": None,
            "element_id": None,
            "bounding_box": None,
        }
    ]
    json.dumps(metadata)


@pytest.mark.parametrize(
    ("module", "converter", "extra"),
    [
        ("langchain_core", to_langchain_document, "langchain"),
        (
            "langchain_core",
            partial(build_langchain_vectorstore, embeddings=object()),
            "langchain",
        ),
        ("llama_index", to_llamaindex_node, "llama-index"),
        ("llama_index", build_llamaindex_index, "llama-index"),
        ("haystack", to_haystack_document, "haystack"),
        ("haystack", build_haystack_document_store, "haystack"),
    ],
)
def test_missing_framework_dependency_has_install_guidance(
    monkeypatch: pytest.MonkeyPatch,
    chunk: Chunk,
    module: str,
    converter: Callable[[Chunk], object],
    extra: str,
) -> None:
    def missing_framework(name: str, *args: Any, **kwargs: Any) -> object:
        if name == module or name.startswith(f"{module}."):
            raise ModuleNotFoundError(name=name)
        return builtin_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", missing_framework)
    with pytest.raises(ImportError, match=rf"lumberjack-py\[{extra}\]"):
        converter(chunk)

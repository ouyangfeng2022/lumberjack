from __future__ import annotations

import inspect
from dataclasses import fields

import pytest

from lumberjack import lumber
from lumberjack.core.models import Chunk, DocumentBlock, DocumentInline
from lumberjack.core.splitter import SPLITTER_REGISTRY, create_splitter


def test_lumber_public_defaults() -> None:
    parameters = inspect.signature(lumber).parameters

    assert parameters["format"].default == "auto"
    assert parameters["tokenizer"].default == "approx"
    assert parameters["splitter"].default == "sibling"
    assert parameters["max_tokens"].default == 1200
    assert parameters["ideal_max_tokens_ratio"].default == 0.8
    assert parameters["merge_below_ratio"].default == 0.125
    assert parameters["skip_empty_sections"].default is True
    assert parameters["render_headings"].default is True
    assert parameters["max_heading_level"].default is None


def test_chunk_serialization_fields() -> None:
    assert [field.name for field in fields(Chunk)] == [
        "chunk_id",
        "chunk_type",
        "body",
        "token_count",
        "estimated_token_count",
        "headings",
        "section_level",
        "document_title",
        "document_path",
        "start_line",
        "end_line",
    ]


def test_format_neutral_ast_node_names_are_public() -> None:
    assert DocumentInline.__name__ == "DocumentInline"
    assert DocumentBlock.__name__ == "DocumentBlock"


def test_splitter_registry_public_names() -> None:
    assert set(SPLITTER_REGISTRY) == {
        "sibling",
        "exact-sibling",
        "incremental-sibling",
        "subtree",
        "exact-subtree",
        "incremental-subtree",
        "section",
        "exact-section",
        "incremental-section",
    }

    for removed_name in ("recursive", "exact-recursive", "incremental-recursive"):
        with pytest.raises(ValueError, match="Unsupported splitter"):
            create_splitter(removed_name)

from __future__ import annotations

import inspect

from lumberjack.web.routes import ChunkResponse, TextSplitRequest, split_file


def test_text_request_defaults() -> None:
    fields = TextSplitRequest.model_fields

    assert fields["input_format"].default == "markdown"
    assert fields["tokenizer"].default == "approx"
    assert fields["splitter"].default == "sibling"
    assert fields["max_tokens"].default == 1200
    assert fields["ideal_max_tokens_ratio"].default == 0.8
    assert fields["merge_below_ratio"].default == 0.125
    assert fields["skip_empty_sections"].default is True
    assert fields["heading_sensitive"].default is True
    assert fields["max_heading_level"].default is None
    assert "only to encode and count" in (fields["tokenizer"].description or "")
    assert "counting mode" in (fields["splitter"].description or "")


def test_chunk_response_fields_match_serialized_chunk() -> None:
    assert list(ChunkResponse.model_fields) == [
        "chunk_id",
        "chunk_type",
        "body",
        "token_count",
        "estimated_token_count",
        "headings_token_count",
        "body_token_count",
        "ancestor_headings",
        "own_heading",
        "section_level",
        "document_title",
        "document_path",
        "start_line",
        "end_line",
    ]


def test_file_request_defaults() -> None:
    parameters = inspect.signature(split_file).parameters

    assert parameters["input_format"].default.default == "auto"
    assert parameters["tokenizer"].default.default == "approx"
    assert parameters["splitter"].default.default == "sibling"
    assert parameters["max_tokens"].default.default == 1200
    assert parameters["ideal_max_tokens_ratio"].default.default == 0.8
    assert parameters["merge_below_ratio"].default.default == 0.125
    assert parameters["skip_empty_sections"].default.default is True
    assert parameters["heading_sensitive"].default.default is True
    assert parameters["max_heading_level"].default.default is None

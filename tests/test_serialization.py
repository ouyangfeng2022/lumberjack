from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from lumberjack import Document, Lumberjack
from lumberjack.serialization import (
    chunk_from_dict,
    chunk_to_dict,
    doc_tree_from_dict,
    doc_tree_to_dict,
    split_result_to_dict,
)


def _schema(name: str) -> dict[str, object]:
    return json.loads((Path("schemas") / name).read_text(encoding="utf-8"))


def test_v1_payloads_validate_and_round_trip() -> None:
    result = Lumberjack().saw("# Guide\n\nBody")
    chunk_payload = split_result_to_dict(result)
    tree_payload = doc_tree_to_dict(result.document)

    Draft202012Validator(_schema("chunk-v1.schema.json")).validate(chunk_payload)
    Draft202012Validator(_schema("doc-tree-v1.schema.json")).validate(tree_payload)
    assert chunk_from_dict(chunk_to_dict(result.chunks[0])) == result.chunks[0]
    assert doc_tree_from_dict(tree_payload) == result.document


def test_saw_many_is_streaming_ordered_and_isolates_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.md"
    inputs = (
        document
        for document in [
            Document(source="# First", source_path="first.md"),
            Document(source=missing, source_path="missing.md"),
            Document(source="# Last", source_path="last.md"),
        ]
    )
    outcomes = list(Lumberjack().saw_many(inputs))

    assert [outcome.input_id for outcome in outcomes] == [
        "first.md",
        "missing.md",
        "last.md",
    ]
    assert outcomes[0].result is not None
    assert outcomes[1].result is None and outcomes[1].error is not None
    assert outcomes[2].result is not None

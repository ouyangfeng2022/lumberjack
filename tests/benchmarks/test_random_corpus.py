from __future__ import annotations

import hashlib
import random

import pytest

from benchmarks.random_corpus import (
    ADVERSARIAL_RATIO,
    FORMAT_SPECS,
    generate_documents,
)
from benchmarks.random_run import _parse_generated


def test_random_corpus_generation_is_deterministic() -> None:
    first = generate_documents(["html", "json", "xlsx"], seed=7, count_per_format=4)
    repeated = generate_documents(["html", "json", "xlsx"], seed=7, count_per_format=4)

    def digest(source: str | bytes) -> str:
        return hashlib.sha256(
            source.encode("utf-8") if isinstance(source, str) else source
        ).hexdigest()

    assert [
        (document.format, document.document_id, digest(document.source))
        for document in first
    ] == [
        (document.format, document.document_id, digest(document.source))
        for document in repeated
    ]
    other_seed = generate_documents(["html"], seed=8, count_per_format=4)
    assert {d.document_id for d in other_seed} != {
        d.document_id for d in first[:4]
    } or any(a.source != b.source for a, b in zip(other_seed, first, strict=False))


def test_random_corpus_rejects_unknown_formats() -> None:
    with pytest.raises(ValueError, match="unknown random corpus formats"):
        generate_documents(["nosuch"], seed=1, count_per_format=1)


def test_every_format_generates_parser_satisfying_documents() -> None:
    documents = generate_documents(
        sorted(FORMAT_SPECS), seed=20260825, count_per_format=6
    )

    assert {document.format for document in documents} == set(FORMAT_SPECS)
    adversarial = 0
    for document in documents:
        result = _parse_generated(document)
        if document.allowed_error_types:
            adversarial += 1
            assert result.status in {"success", "rejected"}, result.diagnostics
        else:
            assert result.status == "success", result.diagnostics
    assert adversarial >= len(documents) * ADVERSARIAL_RATIO * 0.5


def test_random_corpus_oracle_detects_element_count_regressions() -> None:
    from dataclasses import replace

    documents = generate_documents(["html"], seed=20260825, count_per_format=4)
    strict = next(d for d in documents if not d.allowed_error_types)
    damaged = replace(
        strict,
        required_elements=(*strict.required_elements, "block:list"),
    )

    result = _parse_generated(damaged)

    assert result.status == "invalid"
    assert any("element count mismatch" in item for item in result.diagnostics)


def test_random_corpus_oracle_detects_recall_regressions() -> None:
    from dataclasses import replace

    documents = generate_documents(["text"], seed=20260825, count_per_format=4)
    strict = next(d for d in documents if not d.allowed_error_types)
    damaged = replace(
        strict, reference_text=strict.reference_text + " vanished sentinel"
    )

    result = _parse_generated(damaged)

    assert result.status == "invalid"
    assert any("token recall" in item for item in result.diagnostics)


def test_random_corpus_adversarial_documents_declare_allowed_errors() -> None:
    documents = generate_documents(["csv", "xml"], seed=3, count_per_format=200)

    adversarial = [d for d in documents if d.allowed_error_types]
    assert adversarial
    assert all(d.min_token_recall == 0.0 for d in adversarial)
    assert all(not d.required_elements for d in adversarial)


def test_random_generator_survives_arbitrary_seed_streams() -> None:
    for seed in range(5):
        rng = random.Random(f"probe:{seed}".encode())
        for _name, spec in sorted(FORMAT_SPECS.items()):
            document = spec.generate(rng)
            if not document.allowed_error_types:
                assert document.source

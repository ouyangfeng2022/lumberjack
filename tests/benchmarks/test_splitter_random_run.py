from __future__ import annotations

from typing import Any

import pytest

from benchmarks.contract import BenchmarkChunk
from benchmarks.splitter_random_corpus import generate_documents
from benchmarks.splitter_random_run import (
    SPLITTER_CLASSES,
    SplitterRandomConfig,
    _evaluate_chunks,
    _measure_document,
    _tokenizer_template,
    _tree_reference_text,
    run_splitter_benchmark,
)
from lumberjack.models import Document
from lumberjack.parser.markdown import MarkdownParser


def _small_config(**overrides: Any) -> SplitterRandomConfig:
    defaults: dict[str, Any] = {
        "corpus": "synthetic",
        "shapes": ("deep-tree", "oversized-blocks"),
        "splitters": tuple(SPLITTER_CLASSES),
        "tokenizers": ("approx",),
        "documents_per_shape": 2,
        "recombined_documents": 1,
        "max_tokens": 200,
        "warmups": 0,
        "repetitions": 1,
        "memory_reps": 1,
        "seed": 99,
    }
    defaults.update(overrides)
    return SplitterRandomConfig(**defaults)


def test_small_synthetic_run_succeeds_for_all_variants() -> None:
    report = run_splitter_benchmark(_small_config())

    assert report.schema_version == "1.1"
    assert report.dataset_version == "generated"
    assert len(report.results) == 2 * 2 * 6
    failures = [result for result in report.results if result.status != "success"]
    assert not failures, [result.diagnostics for result in failures]
    assert report.summary["overall"]["failed"] == 0
    assert set(report.summary["by_tokenizer"]["approx"]["by_splitter"]) == set(
        SPLITTER_CLASSES
    )
    assert set(report.summary["pairwise"]["approx"]) == {
        "section",
        "subtree",
        "sibling",
    }
    assert set(report.summary["by_dataset"]) == {
        "synthetic-deep-tree",
        "synthetic-oversized-blocks",
    }


def test_exact_splitters_report_zero_estimate_error() -> None:
    report = run_splitter_benchmark(
        _small_config(splitters=("exact-section", "exact-sibling"))
    )

    assert len(report.results) == 8
    for result in report.results:
        assert result.status == "success"
        assert result.chunk_count >= 1
        assert result.estimate_abs_error_max == 0.0
        assert all(observation.abs_estimate_error == 0 for observation in result.chunks)


def test_incremental_estimate_error_is_quantified() -> None:
    report = run_splitter_benchmark(_small_config(splitters=("incremental-section",)))

    for result in report.results:
        assert result.status == "success"
        assert result.estimate_abs_error_max >= 0
        assert result.estimate_abs_error_mean >= 0.0
        assert len(result.chunks) == result.chunk_count
        assert result.split_samples[0].draft_count >= 1


def test_memory_peaks_measured_per_phase() -> None:
    report = run_splitter_benchmark(
        _small_config(
            splitters=("exact-section", "incremental-section"),
            memory_reps=2,
        )
    )

    assert report.summary["overall"]["failed"] == 0
    for result in report.results:
        assert result.split_peak_memory_bytes > 0
        assert result.total_peak_memory_bytes >= result.split_peak_memory_bytes
    by_splitter = report.summary["by_tokenizer"]["approx"]["by_splitter"]
    for splitter in ("exact-section", "incremental-section"):
        assert by_splitter[splitter]["split_peak_memory_bytes_median"] > 0
        assert by_splitter[splitter]["total_peak_memory_bytes_median"] > 0


def test_memory_reps_zero_disables_memory_measurement() -> None:
    report = run_splitter_benchmark(
        _small_config(splitters=("exact-section",), memory_reps=0)
    )

    for result in report.results:
        assert result.split_peak_memory_bytes == 0
        assert result.total_peak_memory_bytes == 0


def test_config_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown splitters"):
        SplitterRandomConfig(corpus="synthetic", splitters=("nope",))
    with pytest.raises(ValueError, match="unknown shapes"):
        SplitterRandomConfig(corpus="synthetic", shapes=("nope",))
    with pytest.raises(ValueError, match="unknown tokenizer engines"):
        SplitterRandomConfig(corpus="synthetic", tokenizers=("nope",))
    with pytest.raises(ValueError, match="max_tokens must be positive"):
        SplitterRandomConfig(corpus="synthetic", max_tokens=0)


def test_evaluate_chunks_flags_missing_sentinel_and_low_recall() -> None:
    document = generate_documents(
        ["wide-flat"], seed=3, count_per_shape=1, budget_tokens=200
    )[0]
    chunks = [
        BenchmarkChunk(
            text="unrelated text only", token_count=5, estimated_token_count=5
        )
    ]

    values, diagnostics, recall = _evaluate_chunks(
        chunks, document, "reference words alpha beta", max_tokens=200
    )

    assert any("missing required content" in item for item in diagnostics)
    assert recall is not None and recall < 0.99
    assert any("word recall" in item for item in diagnostics)
    assert values["content_recall"] == 0.0


def test_evaluate_chunks_flags_split_protected_content() -> None:
    document = generate_documents(
        ["oversized-blocks"], seed=4, count_per_shape=1, budget_tokens=150
    )[0]
    assert document.protected_content
    sentinel = document.protected_content[0]
    chunks = [
        BenchmarkChunk(
            text=f"prefix {sentinel} suffix", token_count=6, estimated_token_count=6
        ),
        BenchmarkChunk(
            text=f"other {sentinel} chunk", token_count=6, estimated_token_count=6
        ),
    ]

    _, diagnostics, recall = _evaluate_chunks(chunks, document, "", max_tokens=150)

    assert any("protected content appears in 2 chunks" in item for item in diagnostics)
    assert recall is None


def test_oversized_code_fences_split_within_budget_by_default() -> None:
    document = next(
        candidate
        for seed in range(20)
        for candidate in generate_documents(
            ["oversized-blocks"], seed=seed, count_per_shape=1, budget_tokens=150
        )
        if candidate.profile["max_code_fence_tokens"] > 150
    )
    config = _small_config(
        shapes=("oversized-blocks",),
        splitters=("exact-section",),
        documents_per_shape=1,
        max_tokens=150,
    )
    tree = MarkdownParser().parse(
        Document(
            source=document.source,
            format="markdown",
            document_title=document.document_id,
        )
    )
    result = _measure_document(
        document=document,
        tree=tree,
        reference=_tree_reference_text(tree),
        template=_tokenizer_template("approx"),
        engine_name="approx",
        splitter_name="exact-section",
        config=config,
    )

    # Default block options split oversized fences, so every chunk fits the
    # budget, nothing is protected, and the fence sentinel survives whole in
    # exactly one chunk (guarded by the success status).
    assert result.status == "success"
    assert result.chunk_count >= 2
    assert all(observation.token_count <= 150 for observation in result.chunks)
    assert all(not observation.protected for observation in result.chunks)
    assert all(not observation.exceeds_budget for observation in result.chunks)

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.parser_contract import ParserBenchmarkConfig
from benchmarks.parser_run import discover_documents, run_parser_benchmark
from tests.helpers import FIXTURES_DIR


def _write_manifest(path: Path, sources: list[dict[str, object]]) -> Path:
    manifest = path / "manifest.json"
    manifest.write_text(
        json.dumps({"dataset_version": "test", "sources": sources}),
        encoding="utf-8",
    )
    return manifest


def _git_source(source_id: str, source_format: str, pattern: str) -> dict[str, object]:
    return {
        "id": source_id,
        "kind": "git",
        "format": source_format,
        "include": [pattern],
    }


def test_parser_corpus_sampling_is_seeded_per_source(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    source_root = corpus_root / "markdown"
    source_root.mkdir(parents=True)
    for index in range(20):
        (source_root / f"document-{index:02d}.md").write_text(
            f"# Document {index}\n\nbody {index}\n",
            encoding="utf-8",
        )
    manifest = _write_manifest(
        tmp_path,
        [_git_source("markdown", "markdown", "*.md")],
    )

    first = discover_documents(
        corpus_root,
        ParserBenchmarkConfig(seed=7, sample_size_per_source=6),
        manifest_path=manifest,
    )
    repeated = discover_documents(
        corpus_root,
        ParserBenchmarkConfig(seed=7, sample_size_per_source=6),
        manifest_path=manifest,
    )
    other_seed = discover_documents(
        corpus_root,
        ParserBenchmarkConfig(seed=8, sample_size_per_source=6),
        manifest_path=manifest,
    )

    assert first[1:3] == repeated[1:3]
    assert [item.document_id for item in first[3]] == [
        item.document_id for item in repeated[3]
    ]
    assert [item.document_id for item in first[3]] != [
        item.document_id for item in other_seed[3]
    ]
    assert first[1] == {"markdown": 20}
    assert first[2] == {"markdown": 6}


def test_parser_corpus_discovery_rejects_escaping_source_paths(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [_git_source("../outside", "markdown", "*.md")],
    )

    with pytest.raises(ValueError, match="escapes its root"):
        discover_documents(
            tmp_path / "corpus",
            ParserBenchmarkConfig(),
            manifest_path=manifest,
        )


def test_parser_benchmark_preserves_successes_failures_and_raw_evidence(
    tmp_path: Path,
) -> None:
    corpus_root = tmp_path / "corpus"
    markdown_root = corpus_root / "markdown"
    docx_root = corpus_root / "docx"
    markdown_root.mkdir(parents=True)
    docx_root.mkdir(parents=True)
    (markdown_root / "sample.md").write_text(
        "# Heading\n\nContent with [link](https://example.com).\n",
        encoding="utf-8",
    )
    (docx_root / "valid.docx").write_bytes(
        (FIXTURES_DIR / "docx" / "sample.docx").read_bytes()
    )
    (docx_root / "broken.docx").write_bytes(b"not a package")
    manifest = _write_manifest(
        tmp_path,
        [
            _git_source("markdown", "markdown", "*.md"),
            _git_source("docx", "docx", "*.docx"),
        ],
    )

    report = run_parser_benchmark(
        ParserBenchmarkConfig(sample_size_per_source=0),
        corpus_root=corpus_root,
        manifest_path=manifest,
    )

    assert len(report.results) == 3
    assert {result.status for result in report.results} == {"success", "error"}
    assert all(len(result.sha256) == 64 for result in report.results)
    assert (
        next(
            result for result in report.results if result.format == "markdown"
        ).source_token_count
        > 0
    )
    assert report.summary["overall"]["documents"] == 3
    assert report.summary["overall"]["successful"] == 2
    assert report.summary["by_format"]["markdown"]["content_token_recall_min"] == 1.0
    failure = next(result for result in report.results if result.status == "error")
    assert failure.error_type == "BadZipFile"
    assert failure.error_message


def test_parser_benchmark_expands_commonmark_json_examples(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    source_root = corpus_root / "commonmark"
    source_root.mkdir(parents=True)
    payload = json.dumps(
        [
            {"example": 1, "markdown": "# one\n", "html": "<h1>one</h1>\n"},
            {"example": 2, "markdown": "- two\n", "html": "<ul><li>two</li></ul>\n"},
        ]
    ).encode()
    (source_root / "spec.json").write_bytes(payload)
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "id": "commonmark",
                "kind": "commonmark-json",
                "format": "markdown",
                "target": "spec.json",
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
    )

    report = run_parser_benchmark(
        ParserBenchmarkConfig(sample_size_per_source=0),
        corpus_root=corpus_root,
        manifest_path=manifest,
    )

    assert report.candidates_by_source == {"commonmark": 2}
    assert [result.document_id for result in report.results] == [
        "example-0001",
        "example-0002",
    ]
    assert report.summary["overall"]["success_rate"] == 1.0
    assert report.summary["overall"]["content_token_recall_min"] == 1.0


def test_parser_benchmark_checks_required_and_forbidden_elements(
    tmp_path: Path,
) -> None:
    cases = [
        {
            "id": "math",
            "source": "$ a+b=c$",
            "required_elements": ["block:paragraph", "inline:math_inline"],
            "forbidden_elements": ["block:math_block"],
        },
        {
            "id": "deliberate-mismatch",
            "source": "plain text",
            "required_elements": ["inline:math_inline"],
        },
    ]
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "id": "elements",
                "kind": "local-cases-json",
                "format": "markdown",
                "target": "cases.json",
            }
        ],
    )

    report = run_parser_benchmark(
        ParserBenchmarkConfig(sample_size_per_source=0),
        corpus_root=tmp_path / "unused",
        manifest_path=manifest,
    )

    assert [result.status for result in report.results] == ["success", "invalid"]
    assert report.results[0].element_accuracy == 1.0
    assert report.results[1].element_accuracy == 0.0
    assert report.summary["overall"]["element_assertions"] == 4
    assert report.summary["overall"]["passed_element_assertions"] == 3
    assert report.summary["overall"]["element_accuracy"] == 0.75

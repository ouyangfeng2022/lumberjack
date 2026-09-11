"""Contract tests for the multi-run comparison aggregator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmarks.compare import PROVENANCE_NOTE, _render_markdown, compare
from benchmarks.run import ROOT


def _manifest_ids(count: int) -> list[str]:
    manifest = json.loads(
        (ROOT / "datasets" / "manifest.json").read_text(encoding="utf-8")
    )
    return [item["id"] for item in manifest["documents"][:count]]


def _raw(
    adapter: str,
    document_ids: list[str],
    *,
    recall: float = 1.0,
    budget_violation: float = 0.0,
    estimate: int | None = None,
    max_tokens: int = 240,
) -> dict[str, Any]:
    results = []
    for document_id in document_ids:
        chunks = [
            {"text": "alpha", "token_count": 10, "estimated_token_count": estimate},
            {"text": "beta", "token_count": 20, "estimated_token_count": estimate},
        ]
        quality = {
            "content_recall": recall,
            "duplication_rate": 0.0,
            "budget_violation_rate": budget_violation,
            "block_break_rate": 0.0,
            "chunk_utilization": 0.5,
            "estimate_error": 0.0,
            "provenance_coverage": 1.0 if adapter == "lumberjack" else 0.0,
            "wall_time_seconds_median": 0.01,
            "peak_memory_bytes_median": 1_000.0,
            "count_calls_median": 4.0,
        }
        results.append(
            {
                "document_id": document_id,
                "adapter": adapter,
                "chunks": chunks,
                "samples": [],
                "quality": quality,
                "diagnostics": [] if adapter == "lumberjack" else [PROVENANCE_NOTE],
            }
        )
    return {
        "schema_version": "1.0",
        "commit": "a" * 40,
        "generated_at": "2026-09-03T00:00:00+00:00",
        "environment": {"python": "test"},
        "config": {
            "tokenizer": "approx",
            "splitter": "section",
            "max_tokens": max_tokens,
            "warmups": 1,
            "repetitions": 5,
        },
        "dataset_version": "2026.08.27",
        "results": results,
    }


def _write_run(directory: Path, name: str, raw: dict[str, Any]) -> None:
    run_dir = directory / name
    run_dir.mkdir(parents=True)
    (run_dir / "raw.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )


def test_compare_aggregates_runs_scenarios_and_markdown(tmp_path: Path) -> None:
    ids = _manifest_ids(4)
    _write_run(tmp_path, "lumberjack", _raw("lumberjack", ids, estimate=12))
    _write_run(tmp_path, "chonkie-recursive", _raw("chonkie-recursive", ids))

    summary, failures = compare(tmp_path)

    assert failures == []
    native = summary["runs"]["lumberjack"]
    competitor = summary["runs"]["chonkie-recursive"]
    assert native["quality_mean"]["content_recall"] == 1.0
    assert native["chunk_total"] == 8
    assert native["estimate_error"] == 0.0
    assert native["estimate_samples"] == 8
    assert competitor["estimate_error"] is None
    assert native["count_calls_total_median"] == 16.0
    assert native["throughput_mb_per_second"] > 0.0
    assert native["scenarios"], "scenario aggregation should use manifest scenarios"
    assert summary["documents_per_run"] == 4
    assert summary["commit"] == "a" * 40

    markdown = _render_markdown(summary["runs"])
    assert "| `lumberjack` |" in markdown
    assert "| `chonkie-recursive` |" in markdown
    assert "## Per-scenario quality" in markdown


def test_compare_fails_on_native_oracle_violations(tmp_path: Path) -> None:
    ids = _manifest_ids(2)
    _write_run(
        tmp_path,
        "lumberjack",
        _raw("lumberjack", ids, recall=0.5, budget_violation=0.5),
    )

    summary, failures = compare(tmp_path)

    assert any("content_recall" in failure for failure in failures)
    assert not any("mismatch" in failure for failure in failures)
    assert summary["failures"] == failures


def test_compare_flags_budget_and_dataset_mismatches(tmp_path: Path) -> None:
    ids = _manifest_ids(2)
    _write_run(tmp_path, "lumberjack", _raw("lumberjack", ids))
    _write_run(tmp_path, "other-budget", _raw("chonkie-recursive", ids, max_tokens=120))
    mismatched = _raw("chonkie-recursive", ids)
    mismatched["dataset_version"] = "1999.01.01"
    _write_run(tmp_path, "other-dataset", mismatched)

    _, failures = compare(tmp_path)

    assert any("max_tokens mismatch" in failure for failure in failures)
    assert any("dataset version mismatch" in failure for failure in failures)


def test_compare_requires_at_least_one_run(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        compare(tmp_path)
    except SystemExit as error:
        assert "no runs" in str(error)
    else:
        raise AssertionError("compare should exit when the directory has no runs")

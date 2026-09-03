"""Aggregate multi-adapter benchmark runs into one comparison summary.

Reads every ``raw.json`` under per-run subdirectories of a results directory
(the layout produced by ``benchmarks.run --output <dir>/<run>``), aggregates
quality and performance metrics across documents and scenarios, and writes
``summary.json`` plus a ``comparison.md`` table source. Native ``lumberjack``
runs are gated by content/structure oracles; the process exits non-zero when
one fails, mirroring the splitter random benchmark.

Example:
    uv run python -m benchmarks.run --adapter lumberjack \\
        --output benchmarks/results/20260903-abcdef123456/lumberjack
    uv run python -m benchmarks.compare benchmarks/results/20260903-abcdef123456
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Iterable
from pathlib import Path
from statistics import quantiles
from typing import Any

from benchmarks.run import ROOT

QUALITY_METRICS = (
    "content_recall",
    "duplication_rate",
    "budget_violation_rate",
    "block_break_rate",
    "chunk_utilization",
    "provenance_coverage",
)
# Standard note attached by ``benchmarks.run`` to every non-native adapter;
# it is a comparability statement, not an oracle diagnostic.
PROVENANCE_NOTE = (
    "adapter output has no normalized source-line provenance; "
    "provenance coverage is not directly comparable"
)


def _percentile(values: list[int], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    return quantiles(values, n=100, method="inclusive")[percentile - 1]


def _mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return statistics.fmean(materialized) if materialized else 0.0


def _scenario_map() -> dict[str, str]:
    manifest = json.loads(
        (ROOT / "datasets" / "manifest.json").read_text(encoding="utf-8")
    )
    return {
        item["id"]: item.get("scenario", "unknown") for item in manifest["documents"]
    }


def _corpus_bytes(document_ids: list[str]) -> int:
    manifest = json.loads(
        (ROOT / "datasets" / "manifest.json").read_text(encoding="utf-8")
    )
    by_id = {item["id"]: item["path"] for item in manifest["documents"]}
    total = 0
    for document_id in document_ids:
        path = by_id.get(document_id)
        if path is not None:
            total += (ROOT / "datasets" / path).stat().st_size
    return total


def _aggregate_run(raw: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = raw["results"]
    quality_means = {
        metric: _mean(
            float(item["quality"].get(metric, 0.0))
            for item in results
            if metric in item["quality"]
        )
        for metric in QUALITY_METRICS
    }
    tokens = [int(chunk["token_count"]) for item in results for chunk in item["chunks"]]
    estimate_samples = sum(
        1
        for item in results
        for chunk in item["chunks"]
        if chunk.get("estimated_token_count") is not None
    )
    estimate_error = _mean(
        float(item["quality"]["estimate_error"])
        for item in results
        if "estimate_error" in item["quality"] and estimate_samples > 0
    )
    oracle_diagnostics = [
        message
        for item in results
        for message in item.get("diagnostics", [])
        if message != PROVENANCE_NOTE
    ]
    wall_medians = [
        float(item["quality"]["wall_time_seconds_median"])
        for item in results
        if "wall_time_seconds_median" in item["quality"]
    ]
    peak_medians = [
        float(item["quality"]["peak_memory_bytes_median"])
        for item in results
        if "peak_memory_bytes_median" in item["quality"]
    ]
    document_ids = [item["document_id"] for item in results]
    total_wall = sum(wall_medians)
    corpus_bytes = _corpus_bytes(document_ids)
    return {
        "adapter": results[0]["adapter"]
        if results
        else raw.get("config", {}).get("splitter", "unknown"),
        "config": raw["config"],
        "commit": raw["commit"],
        "dataset_version": raw["dataset_version"],
        "generated_at": raw["generated_at"],
        "documents": len(results),
        "quality_mean": quality_means,
        "estimate_error": estimate_error if estimate_samples else None,
        "estimate_samples": estimate_samples,
        "token_p50": _percentile(tokens, 50),
        "token_p95": _percentile(tokens, 95),
        "chunk_total": len(tokens),
        "wall_total_median_seconds": total_wall,
        "wall_mean_per_document_ms": (
            _mean(wall_medians) * 1000 if wall_medians else 0.0
        ),
        "throughput_mb_per_second": (
            corpus_bytes / 1_000_000 / total_wall if total_wall else 0.0
        ),
        "peak_memory_median_max_bytes": max(peak_medians) if peak_medians else 0.0,
        "count_calls_total_median": sum(
            float(item["quality"].get("count_calls_median", 0.0)) for item in results
        ),
        "oracle_diagnostics_count": len(oracle_diagnostics),
        "oracle_diagnostics_samples": sorted(set(oracle_diagnostics))[:5],
    }


def _aggregate_scenarios(raw: dict[str, Any]) -> dict[str, dict[str, float]]:
    scenarios: dict[str, list[dict[str, float]]] = {}
    mapping = _scenario_map()
    for item in raw["results"]:
        scenario = mapping.get(item["document_id"], "unknown")
        scenarios.setdefault(scenario, []).append(
            {
                metric: float(item["quality"].get(metric, 0.0))
                for metric in QUALITY_METRICS
            }
        )
    return {
        scenario: {
            metric: _mean(row[metric] for row in rows) for metric in QUALITY_METRICS
        }
        for scenario, rows in sorted(scenarios.items())
    }


def _fmt(value: float | None, kind: str = "ratio") -> str:
    if value is None:
        return "—"
    if kind == "ratio":
        return f"{value:.3f}"
    if kind == "percent":
        return f"{value * 100:.1f}%"
    if kind == "seconds":
        return f"{value:.3f} s"
    if kind == "ms":
        return f"{value:.1f} ms"
    if kind == "mb":
        return f"{value / 1_000_000:.1f} MB"
    if kind == "int":
        return f"{int(value)}"
    return f"{value:.3f}"


def _render_markdown(runs: dict[str, dict[str, Any]]) -> str:
    lines: list[str] = []
    first = next(iter(runs.values()))
    lines.append(f"# Benchmark comparison ({first['commit'][:12]})")
    lines.append("")
    lines.append(f"- dataset version: `{first['dataset_version']}`")
    lines.append(f"- documents per run: {first['documents']}")
    for name, run in runs.items():
        config = run["config"]
        lines.append(
            f"- `{name}`: adapter `{run['adapter']}`, "
            f"splitter `{config.get('splitter', '—')}`, tokenizer "
            f"`{config.get('tokenizer', '—')}`, max_tokens "
            f"{config.get('max_tokens', '—')}"
        )
    lines.append("")

    lines.append("## Quality (mean across documents)")
    lines.append("")
    header = (
        "| run | content_recall | duplication | budget_violation | block_break | "
        "utilization | estimate_error | provenance | chunks | token p50/p95 |"
    )
    lines.append(header)
    lines.append("|" + " --- |" * 9 + " --- |")
    for name, run in runs.items():
        quality = run["quality_mean"]
        lines.append(
            f"| `{name}` | {_fmt(quality['content_recall'])} | "
            f"{_fmt(quality['duplication_rate'])} | "
            f"{_fmt(quality['budget_violation_rate'])} | "
            f"{_fmt(quality['block_break_rate'])} | "
            f"{_fmt(quality['chunk_utilization'])} | "
            f"{_fmt(run['estimate_error'])} | "
            f"{_fmt(quality['provenance_coverage'])} | "
            f"{_fmt(run['chunk_total'], 'int')} | "
            f"{_fmt(run['token_p50'], 'int')} / {_fmt(run['token_p95'], 'int')} |"
        )
    lines.append("")

    lines.append("## Performance (medians)")
    lines.append("")
    lines.append(
        "| run | total wall | mean per doc | throughput | peak alloc | count calls |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for name, run in runs.items():
        lines.append(
            f"| `{name}` | {_fmt(run['wall_total_median_seconds'], 'seconds')} | "
            f"{_fmt(run['wall_mean_per_document_ms'], 'ms')} | "
            f"{_fmt(run['throughput_mb_per_second'])} MB/s | "
            f"{_fmt(run['peak_memory_median_max_bytes'], 'mb')} | "
            f"{_fmt(run['count_calls_total_median'], 'int')} |"
        )
    lines.append("")

    scenarios = next(iter(runs.values())).get("scenarios", {})
    if scenarios:
        lines.append("## Per-scenario quality (mean across documents)")
        lines.append("")
        for scenario in sorted(scenarios):
            lines.append(f"### {scenario}")
            lines.append("")
            lines.append(
                "| run | content_recall | duplication | budget_violation | "
                "block_break | utilization |"
            )
            lines.append("|" + " --- |" * 6)
            for name, run in runs.items():
                row = run["scenarios"].get(scenario)
                if row is None:
                    continue
                lines.append(
                    f"| `{name}` | {_fmt(row['content_recall'])} | "
                    f"{_fmt(row['duplication_rate'])} | "
                    f"{_fmt(row['budget_violation_rate'])} | "
                    f"{_fmt(row['block_break_rate'])} | "
                    f"{_fmt(row['chunk_utilization'])} |"
                )
            lines.append("")
    return "\n".join(lines) + "\n"


def _native_oracle_failures(run: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    quality = run["quality_mean"]
    if quality["content_recall"] < 1.0:
        failures.append("content_recall below 1.0")
    if quality["block_break_rate"] > 0.0:
        failures.append("protected blocks broken across chunks")
    if quality["budget_violation_rate"] > 0.0:
        failures.append("non-protected chunks exceed max_tokens")
    return failures


def compare(results_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """Aggregate every run directory; return (summary, failures)."""
    run_dirs = sorted(
        path for path in results_dir.iterdir() if (path / "raw.json").is_file()
    )
    if not run_dirs:
        raise SystemExit(f"no runs with raw.json found under {results_dir}")

    runs: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    environment: dict[str, Any] | None = None
    for run_dir in run_dirs:
        raw = json.loads((run_dir / "raw.json").read_text(encoding="utf-8"))
        if environment is None:
            environment = raw.get("environment", {})
        elif raw.get("environment") != environment:
            failures.append(f"{run_dir.name}: environment differs from first run")
        aggregate = _aggregate_run(raw)
        aggregate["scenarios"] = _aggregate_scenarios(raw)
        runs[run_dir.name] = aggregate
        if aggregate["adapter"] == "lumberjack":
            failures.extend(
                f"{run_dir.name}: {failure}"
                for failure in _native_oracle_failures(aggregate)
            )

    reference = next(iter(runs.values()))
    for name, run in runs.items():
        if run["dataset_version"] != reference["dataset_version"]:
            failures.append(f"{name}: dataset version mismatch")
        if run["config"]["max_tokens"] != reference["config"]["max_tokens"]:
            failures.append(f"{name}: max_tokens mismatch")

    summary = {
        "schema_version": "1.0",
        "commit": reference["commit"],
        "dataset_version": reference["dataset_version"],
        "environment": environment,
        "documents_per_run": reference["documents"],
        "runs": runs,
        "failures": failures,
    }
    return summary, failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate benchmark runs into a comparison summary."
    )
    parser.add_argument("results_dir", type=Path)
    args = parser.parse_args()

    summary, failures = compare(args.results_dir)
    (args.results_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.results_dir / "comparison.md").write_text(
        _render_markdown(summary["runs"]), encoding="utf-8"
    )
    print(args.results_dir / "summary.json")
    for failure in failures:
        print(f"FAILURE: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

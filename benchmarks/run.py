"""CLI for repeatable Lumberjack benchmark runs.

Example:
    uv run python -m benchmarks.run --adapter lumberjack --splitter section
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.adapters.base import AdapterUnavailable, BenchmarkAdapter
from benchmarks.adapters.competitors import (
    ChonkieRecursiveAdapter,
    DoclingHierarchicalAdapter,
    UnstructuredBasicAdapter,
    UnstructuredByTitleAdapter,
)
from benchmarks.adapters.langchain import (
    LangChainMarkdownAdapter,
    LangChainRecursiveAdapter,
)
from benchmarks.adapters.lumberjack import LumberjackAdapter
from benchmarks.contract import BenchmarkConfig, BenchmarkReport, DocumentResult
from benchmarks.metrics import evaluate_quality, measure_callable, summarize_samples

ROOT = Path(__file__).resolve().parent


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=ROOT.parent
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _load_manifest() -> dict[str, Any]:
    return json.loads((ROOT / "datasets" / "manifest.json").read_text(encoding="utf-8"))


def _adapter(name: str) -> BenchmarkAdapter:
    adapters: dict[str, BenchmarkAdapter] = {
        "lumberjack": LumberjackAdapter(),
        "langchain-recursive": LangChainRecursiveAdapter(),
        "langchain-markdown": LangChainMarkdownAdapter(),
        "unstructured-basic": UnstructuredBasicAdapter(),
        "unstructured-by-title": UnstructuredByTitleAdapter(),
        "docling-hierarchical": DoclingHierarchicalAdapter(),
        "chonkie-recursive": ChonkieRecursiveAdapter(),
    }
    try:
        return adapters[name]
    except KeyError as error:
        raise ValueError(f"Unsupported adapter: {name}") from error


def run_benchmark(
    adapter: BenchmarkAdapter, config: BenchmarkConfig
) -> BenchmarkReport:
    """Execute warmups and repeated samples for every document in the manifest."""
    manifest = _load_manifest()
    results: list[DocumentResult] = []
    for item in manifest["documents"]:
        source = (ROOT / "datasets" / item["path"]).read_text(encoding="utf-8")
        for _ in range(config.warmups):
            adapter.split(source, config=config)

        chunks = []
        samples = []
        for _ in range(config.repetitions):
            chunks, sample = measure_callable(
                lambda source=source, config=config: adapter.split(
                    source, config=config
                )
            )
            samples.append(
                replace(
                    sample,
                    count_calls=getattr(adapter, "last_count_calls", 0),
                    encode_calls=getattr(adapter, "last_encode_calls", 0),
                )
            )
        quality = evaluate_quality(
            chunks,
            max_tokens=config.max_tokens,
            required_content=tuple(item["required_content"]),
            protected_content=tuple(item["protected_content"]),
        )
        values = dict(quality.values)
        values.update(summarize_samples(samples, len(source.encode("utf-8"))))
        diagnostics = list(quality.diagnostics)
        if adapter.name != "lumberjack":
            diagnostics.append(
                "adapter output has no normalized source-line provenance; "
                "provenance coverage is not directly comparable"
            )
        results.append(
            DocumentResult(
                document_id=item["id"],
                adapter=adapter.name,
                chunks=chunks,
                samples=samples,
                quality=values,
                diagnostics=diagnostics,
            )
        )
    return BenchmarkReport(
        schema_version="1.0",
        commit=_commit(),
        generated_at=datetime.now(UTC).isoformat(),
        environment={
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        config=config,
        dataset_version=manifest["dataset_version"],
        results=results,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Lumberjack benchmark corpus.")
    parser.add_argument(
        "--adapter",
        default="lumberjack",
        choices=(
            "lumberjack",
            "langchain-recursive",
            "langchain-markdown",
            "unstructured-basic",
            "unstructured-by-title",
            "docling-hierarchical",
            "chonkie-recursive",
        ),
    )
    parser.add_argument(
        "--tokenizer", default="approx", choices=("approx", "tiktoken", "transformers")
    )
    parser.add_argument("--splitter", default="section")
    parser.add_argument("--max-tokens", type=int, default=240)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--output", type=Path, help="Directory for raw.json and summary.json"
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = BenchmarkConfig(
        tokenizer=args.tokenizer,
        splitter=args.splitter,
        max_tokens=args.max_tokens,
        warmups=args.warmups,
        repetitions=args.repetitions,
    )
    try:
        report = run_benchmark(_adapter(args.adapter), config)
    except AdapterUnavailable as error:
        print(error, file=sys.stderr)
        return 2
    output = (
        args.output
        or ROOT / "results" / f"{datetime.now():%Y%m%d}-{report.commit[:12]}"
    )
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "raw.json"
    raw_path.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schema_version": report.schema_version,
        "commit": report.commit,
        "dataset_version": report.dataset_version,
        "config": report.as_dict()["config"],
        "results": [
            {
                "document_id": item.document_id,
                "adapter": item.adapter,
                "quality": item.quality,
                "diagnostics": item.diagnostics,
            }
            for item in report.results
        ],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(raw_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Large-scale randomized verification for parsers beyond Markdown and DOCX.

Unlike ``parser_run`` (version-pinned external corpora), this harness
generates documents from seeded grammars and checks each parser against
oracles the generator records while building the document: visible-text
recall, exact element-signature counts, tree invariants, and clean
rejection of adversarially damaged payloads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
import tracemalloc
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.parser_contract import (
    PARSER_BENCHMARK_SCHEMA_VERSION,
    ParserBenchmarkConfig,
    ParserBenchmarkReport,
    ParserDocumentResult,
)
from benchmarks.parser_run import (
    _commit,
    _content_character_stats,
    _content_token_stats,
    _element_signatures,
    _git_status,
    _percentile,
    _structure_counts,
    _tree_text,
    _validate_tree,
)
from benchmarks.random_corpus import FORMAT_SPECS, RandomDocument, generate_documents

ROOT = Path(__file__).resolve().parent


def _document_dataset(document: RandomDocument) -> str:
    suffix = "-adversarial" if document.allowed_error_types else ""
    return f"random-{document.format}{suffix}"


def _parse_generated(document: RandomDocument) -> ParserDocumentResult:
    spec = FORMAT_SPECS[document.format]
    payload = document.source
    digest = hashlib.sha256(
        payload.encode("utf-8") if isinstance(payload, str) else payload
    ).hexdigest()
    tracemalloc.start()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    diagnostics: list[str] = []
    try:
        tree = spec.make_parser().parse(payload, document_title=document.document_id)
        diagnostics.extend(_validate_tree(tree))
        actual = _element_signatures(tree)
        for element, count in Counter(document.required_elements).items():
            if actual[element] != count:
                diagnostics.append(
                    f"element count mismatch for {element!r}: "
                    f"expected {count}, found {actual[element]}"
                )
        for element in document.forbidden_elements:
            if actual[element]:
                diagnostics.append(
                    f"forbidden element {element!r}: found {actual[element]}"
                )
        extracted_text = _tree_text(tree)
        _, _, recall = _content_token_stats(document.reference_text, extracted_text)
        _, _, character_recall = _content_character_stats(
            document.reference_text, extracted_text
        )
        if document.min_token_recall and recall < document.min_token_recall:
            diagnostics.append(
                f"token recall {recall:.4f} below required {document.min_token_recall:.4f}"
            )
        counts = _structure_counts(tree)
        status = "invalid" if diagnostics else "success"
        error_type = None
        error_message = None
    except Exception as error:  # the harness must preserve every corpus failure
        recall = None
        character_recall = None
        counts = {
            "section_count": 0,
            "block_count": 0,
            "inline_count": 0,
            "table_count": 0,
            "list_count": 0,
            "image_count": 0,
        }
        mro_names = {cls.__name__ for cls in type(error).__mro__}
        if document.allowed_error_types and mro_names & set(
            document.allowed_error_types
        ):
            status = "rejected"
        else:
            status = "error"
        error_type = type(error).__name__
        error_message = str(error)
        diagnostics = []
    finally:
        wall_time = time.perf_counter() - wall_start
        cpu_time = time.process_time() - cpu_start
        peak_memory = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    return ParserDocumentResult(
        dataset_id=_document_dataset(document),
        document_id=document.document_id,
        format=document.format,
        sha256=digest,
        source_bytes=len(
            payload.encode("utf-8") if isinstance(payload, str) else payload
        ),
        status=status,
        wall_time_seconds=wall_time,
        cpu_time_seconds=cpu_time,
        peak_memory_bytes=peak_memory,
        content_token_recall=recall,
        content_character_recall=character_recall,
        element_assertions=len(document.required_elements)
        + len(document.forbidden_elements),
        passed_element_assertions=len(document.required_elements)
        + len(document.forbidden_elements)
        if status == "success"
        else 0,
        error_type=error_type,
        error_message=error_message,
        diagnostics=tuple(diagnostics),
        **counts,
    )


def _summarize_group(results: list[ParserDocumentResult]) -> dict[str, Any]:
    successful = [result for result in results if result.status == "success"]
    rejected = [result for result in results if result.status == "rejected"]
    recalls = [
        result.content_token_recall
        for result in successful
        if result.content_token_recall is not None
    ]
    total_wall = sum(result.wall_time_seconds for result in results)
    failures = Counter(
        result.error_type or result.status
        for result in results
        if result.status in {"invalid", "error"}
    )
    return {
        "documents": len(results),
        "successful": len(successful),
        "cleanly_rejected": len(rejected),
        "failed": sum(failures.values()),
        "success_rate": len(successful) / len(results) if results else 0.0,
        "source_bytes": sum(result.source_bytes for result in results),
        "throughput_mb_per_second": (
            sum(result.source_bytes for result in results) / 1_000_000 / total_wall
            if total_wall
            else 0.0
        ),
        "wall_time_seconds_p50": _percentile(
            [result.wall_time_seconds for result in results], 0.5
        ),
        "wall_time_seconds_p95": _percentile(
            [result.wall_time_seconds for result in results], 0.95
        ),
        "peak_memory_bytes_p95": _percentile(
            [float(result.peak_memory_bytes) for result in results], 0.95
        ),
        "content_token_recall_min": min(recalls, default=0.0),
        "documents_below_recall_1_0": sum(recall < 1.0 for recall in recalls),
        "failures": dict(sorted(failures.items())),
    }


def _summarize(results: list[ParserDocumentResult]) -> dict[str, Any]:
    formats = sorted({result.format for result in results})
    datasets = sorted({result.dataset_id for result in results})
    return {
        "overall": _summarize_group(results),
        "by_format": {
            source_format: _summarize_group(
                [result for result in results if result.format == source_format]
            )
            for source_format in formats
        },
        "by_dataset": {
            dataset: _summarize_group(
                [result for result in results if result.dataset_id == dataset]
            )
            for dataset in datasets
        },
    }


def run_random_benchmark(
    formats: list[str],
    *,
    seed: int,
    count_per_format: int,
) -> ParserBenchmarkReport:
    documents = generate_documents(
        formats, seed=seed, count_per_format=count_per_format
    )
    results = [_parse_generated(document) for document in documents]
    return ParserBenchmarkReport(
        schema_version=PARSER_BENCHMARK_SCHEMA_VERSION,
        commit=_commit(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        environment={
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "git_status": _git_status(),
        },
        config=ParserBenchmarkConfig(
            seed=seed,
            sample_size_per_source=count_per_format,
            formats=tuple(formats),
        ),
        dataset_version="generated",
        candidates_by_source=dict.fromkeys(formats, count_per_format),
        selected_by_source={
            name: sum(1 for result in results if result.format == name)
            for name in formats
        },
        results=results,
        summary=_summarize(results),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Randomized parser verification")
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument("--documents-per-format", type=int, default=300)
    parser.add_argument(
        "--formats",
        default=",".join(FORMAT_SPECS),
        help="Comma-separated format list (default: every supported format)",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    formats = [name.strip() for name in args.formats.split(",") if name.strip()]
    report = run_random_benchmark(
        formats,
        seed=args.seed,
        count_per_format=args.documents_per_format,
    )
    failed = report.summary["overall"]["failed"]
    output = (
        args.output
        or ROOT / "results" / f"random-{datetime.now():%Y%m%d}-{report.commit[:12]}"
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schema_version": report.schema_version,
        "commit": report.commit,
        "config": asdict(report.config),
        "summary": report.summary,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.summary["by_format"], ensure_ascii=False, indent=2))
    print(f"results written to {output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Large-scale randomized benchmark for the hierarchical splitters.

Measures the six splitter variants (section/subtree/sibling topology x
exact/incremental counting) under identical tokenizers and documents:

* split-phase wall/CPU speed, measured without tracing overhead, with the
  tokenizer text cache cleared before every repetition so each timed split
  starts from a zero cache — matching production, where caches are
  request-local and never reused across documents,
* tokenizer ``count`` call volume,
* token estimation error - the gap between the split-time running estimate
  (``Chunk.estimated_token_count``) and the finalizer's authoritative recount
  (``Chunk.token_count``),
* final chunks that exceed ``max_tokens`` because the estimate under-counted,
* content fidelity oracles carried by the random corpora,
* cold-run allocation peaks (tracemalloc) for the split phase alone and for
  split + finalize, taken in a separate pass with a fresh tokenizer cache per
  repetition so cache growth is attributed to the splitter that causes it.

Warmup runs exist only to load the tokenizer backend into memory and reach
interpreter/allocator steady state; they never warm the timed repetitions'
cache. The parser runs once per document outside every timed region;
splitters treat the tree as read-only, so all variants split the same
``DocTree`` instance. Re-run with different ``--max-tokens`` values to
compare parameter budgets.

Example:
    uv run python -m benchmarks.splitter_random_run --corpus both
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.contract import BenchmarkChunk
from benchmarks.metrics import evaluate_quality
from benchmarks.metrics.performance import CountingTokenizer
from benchmarks.parser_run import (
    _commit,
    _content_token_stats,
    _git_status,
    _percentile,
    _walk_sections,
)
from benchmarks.splitter_random_corpus import (
    SHAPES,
    RandomSplitDocument,
    generate_documents,
    recombine_documents,
)
from lumberjack.finalizer import ChunkFinalizer
from lumberjack.models import (
    Chunk,
    DocTree,
    Document,
    complete_heading_path,
    render_heading_path,
)
from lumberjack.parser.markdown import MarkdownParser
from lumberjack.protocols import TokenizerProtocol
from lumberjack.splitter import (
    ExactSectionSplitter,
    ExactSiblingSplitter,
    ExactSubtreeSplitter,
    SectionSplitter,
    SiblingSplitter,
    SubtreeSplitter,
)
from lumberjack.splitter.base import BaseSplitter
from lumberjack.tokenizer import ApproxByteTokenizer, TiktokenTokenizer

ROOT = Path(__file__).resolve().parent

SCHEMA_VERSION = "1.1"

SPLITTER_CLASSES: dict[str, type[BaseSplitter]] = {
    "incremental-section": SectionSplitter,
    "exact-section": ExactSectionSplitter,
    "incremental-subtree": SubtreeSplitter,
    "exact-subtree": ExactSubtreeSplitter,
    "incremental-sibling": SiblingSplitter,
    "exact-sibling": ExactSiblingSplitter,
}

TOPOLOGIES = ("section", "subtree", "sibling")

TOKENIZER_ENGINES = ("approx", "tiktoken")


@dataclass(frozen=True, slots=True)
class SplitterRandomConfig:
    """All settings that can affect a splitter benchmark result."""

    corpus: str = "both"
    shapes: tuple[str, ...] = tuple(SHAPES)
    splitters: tuple[str, ...] = tuple(SPLITTER_CLASSES)
    tokenizers: tuple[str, ...] = TOKENIZER_ENGINES
    seed: int = 20260826
    documents_per_shape: int = 10
    recombined_documents: int = 30
    max_tokens: int = 300
    warmups: int = 1
    repetitions: int = 2
    memory_reps: int = 3

    def __post_init__(self) -> None:
        if self.corpus not in {"synthetic", "recombined", "both"}:
            raise ValueError(f"unknown corpus mode: {self.corpus!r}")
        if not self.shapes:
            raise ValueError("at least one shape is required")
        unknown_shapes = sorted(set(self.shapes) - set(SHAPES))
        if unknown_shapes:
            raise ValueError(f"unknown shapes: {unknown_shapes}")
        if not self.splitters:
            raise ValueError("at least one splitter is required")
        unknown_splitters = sorted(set(self.splitters) - set(SPLITTER_CLASSES))
        if unknown_splitters:
            raise ValueError(f"unknown splitters: {unknown_splitters}")
        if not self.tokenizers:
            raise ValueError("at least one tokenizer engine is required")
        unknown_engines = sorted(set(self.tokenizers) - set(TOKENIZER_ENGINES))
        if unknown_engines:
            raise ValueError(f"unknown tokenizer engines: {unknown_engines}")
        if self.corpus in {"synthetic", "both"} and self.documents_per_shape <= 0:
            raise ValueError("documents_per_shape must be positive")
        if self.corpus in {"recombined", "both"} and self.recombined_documents <= 0:
            raise ValueError("recombined_documents must be positive")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.warmups < 0:
            raise ValueError("warmups cannot be negative")
        if self.repetitions <= 0:
            raise ValueError("repetitions must be positive")
        if self.memory_reps < 0:
            raise ValueError("memory_reps cannot be negative")


@dataclass(frozen=True, slots=True)
class SplitSample:
    """One measured ``split()`` invocation (no tracing overhead)."""

    wall_time_seconds: float
    cpu_time_seconds: float
    count_calls: int
    encode_calls: int
    draft_count: int


@dataclass(frozen=True, slots=True)
class ChunkObservation:
    """Per-chunk counting evidence (body text excluded to bound report size)."""

    chunk_id: str
    chunk_type: str
    token_count: int
    estimated_token_count: int
    abs_estimate_error: int
    relative_estimate_error: float
    protected: bool
    exceeds_budget: bool


@dataclass(slots=True)
class SplitterDocumentResult:
    """Result for one (document, tokenizer, splitter) combination."""

    document_id: str
    dataset: str
    shape: str
    tokenizer: str
    splitter: str
    status: str
    error_type: str | None
    diagnostics: list[str] = field(default_factory=list)
    source_bytes: int = 0
    source_approx_tokens: int = 0
    split_samples: list[SplitSample] = field(default_factory=list)
    finalize_wall_seconds: float = 0.0
    finalize_count_calls: int = 0
    split_peak_memory_bytes: int = 0
    total_peak_memory_bytes: int = 0
    quality: dict[str, float] = field(default_factory=dict)
    word_recall: float | None = None
    chunk_count: int = 0
    estimate_abs_error_mean: float = 0.0
    estimate_abs_error_p95: float = 0.0
    estimate_abs_error_max: float = 0.0
    estimate_relative_error_max: float = 0.0
    budget_violations: int = 0
    max_overshoot_tokens: int = 0
    chunks: list[ChunkObservation] = field(default_factory=list)


@dataclass(slots=True)
class SplitterRandomReport:
    """JSON-report envelope written by this module."""

    schema_version: str
    commit: str
    generated_at: str
    environment: dict[str, Any]
    config: SplitterRandomConfig
    dataset_version: str
    results: list[SplitterDocumentResult]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tokenizer_template(name: str) -> TokenizerProtocol:
    if name == "approx":
        return ApproxByteTokenizer()
    if name == "tiktoken":
        try:
            return TiktokenTokenizer()
        except (ImportError, OSError) as error:
            raise ValueError(
                f"tokenizer {name!r} is unavailable ({error}); the tiktoken "
                "extra must be installed and the first run needs network "
                "access to download its encoding file"
            ) from error
    raise ValueError(f"unsupported tokenizer engine: {name!r}")


def _fresh_tokenizer(template: TokenizerProtocol) -> TokenizerProtocol:
    """Give every (engine, splitter) pair a cold cache on a shared encoding."""
    factory = getattr(template, "with_fresh_cache", None)
    if callable(factory):
        return factory()
    return template


def _reset_tokenizer_cache(tokenizer: TokenizerProtocol) -> None:
    """Zero the text cache so the next split starts cold, as in production."""
    clear = getattr(tokenizer, "clear_cache", None)
    if callable(clear):
        clear()


def _tree_reference_text(tree: DocTree) -> str:
    """Visible-text truth from the parsed tree.

    Titles are contributed only by sections that own body blocks, matching the
    documented ``skip_empty_sections`` behavior so intentionally dropped
    heading-only sections do not count as lost content.
    """
    parts: list[str] = []
    for section in _walk_sections(tree.root):
        if not any(block.text.strip() for block in section.blocks):
            continue
        if section.level:
            parts.append(section.title)
        parts.extend(block.text for block in section.blocks if block.text.strip())
    return "\n".join(parts)


def _to_benchmark_chunks(chunks: list[Chunk]) -> list[BenchmarkChunk]:
    return [
        BenchmarkChunk(
            text="\n\n".join(
                part
                for part in (
                    render_heading_path(
                        complete_heading_path(
                            chunk.ancestor_headings, chunk.own_heading
                        )
                    ),
                    chunk.body,
                )
                if part
            ),
            token_count=chunk.token_count,
            estimated_token_count=chunk.estimated_token_count,
            chunk_type=chunk.chunk_type,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            protected=chunk.protected
            or chunk.chunk_type in {"code_fence", "code_block"},
        )
        for chunk in chunks
    ]


def _evaluate_chunks(
    benchmark_chunks: list[BenchmarkChunk],
    document: RandomSplitDocument,
    reference: str,
    *,
    max_tokens: int,
) -> tuple[dict[str, float], list[str], float | None]:
    """Quality metrics plus fidelity diagnostics for one finished chunk list."""
    quality = evaluate_quality(
        benchmark_chunks,
        max_tokens=max_tokens,
        required_content=document.required_content,
        protected_content=document.protected_content,
    )
    diagnostics = list(quality.diagnostics)
    word_recall: float | None = None
    if document.min_word_recall > 0 and reference:
        extracted = "\n\n".join(chunk.text for chunk in benchmark_chunks)
        _, _, word_recall = _content_token_stats(reference, extracted)
        if word_recall < document.min_word_recall:
            diagnostics.append(
                f"word recall {word_recall:.4f} below required "
                f"{document.min_word_recall}"
            )
    return dict(quality.values), diagnostics, word_recall


def _measure_memory(
    *,
    tree: DocTree,
    template: TokenizerProtocol,
    splitter_name: str,
    config: SplitterRandomConfig,
) -> list[tuple[int, int]]:
    """Cold-run allocation peaks as ``(split peak, split+finalize peak)`` pairs.

    Every repetition rebuilds the splitter on a tokenizer with a fresh cache,
    so the traced peak includes whatever LRU entries the splitter's
    cache-enabled counting allocates on a first run (exact modes count
    cache-free and allocate none).
    """
    peaks: list[tuple[int, int]] = []
    for _ in range(config.memory_reps):
        tokenizer = CountingTokenizer(_fresh_tokenizer(template))
        splitter = SPLITTER_CLASSES[splitter_name](
            tokenizer, max_tokens=config.max_tokens
        )
        finalizer = ChunkFinalizer(tokenizer)
        gc.collect()
        tracemalloc.start()
        drafts = splitter.split(tree)
        split_peak = tracemalloc.get_traced_memory()[1]
        chunks = finalizer.finalize(tree, drafts)
        total_peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        peaks.append((split_peak, total_peak))
        del drafts, chunks
        gc.collect()
    return peaks


def _measure_document(
    *,
    document: RandomSplitDocument,
    tree: DocTree,
    reference: str,
    template: TokenizerProtocol,
    engine_name: str,
    splitter_name: str,
    config: SplitterRandomConfig,
) -> SplitterDocumentResult:
    inner = _fresh_tokenizer(template)
    tokenizer = CountingTokenizer(inner)
    splitter = SPLITTER_CLASSES[splitter_name](tokenizer, max_tokens=config.max_tokens)
    finalizer = ChunkFinalizer(tokenizer)
    result = SplitterDocumentResult(
        document_id=document.document_id,
        dataset=document.dataset,
        shape=document.shape,
        tokenizer=engine_name,
        splitter=splitter_name,
        status="success",
        error_type=None,
        source_bytes=document.profile.get(
            "source_bytes", len(document.source.encode())
        ),
        source_approx_tokens=document.profile.get("approx_tokens", 0),
    )
    try:
        # Warmup loads the tokenizer backend and reaches steady state only;
        # every timed repetition below clears the cache first, so warmup
        # never leaks a warm cache into the measurements.
        for _ in range(config.warmups):
            splitter.split(tree)
        drafts: list[Any] = []
        for _ in range(config.repetitions):
            _reset_tokenizer_cache(inner)
            tokenizer.count_calls = 0
            tokenizer.encode_calls = 0
            wall_start = time.perf_counter()
            cpu_start = time.process_time()
            drafts = splitter.split(tree)
            result.split_samples.append(
                SplitSample(
                    wall_time_seconds=time.perf_counter() - wall_start,
                    cpu_time_seconds=time.process_time() - cpu_start,
                    count_calls=tokenizer.count_calls,
                    encode_calls=tokenizer.encode_calls,
                    draft_count=len(drafts),
                )
            )
        tokenizer.count_calls = 0
        finalize_start = time.perf_counter()
        chunks = finalizer.finalize(tree, drafts)
        result.finalize_wall_seconds = time.perf_counter() - finalize_start
        result.finalize_count_calls = tokenizer.count_calls
        if config.memory_reps:
            peaks = _measure_memory(
                tree=tree,
                template=template,
                splitter_name=splitter_name,
                config=config,
            )
            result.split_peak_memory_bytes = int(
                statistics.median(peak[0] for peak in peaks)
            )
            result.total_peak_memory_bytes = int(
                statistics.median(peak[1] for peak in peaks)
            )
    except Exception as error:
        result.status = "error"
        result.error_type = type(error).__name__
        result.diagnostics = [f"{type(error).__name__}: {error}"[:300]]
        return result

    benchmark_chunks = _to_benchmark_chunks(chunks)
    quality_values, diagnostics, word_recall = _evaluate_chunks(
        benchmark_chunks, document, reference, max_tokens=config.max_tokens
    )
    result.quality = quality_values
    result.diagnostics = diagnostics
    result.word_recall = word_recall
    result.chunk_count = len(chunks)

    observations: list[ChunkObservation] = []
    for chunk, converted in zip(chunks, benchmark_chunks, strict=True):
        error = abs(chunk.estimated_token_count - chunk.token_count)
        exceeds = not converted.protected and chunk.token_count > config.max_tokens
        observations.append(
            ChunkObservation(
                chunk_id=chunk.chunk_id,
                chunk_type=chunk.chunk_type,
                token_count=chunk.token_count,
                estimated_token_count=chunk.estimated_token_count,
                abs_estimate_error=error,
                relative_estimate_error=(
                    error / chunk.token_count if chunk.token_count else 0.0
                ),
                protected=converted.protected,
                exceeds_budget=exceeds,
            )
        )
    result.chunks = observations
    abs_errors = [float(observation.abs_estimate_error) for observation in observations]
    if abs_errors:
        result.estimate_abs_error_mean = statistics.mean(abs_errors)
        result.estimate_abs_error_p95 = float(_percentile(abs_errors, 0.95))
        result.estimate_abs_error_max = max(abs_errors)
        result.estimate_relative_error_max = max(
            observation.relative_estimate_error for observation in observations
        )
    violations = [obs for obs in observations if obs.exceeds_budget]
    result.budget_violations = len(violations)
    result.max_overshoot_tokens = max(
        (obs.token_count - config.max_tokens for obs in violations), default=0
    )
    if diagnostics:
        result.status = "invalid"
    return result


def _collect_documents(config: SplitterRandomConfig) -> list[RandomSplitDocument]:
    documents: list[RandomSplitDocument] = []
    if config.corpus in {"synthetic", "both"}:
        documents.extend(
            generate_documents(
                list(config.shapes),
                seed=config.seed,
                count_per_shape=config.documents_per_shape,
                budget_tokens=config.max_tokens,
            )
        )
    if config.corpus in {"recombined", "both"}:
        documents.extend(
            recombine_documents(seed=config.seed, count=config.recombined_documents)
        )
    if not documents:
        raise ValueError("no documents selected; check corpus and shape settings")
    return documents


def _aggregate(results: list[SplitterDocumentResult]) -> dict[str, Any]:
    if not results:
        return {"results": 0, "failed": 0, "statuses": {}}
    wall_medians = [
        statistics.median(sample.wall_time_seconds for sample in result.split_samples)
        for result in results
        if result.split_samples
    ]
    wall_means = [
        statistics.mean(sample.wall_time_seconds for sample in result.split_samples)
        for result in results
        if result.split_samples
    ]
    call_medians = [
        statistics.median(sample.count_calls for sample in result.split_samples)
        for result in results
        if result.split_samples
    ]
    split_peaks = [
        result.split_peak_memory_bytes
        for result in results
        if result.split_peak_memory_bytes
    ]
    total_peaks = [
        result.total_peak_memory_bytes
        for result in results
        if result.total_peak_memory_bytes
    ]
    source_bytes = [result.source_bytes for result in results]
    source_tokens = [
        result.source_approx_tokens for result in results if result.source_approx_tokens
    ]
    chunk_counts = [result.chunk_count for result in results]
    observations = [obs for result in results for obs in result.chunks]
    abs_errors = [float(obs.abs_estimate_error) for obs in observations]
    violations = [obs for obs in observations if obs.exceeds_budget]
    recalls = [
        result.word_recall for result in results if result.word_recall is not None
    ]
    statuses: dict[str, int] = {}
    for result in results:
        statuses[result.status] = statuses.get(result.status, 0) + 1
    return {
        "results": len(results),
        "failed": sum(result.status != "success" for result in results),
        "statuses": statuses,
        "source_bytes_median": statistics.median(source_bytes) if source_bytes else 0,
        "source_bytes_total": sum(source_bytes),
        "source_approx_tokens_median": statistics.median(source_tokens)
        if source_tokens
        else 0,
        "split_wall_seconds_median": statistics.median(wall_medians)
        if wall_medians
        else 0.0,
        "split_wall_seconds_mean": statistics.mean(wall_means) if wall_means else 0.0,
        "split_wall_seconds_p95": _percentile(wall_medians, 0.95)
        if wall_medians
        else 0.0,
        "split_count_calls_median": statistics.median(call_medians)
        if call_medians
        else 0.0,
        "finalize_wall_seconds_median": statistics.median(
            result.finalize_wall_seconds for result in results
        ),
        "split_peak_memory_bytes_median": statistics.median(split_peaks)
        if split_peaks
        else 0,
        "total_peak_memory_bytes_median": statistics.median(total_peaks)
        if total_peaks
        else 0,
        "chunk_count_total": sum(chunk_counts),
        "chunk_count_median": statistics.median(chunk_counts) if chunk_counts else 0,
        "estimate_abs_error_mean": statistics.mean(abs_errors) if abs_errors else 0.0,
        "estimate_abs_error_p95": float(_percentile(abs_errors, 0.95))
        if abs_errors
        else 0.0,
        "estimate_abs_error_max": max(abs_errors) if abs_errors else 0,
        "budget_violations": len(violations),
        "budget_violation_rate": len(violations) / len(observations)
        if observations
        else 0.0,
        "max_overshoot_tokens": max((obs.token_count for obs in violations), default=0),
        "word_recall_min": min(recalls) if recalls else None,
    }


def _ratio(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return numerator / denominator


def _summarize(results: list[SplitterDocumentResult]) -> dict[str, Any]:
    by_tokenizer: dict[str, Any] = {}
    for engine in sorted({result.tokenizer for result in results}):
        engine_results = [r for r in results if r.tokenizer == engine]
        by_splitter = {
            splitter: _aggregate([r for r in engine_results if r.splitter == splitter])
            for splitter in sorted({r.splitter for r in engine_results})
        }
        engine_summary = _aggregate(engine_results)
        engine_summary["by_splitter"] = by_splitter
        by_tokenizer[engine] = engine_summary
    by_dataset = {
        dataset: _aggregate([r for r in results if r.dataset == dataset])
        for dataset in sorted({r.dataset for r in results})
    }
    pairwise: dict[str, dict[str, Any]] = {}
    for engine, engine_summary in by_tokenizer.items():
        rows: dict[str, Any] = {}
        for topology in TOPOLOGIES:
            incremental = engine_summary["by_splitter"].get(f"incremental-{topology}")
            exact = engine_summary["by_splitter"].get(f"exact-{topology}")
            if not incremental or not exact:
                continue
            rows[topology] = {
                "incremental_wall_median": incremental["split_wall_seconds_median"],
                "exact_wall_median": exact["split_wall_seconds_median"],
                "exact_over_incremental_wall_ratio": _ratio(
                    exact["split_wall_seconds_median"],
                    incremental["split_wall_seconds_median"],
                ),
                "incremental_count_calls_median": incremental[
                    "split_count_calls_median"
                ],
                "exact_count_calls_median": exact["split_count_calls_median"],
                "exact_over_incremental_count_calls_ratio": _ratio(
                    exact["split_count_calls_median"],
                    incremental["split_count_calls_median"],
                ),
                "incremental_split_peak_memory_median": incremental[
                    "split_peak_memory_bytes_median"
                ],
                "exact_split_peak_memory_median": exact[
                    "split_peak_memory_bytes_median"
                ],
                "exact_over_incremental_peak_memory_ratio": _ratio(
                    exact["split_peak_memory_bytes_median"],
                    incremental["split_peak_memory_bytes_median"],
                ),
                "incremental_estimate_abs_error_mean": incremental[
                    "estimate_abs_error_mean"
                ],
                "exact_estimate_abs_error_mean": exact["estimate_abs_error_mean"],
                "incremental_estimate_abs_error_max": incremental[
                    "estimate_abs_error_max"
                ],
                "incremental_budget_violation_rate": incremental[
                    "budget_violation_rate"
                ],
                "exact_budget_violation_rate": exact["budget_violation_rate"],
                "chunk_count_total_diff": incremental["chunk_count_total"]
                - exact["chunk_count_total"],
            }
        pairwise[engine] = rows
    return {
        "overall": _aggregate(results),
        "by_tokenizer": by_tokenizer,
        "by_dataset": by_dataset,
        "pairwise": pairwise,
    }


def run_splitter_benchmark(
    config: SplitterRandomConfig,
) -> SplitterRandomReport:
    """Generate documents, then measure every (engine, splitter) combination."""
    documents = _collect_documents(config)
    templates = {name: _tokenizer_template(name) for name in config.tokenizers}
    parser = MarkdownParser()
    results: list[SplitterDocumentResult] = []
    for document in documents:
        tree = parser.parse(
            Document(
                source=document.source,
                format="markdown",
                document_title=document.document_id,
            )
        )
        reference = _tree_reference_text(tree)
        for engine_name in config.tokenizers:
            template = templates[engine_name]
            for splitter_name in config.splitters:
                results.append(
                    _measure_document(
                        document=document,
                        tree=tree,
                        reference=reference,
                        template=template,
                        engine_name=engine_name,
                        splitter_name=splitter_name,
                        config=config,
                    )
                )
    return SplitterRandomReport(
        schema_version=SCHEMA_VERSION,
        commit=_commit(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        environment={
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "git_status": _git_status(),
        },
        config=config,
        dataset_version="generated",
        results=results,
        summary=_summarize(results),
    )


def _format_ratio(value: float | None, suffix: str = "") -> str:
    return f"{value:.2f}{suffix}" if value is not None else "n/a"


def _print_report_tables(report: SplitterRandomReport) -> None:
    overall = report.summary["overall"]
    print(
        f"results: {overall['results']}, failed: {overall['failed']}, "
        f"max_tokens: {report.config.max_tokens}"
    )
    for engine, engine_summary in report.summary["by_tokenizer"].items():
        print(f"\n=== tokenizer: {engine} ===")
        print(
            f"{'splitter':<22} {'wall med ms':>11} {'wall mean ms':>12} "
            f"{'wall p95 ms':>11} {'mem KB':>8} {'calls med':>10} "
            f"{'|err| mean':>10} {'|err| max':>9} {'viol %':>7} "
            f"{'chunks':>7} {'failed':>6}"
        )
        for splitter, stats in engine_summary["by_splitter"].items():
            print(
                f"{splitter:<22} "
                f"{stats['split_wall_seconds_median'] * 1000:>11.2f} "
                f"{stats['split_wall_seconds_mean'] * 1000:>12.2f} "
                f"{stats['split_wall_seconds_p95'] * 1000:>11.2f} "
                f"{stats['split_peak_memory_bytes_median'] / 1024:>8.1f} "
                f"{stats['split_count_calls_median']:>10.0f} "
                f"{stats['estimate_abs_error_mean']:>10.3f} "
                f"{stats['estimate_abs_error_max']:>9.0f} "
                f"{stats['budget_violation_rate'] * 100:>6.2f}% "
                f"{stats['chunk_count_total']:>7} "
                f"{stats['failed']:>6}"
            )
    for engine, rows in report.summary["pairwise"].items():
        print(f"\n=== exact vs incremental ({engine}) ===")
        for topology, pair in rows.items():
            print(
                f"{topology:<10} "
                f"wall exact/inc {_format_ratio(pair['exact_over_incremental_wall_ratio'], 'x')} | "
                f"mem exact/inc {_format_ratio(pair['exact_over_incremental_peak_memory_ratio'], 'x')} | "
                f"calls {pair['exact_count_calls_median']:.0f}/"
                f"{pair['incremental_count_calls_median']:.0f} "
                f"({_format_ratio(pair['exact_over_incremental_count_calls_ratio'])}) | "
                f"|err| mean inc {pair['incremental_estimate_abs_error_mean']:.3f} "
                f"exact {pair['exact_estimate_abs_error_mean']:.3f} | "
                f"viol% inc {pair['incremental_budget_violation_rate'] * 100:.2f} "
                f"exact {pair['exact_budget_violation_rate'] * 100:.2f} | "
                f"chunk diff {pair['chunk_count_total_diff']}"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Large-scale random splitter benchmark."
    )
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument(
        "--corpus", choices=("synthetic", "recombined", "both"), default="both"
    )
    parser.add_argument("--shapes", default=",".join(SHAPES))
    parser.add_argument("--documents-per-shape", type=int, default=10)
    parser.add_argument("--recombined-documents", type=int, default=30)
    parser.add_argument("--tokenizers", default=",".join(TOKENIZER_ENGINES))
    parser.add_argument("--splitters", default=",".join(SPLITTER_CLASSES))
    parser.add_argument("--max-tokens", type=int, default=300)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument(
        "--memory-reps",
        type=int,
        default=3,
        help="Cold-run tracemalloc repetitions (0 disables memory measurement)",
    )
    parser.add_argument(
        "--output", type=Path, help="Directory for raw.json and summary.json"
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        config = SplitterRandomConfig(
            corpus=args.corpus,
            shapes=tuple(
                name.strip() for name in args.shapes.split(",") if name.strip()
            ),
            splitters=tuple(
                name.strip() for name in args.splitters.split(",") if name.strip()
            ),
            tokenizers=tuple(
                name.strip() for name in args.tokenizers.split(",") if name.strip()
            ),
            seed=args.seed,
            documents_per_shape=args.documents_per_shape,
            recombined_documents=args.recombined_documents,
            max_tokens=args.max_tokens,
            warmups=args.warmups,
            repetitions=args.repetitions,
            memory_reps=args.memory_reps,
        )
        report = run_splitter_benchmark(config)
    except (ValueError, FileNotFoundError) as error:
        print(error, file=sys.stderr)
        return 2
    output = args.output or ROOT / "results" / (
        f"splitter-random-{datetime.now():%Y%m%d}-{report.commit[:12]}"
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": report.schema_version,
                "commit": report.commit,
                "generated_at": report.generated_at,
                "config": asdict(report.config),
                "summary": report.summary,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _print_report_tables(report)
    print(f"\nresults written to {output}")
    return 1 if report.summary["overall"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

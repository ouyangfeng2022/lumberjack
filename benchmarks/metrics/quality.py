"""Splitter-independent structure, budget, and provenance metrics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import quantiles

from benchmarks.contract import BenchmarkChunk


@dataclass(frozen=True, slots=True)
class QualityReport:
    values: dict[str, float]
    diagnostics: list[str]


def _percentile(values: list[int], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    return quantiles(values, n=100, method="inclusive")[percentile - 1]


def evaluate_quality(
    chunks: list[BenchmarkChunk],
    *,
    max_tokens: int,
    required_content: tuple[str, ...] = (),
    protected_content: tuple[str, ...] = (),
    intentional_repetitions: tuple[str, ...] = (),
) -> QualityReport:
    """Measure a normalized chunk list without depending on a splitter.

    ``required_content`` and ``protected_content`` come from the versioned
    dataset annotations.  Protected content that itself exceeds the budget is
    excluded from ordinary budget-violation accounting.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    texts = [chunk.text for chunk in chunks]
    diagnostics: list[str] = []
    missing = [
        item for item in required_content if not any(item in text for text in texts)
    ]
    for item in missing:
        diagnostics.append(f"missing required content: {item[:80]!r}")

    protected_breaks = 0
    for item in protected_content:
        appearances = sum(item in text for text in texts)
        if appearances != 1:
            protected_breaks += 1
            diagnostics.append(
                f"protected content appears in {appearances} chunks: {item[:80]!r}"
            )

    tokens = [chunk.token_count for chunk in chunks]
    non_protected = [chunk for chunk in chunks if not chunk.protected]
    violations = sum(chunk.token_count > max_tokens for chunk in non_protected)
    repeated = Counter(
        text for text in texts if text and text not in intentional_repetitions
    )
    duplicate_chunks = sum(count - 1 for count in repeated.values() if count > 1)
    estimate_errors = [
        abs(chunk.estimated_token_count - chunk.token_count) / chunk.token_count
        for chunk in chunks
        if chunk.estimated_token_count is not None and chunk.token_count > 0
    ]
    provenance = [
        chunk
        for chunk in chunks
        if chunk.start_line is not None and chunk.end_line is not None
    ]

    return QualityReport(
        values={
            "content_recall": 1.0
            if not required_content
            else 1 - len(missing) / len(required_content),
            "duplication_rate": duplicate_chunks / len(chunks) if chunks else 0.0,
            "budget_violation_rate": violations / len(non_protected)
            if non_protected
            else 0.0,
            "block_break_rate": protected_breaks / len(protected_content)
            if protected_content
            else 0.0,
            "chunk_utilization": (
                sum(min(chunk.token_count, max_tokens) for chunk in non_protected)
                / (len(non_protected) * max_tokens)
                if non_protected
                else 0.0
            ),
            "estimate_error": sum(estimate_errors) / len(estimate_errors)
            if estimate_errors
            else 0.0,
            "provenance_coverage": len(provenance) / len(chunks) if chunks else 0.0,
            "chunk_count": float(len(chunks)),
            "token_p50": _percentile(tokens, 50),
            "token_p95": _percentile(tokens, 95),
        },
        diagnostics=diagnostics,
    )

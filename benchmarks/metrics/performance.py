"""Timing, memory, and tokenizer-call measurements."""

from __future__ import annotations

import statistics
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from benchmarks.contract import SampleResult
from lumberjack.protocols import TokenizerProtocol


class CountingTokenizer(TokenizerProtocol):
    """A transparent tokenizer wrapper that records calls made by a splitter."""

    def __init__(self, tokenizer: TokenizerProtocol) -> None:
        self.tokenizer = tokenizer
        self.count_calls = 0
        self.encode_calls = 0

    def count(self, text: str, *, cache: bool = False) -> int:
        self.count_calls += 1
        return self.tokenizer.count(text, cache=cache)

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:
        self.encode_calls += 1
        return self.tokenizer.encode(text, cache=cache)


def measure_callable(action: Callable[[], Any]) -> tuple[Any, SampleResult]:
    """Run one action and record wall/CPU time plus Python allocation peak."""
    tracemalloc.start()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    result = action()
    sample = SampleResult(
        wall_time_seconds=time.perf_counter() - wall_start,
        cpu_time_seconds=time.process_time() - cpu_start,
        peak_memory_bytes=tracemalloc.get_traced_memory()[1],
        count_calls=0,
        encode_calls=0,
    )
    tracemalloc.stop()
    return result, sample


def summarize_samples(
    samples: list[SampleResult], source_bytes: int
) -> dict[str, float]:
    """Summarize raw samples with median, P95, and standard deviation."""
    if not samples:
        return {}

    def values(field: str) -> list[float]:
        return [float(asdict(sample)[field]) for sample in samples]

    summary: dict[str, float] = {}
    for field in ("wall_time_seconds", "cpu_time_seconds", "peak_memory_bytes"):
        observations = sorted(values(field))
        summary[f"{field}_median"] = statistics.median(observations)
        summary[f"{field}_p95"] = observations[
            max(0, round((len(observations) - 1) * 0.95))
        ]
        summary[f"{field}_stdev"] = statistics.pstdev(observations)
    summary["count_calls_median"] = statistics.median(
        sample.count_calls for sample in samples
    )
    summary["encode_calls_median"] = statistics.median(
        sample.encode_calls for sample in samples
    )
    median_wall = summary["wall_time_seconds_median"]
    summary["throughput_mb_per_second"] = (
        source_bytes / 1_000_000 / median_wall if median_wall else 0.0
    )
    return summary

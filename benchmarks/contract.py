"""Stable, serialisable contracts for benchmark inputs and outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """All settings that can affect a benchmark result."""

    tokenizer: str = "approx"
    splitter: str = "section"
    max_tokens: int = 240
    warmups: int = 1
    repetitions: int = 5
    allow_oversized_protected_blocks: bool = True

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.warmups < 0:
            raise ValueError("warmups cannot be negative")
        if self.repetitions <= 0:
            raise ValueError("repetitions must be positive")


@dataclass(frozen=True, slots=True)
class BenchmarkChunk:
    """Adapter-neutral representation consumed by quality metrics."""

    text: str
    token_count: int
    estimated_token_count: int | None = None
    chunk_type: str = "text"
    start_line: int | None = None
    end_line: int | None = None
    protected: bool = False


@dataclass(frozen=True, slots=True)
class SampleResult:
    """Raw timing and resource observations for one measured invocation."""

    wall_time_seconds: float
    cpu_time_seconds: float
    peak_memory_bytes: int
    count_calls: int
    encode_calls: int


@dataclass(slots=True)
class DocumentResult:
    """Result for a document, preserving raw observations for reproducibility."""

    document_id: str
    adapter: str
    chunks: list[BenchmarkChunk]
    samples: list[SampleResult]
    quality: dict[str, float]
    diagnostics: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BenchmarkReport:
    """JSON-report envelope written by :mod:`benchmarks.run`."""

    schema_version: str
    commit: str
    generated_at: str
    environment: dict[str, Any]
    config: BenchmarkConfig
    dataset_version: str
    results: list[DocumentResult]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

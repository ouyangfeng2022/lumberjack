"""Serializable contracts for parser-focused corpus benchmarks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PARSER_BENCHMARK_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ParserBenchmarkConfig:
    """Settings controlling deterministic corpus selection and parsing."""

    seed: int = 20260824
    sample_size_per_source: int = 500
    max_document_bytes: int = 20_000_000

    def __post_init__(self) -> None:
        if self.sample_size_per_source < 0:
            raise ValueError("sample_size_per_source cannot be negative")
        if self.max_document_bytes <= 0:
            raise ValueError("max_document_bytes must be positive")


@dataclass(frozen=True, slots=True)
class ParserDocumentResult:
    """Raw result for one selected corpus document."""

    dataset_id: str
    document_id: str
    format: str
    sha256: str
    source_bytes: int
    status: str
    wall_time_seconds: float
    cpu_time_seconds: float
    peak_memory_bytes: int
    content_token_recall: float | None = None
    source_token_count: int = 0
    matched_token_count: int = 0
    content_character_recall: float | None = None
    source_character_count: int = 0
    matched_character_count: int = 0
    section_count: int = 0
    block_count: int = 0
    inline_count: int = 0
    table_count: int = 0
    list_count: int = 0
    image_count: int = 0
    element_assertions: int = 0
    passed_element_assertions: int = 0
    element_accuracy: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass(slots=True)
class ParserBenchmarkReport:
    """Auditable envelope containing selection, raw results, and summary."""

    schema_version: str
    commit: str
    generated_at: str
    environment: dict[str, Any]
    config: ParserBenchmarkConfig
    dataset_version: str
    candidates_by_source: dict[str, int]
    selected_by_source: dict[str, int]
    results: list[ParserDocumentResult]
    summary: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

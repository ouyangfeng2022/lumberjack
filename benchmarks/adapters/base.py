"""Common adapter protocol and optional-dependency error handling."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from benchmarks.contract import BenchmarkChunk, BenchmarkConfig


class AdapterUnavailable(RuntimeError):
    """Raised when an explicitly requested optional benchmark tool is absent."""


class BenchmarkAdapter(Protocol):
    """Normalize one chunking implementation for the benchmark runner."""

    name: str

    def split(
        self, source: str, *, config: BenchmarkConfig, format: str = "markdown"
    ) -> list[BenchmarkChunk]: ...


def optional_adapter(
    name: str, loader: Callable[[], BenchmarkAdapter]
) -> BenchmarkAdapter:
    """Load an adapter with an error that names the missing benchmark extra."""
    try:
        return loader()
    except ImportError as error:
        raise AdapterUnavailable(
            f"{name} is not installed. Install the benchmark dependency group or "
            "choose --adapter lumberjack."
        ) from error

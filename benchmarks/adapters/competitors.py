"""Best-effort optional adapters for the benchmark comparison set."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from benchmarks.adapters.base import AdapterUnavailable
from benchmarks.contract import BenchmarkChunk, BenchmarkConfig


def _approx_chunks(parts: Iterable[Any]) -> list[BenchmarkChunk]:
    """Normalize third-party chunks that do not carry Lumberjack provenance."""
    return [
        BenchmarkChunk(
            text=str(getattr(part, "text", part)),
            token_count=max(
                1, len(str(getattr(part, "text", part)).encode("utf-8")) // 3
            ),
        )
        for part in parts
    ]


class UnstructuredBasicAdapter:
    name = "unstructured-basic"

    def split(self, source: str, *, config: BenchmarkConfig) -> list[BenchmarkChunk]:
        del config
        try:
            from unstructured.partition.md import partition_md
        except ImportError as error:
            raise AdapterUnavailable(
                "unstructured is required for unstructured-basic"
            ) from error
        return _approx_chunks(partition_md(text=source))


class UnstructuredByTitleAdapter:
    name = "unstructured-by-title"

    def split(self, source: str, *, config: BenchmarkConfig) -> list[BenchmarkChunk]:
        del config
        try:
            from unstructured.chunking.title import chunk_by_title
            from unstructured.partition.md import partition_md
        except ImportError as error:
            raise AdapterUnavailable(
                "unstructured is required for unstructured-by-title"
            ) from error
        return _approx_chunks(chunk_by_title(partition_md(text=source)))


class DoclingHierarchicalAdapter:
    name = "docling-hierarchical"

    def split(self, source: str, *, config: BenchmarkConfig) -> list[BenchmarkChunk]:
        del config
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as error:
            raise AdapterUnavailable(
                "docling is required for docling-hierarchical"
            ) from error
        converter = DocumentConverter()
        try:
            document = converter.convert_string(
                source, filename="benchmark.md"
            ).document
            return _approx_chunks([document.export_to_markdown()])
        except (AttributeError, TypeError) as error:
            raise AdapterUnavailable(
                "the installed docling version lacks the required Markdown conversion API"
            ) from error


class ChonkieRecursiveAdapter:
    name = "chonkie-recursive"

    def split(self, source: str, *, config: BenchmarkConfig) -> list[BenchmarkChunk]:
        try:
            from chonkie import RecursiveChunker
        except ImportError as error:
            raise AdapterUnavailable(
                "chonkie is required for chonkie-recursive"
            ) from error
        return _approx_chunks(RecursiveChunker(chunk_size=config.max_tokens)(source))

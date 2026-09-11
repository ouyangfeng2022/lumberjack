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

    def split(
        self, source: str, *, config: BenchmarkConfig, format: str = "markdown"
    ) -> list[BenchmarkChunk]:
        del config
        try:
            if format == "html":
                from unstructured.partition.html import partition_html

                elements = partition_html(text=source)
            else:
                from unstructured.partition.md import partition_md

                elements = partition_md(text=source)
        except ImportError as error:
            raise AdapterUnavailable(
                "unstructured is required for unstructured-basic"
            ) from error
        return _approx_chunks(elements)


class UnstructuredByTitleAdapter:
    name = "unstructured-by-title"

    def split(
        self, source: str, *, config: BenchmarkConfig, format: str = "markdown"
    ) -> list[BenchmarkChunk]:
        del config
        try:
            from unstructured.chunking.title import chunk_by_title

            if format == "html":
                from unstructured.partition.html import partition_html

                elements = partition_html(text=source)
            else:
                from unstructured.partition.md import partition_md

                elements = partition_md(text=source)
        except ImportError as error:
            raise AdapterUnavailable(
                "unstructured is required for unstructured-by-title"
            ) from error
        return _approx_chunks(chunk_by_title(elements))


def _convert_docling(converter, source: str, fmt: str):
    """Convert a text source with docling across its changing API.

    docling >= 2.120 requires ``convert_string(content, format)`` with an
    ``InputFormat``; older versions accepted ``filename=``. Support both so
    the adapters track whatever the benchmark group resolves.
    """
    try:
        from docling.datamodel.base_models import InputFormat

        input_format = InputFormat.HTML if fmt == "html" else InputFormat.MD
        return converter.convert_string(source, input_format).document
    except TypeError:
        return converter.convert_string(source, filename=f"benchmark.{fmt}").document


class DoclingHierarchicalAdapter:
    """Docling HierarchicalChunker: pure structure chunking without a budget."""

    name = "docling-hierarchical"

    def split(
        self, source: str, *, config: BenchmarkConfig, format: str = "markdown"
    ) -> list[BenchmarkChunk]:
        del config  # HierarchicalChunker has no token-budget parameter by design
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as error:
            raise AdapterUnavailable(
                "docling is required for docling-hierarchical"
            ) from error
        try:
            from docling_core.transforms.chunker import HierarchicalChunker
        except ImportError as error:
            raise AdapterUnavailable(
                "docling-core is required for docling-hierarchical"
            ) from error
        converter = DocumentConverter()
        try:
            document = _convert_docling(converter, source, format)
            chunker = HierarchicalChunker()
            return _approx_chunks(chunker.chunk(document))
        except (AttributeError, TypeError) as error:
            raise AdapterUnavailable(
                "the installed docling version lacks the required Markdown "
                "conversion or hierarchical chunking API"
            ) from error


class ChonkieRecursiveAdapter:
    name = "chonkie-recursive"

    def split(
        self, source: str, *, config: BenchmarkConfig, format: str = "markdown"
    ) -> list[BenchmarkChunk]:
        del format
        try:
            from chonkie import ByteTokenizer, RecursiveChunker
        except ImportError as error:
            raise AdapterUnavailable(
                "chonkie is required for chonkie-recursive"
            ) from error
        # chonkie counts with UTF-8 bytes here; the benchmark token unit is
        # UTF-8 bytes / 3, so translate the budget the same way the table
        # adapter and the LangChain recursive adapter translate theirs.
        chunker = RecursiveChunker(
            tokenizer=ByteTokenizer(), chunk_size=config.max_tokens * 3
        )
        return _approx_chunks(chunker(source))


class ChonkieTableAdapter:
    """Table-aware chonkie chunking: whole rows, header-aware packing."""

    name = "chonkie-table"

    def split(
        self, source: str, *, config: BenchmarkConfig, format: str = "markdown"
    ) -> list[BenchmarkChunk]:
        del format
        try:
            from chonkie import ByteTokenizer, TableChunker
        except ImportError as error:
            raise AdapterUnavailable(
                "chonkie>=1.7 is required for chonkie-table (TableChunker)"
            ) from error
        # chonkie tokenizes with byte counts here; the benchmark token unit is
        # UTF-8 bytes / 3, so translate the budget the same way the recursive
        # adapters translate character budgets.
        chunker = TableChunker(
            tokenizer=ByteTokenizer(), chunk_size=config.max_tokens * 3
        )
        return _approx_chunks(chunker.chunk(source))


def _offline_docling_tokenizer(max_tokens: int):
    """Build a docling BaseTokenizer that counts UTF-8 bytes / 3.

    The default HybridChunker tokenizer downloads a HuggingFace model; the
    offline approx tokenizer keeps the benchmark hermetic while matching the
    benchmark token unit. Docling resolves the chunk budget from
    ``get_max_tokens()``, so the benchmark budget must be returned there.
    Imported lazily so only docling-core is needed.
    """
    from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer

    class _ApproxTokenizer(BaseTokenizer):
        def count_tokens(self, text: str) -> int:
            return max(1, len(text.encode("utf-8")) // 3)

        def get_max_tokens(self) -> int:
            return max_tokens

        def get_tokenizer(self):
            # HybridChunker delegates overflow refinement to semchunk, which
            # requires a callable token counter; return the same byte/3 count.
            return lambda text: max(1, len(text.encode("utf-8")) // 3)

    return _ApproxTokenizer()


class DoclingHybridAdapter:
    """Docling HybridChunker: hierarchy-aware chunks merged under a budget."""

    name = "docling-hybrid"

    def split(
        self, source: str, *, config: BenchmarkConfig, format: str = "markdown"
    ) -> list[BenchmarkChunk]:
        try:
            from docling.document_converter import DocumentConverter
            from docling_core.transforms.chunker import HybridChunker
        except ImportError as error:
            raise AdapterUnavailable(
                "docling is required for docling-hybrid"
            ) from error
        converter = DocumentConverter()
        try:
            document = _convert_docling(converter, source, format)
            chunker = HybridChunker(
                tokenizer=_offline_docling_tokenizer(config.max_tokens),
                merge_peers=True,
            )
            return _approx_chunks(chunker.chunk(document))
        except (AttributeError, TypeError) as error:
            raise AdapterUnavailable(
                "the installed docling version lacks the required Markdown "
                "conversion or hybrid chunking API"
            ) from error

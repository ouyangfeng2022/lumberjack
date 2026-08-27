"""LangChain adapters, loaded only when the package is installed."""

from __future__ import annotations

from benchmarks.adapters.base import AdapterUnavailable
from benchmarks.contract import BenchmarkChunk, BenchmarkConfig


class LangChainRecursiveAdapter:
    name = "langchain-recursive"

    def split(
        self, source: str, *, config: BenchmarkConfig, format: str = "markdown"
    ) -> list[BenchmarkChunk]:
        del format
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except ImportError as error:
            raise AdapterUnavailable(
                "langchain-text-splitters is required for langchain-recursive"
            ) from error
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.max_tokens * 3,
            chunk_overlap=0,
            length_function=lambda text: max(1, len(text.encode("utf-8")) // 3),
        )
        return [
            BenchmarkChunk(
                text=text, token_count=max(1, len(text.encode("utf-8")) // 3)
            )
            for text in splitter.split_text(source)
        ]


class LangChainMarkdownAdapter(LangChainRecursiveAdapter):
    name = "langchain-markdown"

    def split(
        self, source: str, *, config: BenchmarkConfig, format: str = "markdown"
    ) -> list[BenchmarkChunk]:
        del config, format
        try:
            from langchain_text_splitters import MarkdownHeaderTextSplitter
        except ImportError as error:
            raise AdapterUnavailable(
                "langchain-text-splitters is required for langchain-markdown"
            ) from error
        splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,
        )
        return [
            BenchmarkChunk(
                text=document.page_content,
                token_count=max(1, len(document.page_content.encode("utf-8")) // 3),
            )
            for document in splitter.split_text(source)
        ]

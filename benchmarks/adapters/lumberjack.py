"""Native adapter, used as the reference implementation in every run."""

from __future__ import annotations

from typing import cast

from benchmarks.contract import BenchmarkChunk, BenchmarkConfig
from benchmarks.metrics.performance import CountingTokenizer
from lumberjack._internal.pipeline import TokenizerRegistry, build_pipeline
from lumberjack.models import (
    Document,
    InputFormat,
    complete_heading_path,
    render_heading_path,
)


class LumberjackAdapter:
    name = "lumberjack"

    def __init__(self) -> None:
        self.last_count_calls = 0
        self.last_encode_calls = 0

    def split(
        self, source: str, *, config: BenchmarkConfig, format: str = "markdown"
    ) -> list[BenchmarkChunk]:
        tokenizer = CountingTokenizer(TokenizerRegistry().create(config.tokenizer))
        pipeline = build_pipeline(
            tokenizer=tokenizer,
            splitter=config.splitter,
            max_tokens=config.max_tokens,
        )
        result = pipeline.run(Document(source=source, format=cast(InputFormat, format)))
        self.last_count_calls = tokenizer.count_calls
        self.last_encode_calls = tokenizer.encode_calls
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
                protected=chunk.chunk_type in {"code_fence", "code_block"},
            )
            for chunk in result.chunks
        ]

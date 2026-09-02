"""Focused tiktoken LRU-capacity probe feeding ``splitter-cache-probe.json``.

The full report (``benchmarks/splitter_report.py``) reads the probe to verify
that cache capacity is irrelevant under per-document cold-start semantics:
every document's split begins with a zero tokenizer cache in production, so
no splitter may depend on intra-split LRU reuse. This module regenerates
that JSON deterministically:

1. Generate the pinned slow document (``synthetic-long-sections`` index) with
   the shared seeded generator at the probe budget.
2. Parse it once; every variant splits the same ``DocTree``.
3. For each cache size, build a fresh tokenizer, warm up once (tokenizer
   load + steady state only), then time ``--repetitions`` splits with the
   cache cleared before every repetition and keep the median wall time.
4. One extra cold pass with a recording wrapper counts the distinct ``count()``
   texts a single split touches.

A large ``speedup`` (cache1000 / cache10000) would mean a variant has
regressed to relying on intra-split cache reuse, which production cold
starts never pay for.

Example:
    uv run python -m benchmarks.splitter_cache_probe
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmarks.splitter_random_corpus import generate_documents
from benchmarks.splitter_random_run import SPLITTER_CLASSES
from lumberjack.models import DocTree, Document
from lumberjack.parser.markdown import MarkdownParser
from lumberjack.tokenizer import TiktokenTokenizer, TokenizerProtocol

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "results" / "splitter-cache-probe.json"


class _RecordingTokenizer(TokenizerProtocol):
    """Wraps a tokenizer and records every ``count()`` text it receives."""

    def __init__(self, inner: TokenizerProtocol) -> None:
        self.inner = inner
        self.texts: set[str] = set()

    def count(self, text: str, *, cache: bool = False) -> int:
        self.texts.add(text)
        return self.inner.count(text, cache=cache)

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:
        return self.inner.encode(text, cache=cache)


@dataclass(frozen=True, slots=True)
class ProbeConfig:
    seed: int
    max_tokens: int
    document_index: int
    cache_sizes: tuple[int, ...]
    warmups: int
    repetitions: int


def _probe_document(config: ProbeConfig) -> tuple[str, int, DocTree]:
    documents = generate_documents(
        ["long-sections"],
        seed=config.seed,
        count_per_shape=config.document_index + 1,
        budget_tokens=config.max_tokens,
    )
    document = documents[config.document_index]
    source = document.source.encode("utf-8")
    tree = MarkdownParser().parse(
        Document(
            source=document.source,
            format="markdown",
            document_title=document.document_id,
        )
    )
    return document.document_id, len(source), tree


def run_probe(config: ProbeConfig) -> dict[str, Any]:
    document_id, source_bytes, tree = _probe_document(config)
    rows: list[dict[str, Any]] = []
    distinct_texts = 0
    for splitter_name in SPLITTER_CLASSES:
        medians: dict[int, float] = {}
        for cache_size in config.cache_sizes:
            tokenizer = TiktokenTokenizer(max_cache_size=cache_size)
            splitter = SPLITTER_CLASSES[splitter_name](
                tokenizer, max_tokens=config.max_tokens
            )
            for _ in range(config.warmups):
                splitter.split(tree)
            samples: list[float] = []
            for _ in range(config.repetitions):
                tokenizer.clear_cache()
                start = time.perf_counter()
                splitter.split(tree)
                samples.append(time.perf_counter() - start)
            medians[cache_size] = statistics.median(samples) * 1000
        recorder = _RecordingTokenizer(TiktokenTokenizer())
        recorder_splitter = SPLITTER_CLASSES[splitter_name](
            recorder, max_tokens=config.max_tokens
        )
        recorder_splitter.split(tree)
        distinct_texts = max(distinct_texts, len(recorder.texts))
        smallest, largest = config.cache_sizes[0], config.cache_sizes[-1]
        rows.append(
            {
                "splitter": splitter_name,
                **{f"cache{size}_ms": medians[size] for size in config.cache_sizes},
                "speedup": medians[smallest] / medians[largest],
                "distinct_count_texts": len(recorder.texts),
            }
        )
    return {
        "document_id": document_id,
        "source_bytes": source_bytes,
        "max_tokens": config.max_tokens,
        "cache_sizes": list(config.cache_sizes),
        "warmups": config.warmups,
        "repetitions": config.repetitions,
        "distinct_count_texts_max": distinct_texts,
        "rows": rows,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="tiktoken LRU-capacity probe for one slow document."
    )
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--max-tokens", type=int, default=600)
    parser.add_argument("--document-index", type=int, default=4)
    parser.add_argument("--cache-sizes", type=int, nargs="+", default=[1000, 10000])
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = ProbeConfig(
        seed=args.seed,
        max_tokens=args.max_tokens,
        document_index=args.document_index,
        cache_sizes=tuple(args.cache_sizes),
        warmups=args.warmups,
        repetitions=args.repetitions,
    )
    probe = run_probe(config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"document: {probe['document_id']} ({probe['source_bytes']} bytes)")
    for row in probe["rows"]:
        sizes = " | ".join(
            f"LRU={size}: {row[f'cache{size}_ms']:.1f} ms"
            for size in config.cache_sizes
        )
        print(
            f"{row['splitter']:<22} {sizes} | "
            f"speedup {row['speedup']:.1f}x | "
            f"distinct count() texts {row['distinct_count_texts']}"
        )
    print(f"probe written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

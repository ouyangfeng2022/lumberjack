"""End-to-end case C: exact vs incremental counting on one corpus.

Splits the same generated document twice — ``exact-section`` (full recount
at every budget decision) and ``section`` (incremental running estimate) —
under a counting tokenizer wrapper that records call counts and the volume
of text pushed through ``count()``. Prints chunk counts, tokenizer calls and
characters, wall time, and the split-time estimate error.

The example defaults to the offline byte-approximation tokenizer. Set
``LUMBERJACK_EXAMPLE_TOKENIZER=tiktoken`` to measure with tiktoken instead;
this requires the encoding to be cached locally or the network to be
reachable on first use.

Run:
    uv run python examples/incremental_counting.py
"""

from __future__ import annotations

import json
import os
import time

from lumberjack import Document, Lumberjack
from lumberjack.tokenizer import ApproxByteTokenizer, TiktokenTokenizer

MAX_TOKENS = 300
SECTIONS = [
    (
        "Design Reviews",
        "Reviews stay small on purpose; a decision log replaces consensus meetings.",
    ),
    (
        "Incidents",
        "Every incident gets an owner, a timeline, and one follow-up that ships.",
    ),
    ("On Call", "The rotation hands over with a written summary, never a verbal one."),
    (
        "Capacity",
        "Headroom is tracked per region and reviewed before each release train.",
    ),
]


class CountingTokenizer:
    """Tokenizer wrapper that counts ``count``/``encode`` invocations."""

    def __init__(self, base) -> None:
        self.base = base
        self.count_calls = 0
        self.encode_calls = 0
        self.count_chars = 0

    def count(self, text: str, *, cache: bool = False) -> int:
        self.count_calls += 1
        self.count_chars += len(text)
        return self.base.count(text, cache=cache)

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:
        self.encode_calls += 1
        return self.base.encode(text, cache=cache)


def build_document() -> str:
    parts = ["# Operations Handbook", "", "Working practices for the platform team."]
    for number in range(1, 25):
        name, sentence = SECTIONS[number % len(SECTIONS)]
        parts.append(f"## {name} {number}")
        for repeat in range(1, 7):
            parts.append(
                f"Rule {number}.{repeat}: {sentence} Apply it before the next "
                "deploy window opens and record the outcome."
            )
    return "\n\n".join(parts) + "\n"


def make_tokenizer() -> tuple[object, str]:
    if os.environ.get("LUMBERJACK_EXAMPLE_TOKENIZER", "").strip().lower() == "tiktoken":
        return TiktokenTokenizer(), "tiktoken (gpt-4o-mini / cl100k_base)"
    return ApproxByteTokenizer(), "approx (UTF-8 bytes / 3)"


def measure(splitter_name: str, base_tokenizer, document: str) -> dict:
    counting = CountingTokenizer(base_tokenizer)
    sawyer = Lumberjack(
        tokenizer=counting, splitter=splitter_name, max_tokens=MAX_TOKENS
    )
    started = time.perf_counter()
    result = sawyer.saw(Document(source=document, format="markdown"))
    elapsed_ms = (time.perf_counter() - started) * 1000

    errors = [
        abs(c.estimated_token_count - c.token_count) / c.token_count
        for c in result.chunks
        if c.token_count > 0
    ]
    mean_error = sum(errors) / len(errors) * 100 if errors else 0.0
    return {
        "chunk_count": len(result.chunks),
        "tokenizer_count_calls": counting.count_calls,
        "tokenizer_count_chars": counting.count_chars,
        "tokenizer_encode_calls": counting.encode_calls,
        "wall_time_ms": round(elapsed_ms, 1),
        "mean_estimate_error_pct": round(mean_error, 3),
        "total_tokens": sum(c.token_count for c in result.chunks),
    }


def main() -> int:
    document = build_document()
    base_tokenizer, tokenizer_name = make_tokenizer()

    exact = measure("exact-section", base_tokenizer, document)
    incremental = measure("section", base_tokenizer, document)

    summary = {
        "case": "incremental_counting",
        "document_bytes": len(document.encode("utf-8")),
        "max_tokens": MAX_TOKENS,
        "tokenizer": tokenizer_name,
        "exact_section": exact,
        "incremental_section": incremental,
        "reading": (
            "both runs emit the same authoritative token counts; exact "
            "planning re-encodes more total text because every budget "
            "decision recounts the growing rendered candidate (identical "
            "strings are deduplicated per split), while incremental plans "
            "from one pre-measure pass and keeps its estimate error small"
        ),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

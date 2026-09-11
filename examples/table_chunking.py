"""End-to-end case B: a wide table under a tight token budget.

Splits one 20-row Markdown pricing table with three configurations:
the default (header repeated in every table chunk), ``repeat_header``
disabled, and the table marked unsplittable so it stays whole as a
``protected`` chunk that deliberately exceeds the budget.

Run:
    uv run python examples/table_chunking.py
"""

from __future__ import annotations

import json

from lumberjack import Document, Lumberjack
from lumberjack.block import MarkdownTableConfig
from lumberjack.splitter import SectionSplitter
from lumberjack.tokenizer import ApproxByteTokenizer

MAX_TOKENS = 220

REGIONS = [
    ("us-east-1", "api-gateway", "16 vCPU", "64 GiB", "12000"),
    ("us-east-1", "auth-service", "8 vCPU", "32 GiB", "8000"),
    ("us-east-1", "search-indexer", "16 vCPU", "64 GiB", "15000"),
    ("eu-west-1", "billing-worker", "32 vCPU", "128 GiB", "30000"),
    ("eu-west-1", "analytics-db", "16 vCPU", "64 GiB", "22000"),
    ("eu-west-1", "stream-processor", "16 vCPU", "64 GiB", "20000"),
    ("ap-south-1", "ml-inference", "64 vCPU", "256 GiB", "90000"),
    ("ap-south-1", "edge-cache", "8 vCPU", "16 GiB", "5000"),
    ("ap-south-1", "queue-store", "16 vCPU", "64 GiB", "18000"),
    ("us-west-2", "vault-proxy", "4 vCPU", "16 GiB", "3000"),
]
REGIONS = REGIONS * 2  # widen the table well past the budget

TABLE_LINES = [
    "| Region | Service | CPU | Memory | Monthly Quota |",
    "| --- | --- | ---: | ---: | ---: |",
    *(
        f"| {region} | {service} | {cpu} | {mem} | {quota} |"
        for region, service, cpu, mem, quota in REGIONS
    ),
]
DOCUMENT = (
    "# Service Quotas\n\n"
    "Monthly quotas per service and region. Overages are billed per the "
    "pricing page.\n\n" + "\n".join(TABLE_LINES) + "\n"
)
HEADER = "\n".join(TABLE_LINES[:2])


def split_with(block_options: list) -> dict:
    splitter = SectionSplitter(
        ApproxByteTokenizer(),
        max_tokens=MAX_TOKENS,
        block_options=block_options,
    )
    result = Lumberjack(splitter=splitter).saw(
        Document(source=DOCUMENT, format="markdown")
    )
    # Oversized blocks (including split tables) are emitted with chunk_type
    # "paragraph", so identify table chunks by their rendered pipe rows.
    table_chunks = [c for c in result.chunks if c.body.lstrip().startswith("|")]
    return {
        "chunk_count": len(result.chunks),
        "table_chunk_count": len(table_chunks),
        "every_table_chunk_repeats_header": bool(table_chunks)
        and all(c.body.lstrip().startswith(HEADER) for c in table_chunks),
        "over_budget_chunks": sum(
            1 for c in result.chunks if c.token_count > MAX_TOKENS
        ),
        "total_tokens": sum(c.token_count for c in result.chunks),
    }


def main() -> int:
    summary = {
        "case": "table_chunking",
        "max_tokens": MAX_TOKENS,
        "repeat_header_default": split_with([MarkdownTableConfig()]),
        "repeat_header_off": split_with([MarkdownTableConfig(repeat_header=False)]),
        "unsplittable_table": split_with([MarkdownTableConfig(split=False)]),
        "notes": {
            "repeat_header_default": (
                "the header row is duplicated into every split table chunk so "
                "each chunk stays self-describing"
            ),
            "repeat_header_off": (
                "only the first table chunk carries the header; later chunks "
                "are raw rows"
            ),
            "unsplittable_table": (
                "the whole table stays one chunk that exceeds max_tokens by "
                "design — prefer a broken budget over a broken table"
            ),
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

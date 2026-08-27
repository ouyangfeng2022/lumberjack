"""End-to-end case A: a technical document split two ways.

Runs the same multi-level Markdown document through Lumberjack's structure-
aware ``sibling`` splitter and through a naive paragraph packer that ignores
document structure, then prints a JSON summary comparing chunk counts,
budget compliance, and heading provenance.

Run:
    uv run python examples/technical_document.py
"""

from __future__ import annotations

import json

from lumberjack import Document, Lumberjack
from lumberjack.tokenizer import ApproxByteTokenizer

MAX_TOKENS = 150

DOCUMENT = """# Platform Guide

This guide describes how to operate the ingestion platform in production.

## Installation

Install the collector on every node that produces telemetry. The daemon
watches log directories and forwards normalized events to the relay tier.

### Requirements

Each node needs two CPU cores, 4 GiB of memory, and outbound HTTPS access
to the relay endpoints listed in the network appendix.

## Configuration

Write a minimal configuration file before starting the daemon.

### Timeouts

The ingest timeout bounds how long the daemon waits for the relay to
acknowledge a batch before retrying with exponential backoff.

### Backpressure

When the relay reports sustained backpressure the daemon sheds debug-level
events first and warns-level events last.

## Troubleshooting

Check the daemon log for the phrase `relay stalled` before anything else;
it accounts for the majority of historical incidents.
"""


def naive_split(text: str, max_tokens: int) -> list[str]:
    """Pack blank-line-separated paragraphs without any document structure."""
    tokenizer = ApproxByteTokenizer()
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for paragraph in paragraphs:
        tokens = tokenizer.count(paragraph) + (1 if current else 0)
        if current and current_tokens + tokens > max_tokens:
            chunks.append("\n\n".join(current))
            current, current_tokens = [paragraph], tokenizer.count(paragraph)
        else:
            current.append(paragraph)
            current_tokens += tokens
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def main() -> int:
    tokenizer = ApproxByteTokenizer()

    structure = Lumberjack(
        tokenizer=tokenizer, splitter="sibling", max_tokens=MAX_TOKENS
    )
    result = structure.saw(Document(source=DOCUMENT, format="markdown"))

    naive_chunks = naive_split(DOCUMENT, MAX_TOKENS)

    naive_violations = sum(
        1 for chunk in naive_chunks if tokenizer.count(chunk) > MAX_TOKENS
    )
    budget_violations = sum(
        1 for chunk in result.chunks if chunk.token_count > MAX_TOKENS
    )
    provenance = [
        {
            "body_head": chunk.body.splitlines()[0][:60],
            "ancestor_headings": list(chunk.ancestor_headings),
            "own_heading": list(chunk.own_heading) if chunk.own_heading else None,
        }
        for chunk in result.chunks
    ]

    summary = {
        "case": "technical_document",
        "max_tokens": MAX_TOKENS,
        "structure_aware": {
            "splitter": "sibling",
            "chunk_count": len(result.chunks),
            "budget_violations": budget_violations,
            "chunks_with_heading_provenance": sum(
                1 for chunk in result.chunks if chunk.ancestor_headings
            ),
            "provenance": provenance,
        },
        "naive_text_split": {
            "chunk_count": len(naive_chunks),
            "budget_violations": naive_violations,
            "heading_provenance": None,
            "note": (
                "plain paragraph packing: headings travel as ordinary text, "
                "so retrieval cannot recover which section a chunk belongs to"
            ),
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

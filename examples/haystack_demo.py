"""Run Lumberjack chunks through a Haystack store and BM25 retrieval pipeline.

Run from a source checkout:

    uv sync --extra haystack
    uv run python examples/haystack_demo.py handbook.md --query "How do I install it?"
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from lumberjack import Lumberjack
from lumberjack.integrations import build_haystack_document_store


def run_demo(
    source: Path, *, query: str, max_tokens: int, top_k: int
) -> dict[str, Any]:
    """Split, write, retrieve, and compose a Haystack RAG prompt offline."""
    try:
        from haystack import Pipeline
        from haystack.components.builders import PromptBuilder
        from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
    except ModuleNotFoundError as error:
        raise ImportError(
            "This demo requires `uv sync --extra haystack` "
            "or `pip install lumberjack-py[haystack]`."
        ) from error

    result = Lumberjack(max_tokens=max_tokens).saw(source)
    document_store = build_haystack_document_store(result.chunks)
    pipeline = Pipeline()
    pipeline.add_component(
        "retriever", InMemoryBM25Retriever(document_store=document_store, top_k=top_k)
    )
    pipeline.add_component(
        "prompt_builder",
        PromptBuilder(
            template=(
                "Answer using the retrieved documents.\n"
                "{% for document in documents %}{{ document.content }}\n{% endfor %}"
                "Question: {{ question }}"
            )
        ),
    )
    pipeline.connect("retriever.documents", "prompt_builder.documents")
    pipeline_result = pipeline.run(
        {"retriever": {"query": query}, "prompt_builder": {"question": query}},
        include_outputs_from={"retriever"},
    )
    retrieved = pipeline_result["retriever"]["documents"]

    return {
        "document": result.document.title,
        "chunk_count": len(result.chunks),
        "retrieved": [
            {
                "chunk_id": document.id,
                "score": document.score,
                "body": document.content,
                "metadata": document.meta,
            }
            for document in retrieved
        ],
        "prompt": pipeline_result["prompt_builder"]["prompt"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Lumberjack -> Haystack indexing and retrieval demo."
    )
    parser.add_argument("source", type=Path, help="Input file supported by Lumberjack")
    parser.add_argument("--query", default="What does this document explain?")
    parser.add_argument("--max-tokens", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_tokens < 1 or args.top_k < 1:
        raise ValueError("--max-tokens and --top-k must be at least 1")
    print(
        json.dumps(
            run_demo(
                args.source,
                query=args.query,
                max_tokens=args.max_tokens,
                top_k=args.top_k,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

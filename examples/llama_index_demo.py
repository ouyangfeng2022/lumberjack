"""Index Lumberjack chunks with LlamaIndex and inspect retrieval provenance.

Run from a source checkout:

    uv sync --extra llama-index
    uv run python examples/llama_index_demo.py handbook.md --query "How do I install it?"

The demo uses LlamaIndex's built-in mock embedding model and LLM, so it runs
offline. Replace them with configured production models while keeping the same
``build_llamaindex_index`` / retriever / query-engine flow.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from lumberjack import Lumberjack
from lumberjack.integrations import build_llamaindex_index, chunk_metadata


def run_demo(
    source: Path,
    *,
    query: str,
    max_tokens: int,
    top_k: int,
) -> dict[str, Any]:
    """Split ``source``, index its chunks, retrieve, and query with LlamaIndex."""
    try:
        from llama_index.core.embeddings import MockEmbedding
        from llama_index.core.llms.mock import MockLLM
    except ModuleNotFoundError as error:
        raise ImportError(
            "This demo requires `uv sync --extra llama-index` "
            "or `pip install lumberjack-py[llama-index]`."
        ) from error

    result = Lumberjack(max_tokens=max_tokens).saw(source)
    index = build_llamaindex_index(
        result.chunks,
        embed_model=MockEmbedding(embed_dim=8),
    )
    retrieved = index.as_retriever(similarity_top_k=top_k).retrieve(query)
    response = index.as_query_engine(llm=MockLLM(), similarity_top_k=top_k).query(query)

    return {
        "document": result.document.title,
        "chunk_count": len(result.chunks),
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "body": chunk.body,
                "metadata": chunk_metadata(chunk),
            }
            for chunk in result.chunks
        ],
        "retrieved": [
            {
                "chunk_id": item.node_id,
                "score": item.score,
                "body": item.text,
                "metadata": item.metadata,
            }
            for item in retrieved
        ],
        "response": str(response),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Lumberjack -> LlamaIndex indexing, retrieval, and query demo."
    )
    parser.add_argument("source", type=Path, help="Input file supported by Lumberjack")
    parser.add_argument(
        "--query",
        default="What does this document explain?",
        help="Query sent to the LlamaIndex retriever and query engine",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=300,
        help="Lumberjack token budget per chunk (default: 300)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Maximum retrieved LlamaIndex nodes (default: 3)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_tokens < 1:
        raise ValueError("--max-tokens must be at least 1")
    if args.top_k < 1:
        raise ValueError("--top-k must be at least 1")
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

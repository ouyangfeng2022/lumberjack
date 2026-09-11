"""Run Lumberjack chunks through a LangChain vector store and RAG runnable.

Run from a source checkout:

    uv sync --extra langchain
    uv run python examples/langchain_demo.py handbook.md --query "How do I install it?"
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from lumberjack import Lumberjack
from lumberjack.integrations import build_langchain_vectorstore


def run_demo(
    source: Path, *, query: str, max_tokens: int, top_k: int
) -> dict[str, Any]:
    """Split, embed, retrieve, and invoke a LangChain RAG runnable offline."""
    try:
        from langchain_core.embeddings import DeterministicFakeEmbedding
        from langchain_core.language_models.fake import FakeListLLM
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import PromptTemplate
    except ModuleNotFoundError as error:
        raise ImportError(
            "This demo requires `uv sync --extra langchain` "
            "or `pip install lumberjack-py[langchain]`."
        ) from error

    result = Lumberjack(max_tokens=max_tokens).saw(source)
    vectorstore = build_langchain_vectorstore(
        result.chunks, embeddings=DeterministicFakeEmbedding(size=8)
    )
    retrieved = vectorstore.similarity_search(query, k=top_k)
    context = "\n\n".join(document.page_content for document in retrieved)
    rag_chain = (
        PromptTemplate.from_template("Context:\n{context}\n\nQuestion: {question}")
        | FakeListLLM(responses=["Offline LangChain demo response."])
        | StrOutputParser()
    )
    response = rag_chain.invoke({"context": context, "question": query})

    return {
        "document": result.document.title,
        "chunk_count": len(result.chunks),
        "retrieved": [
            {
                "chunk_id": document.id,
                "body": document.page_content,
                "metadata": document.metadata,
            }
            for document in retrieved
        ],
        "response": response,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Lumberjack -> LangChain indexing, retrieval, and RAG demo."
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

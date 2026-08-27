"""Smoke tests for the optional competitor adapters.

These run only when the corresponding ``benchmark`` dependency group package
is importable; otherwise they skip. They pin the adapter wiring (imports,
names, output normalization) so a dependency upgrade that breaks an adapter
surfaces here first.
"""

from __future__ import annotations

import pytest

from benchmarks.contract import BenchmarkConfig

SIMPLE_MD = (
    "# Guide\n\nIntro paragraph.\n\n## Table\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n"
)


def test_chonkie_table_adapter_chunks_tables() -> None:
    pytest.importorskip("chonkie", reason="benchmark group not installed")
    from chonkie import TableChunker  # ty: ignore[unresolved-import]

    from benchmarks.adapters.competitors import ChonkieTableAdapter

    del TableChunker  # capability probe: chonkie>=1.7 provides TableChunker

    adapter = ChonkieTableAdapter()
    chunks = adapter.split(SIMPLE_MD, config=BenchmarkConfig(max_tokens=240))
    assert len(chunks) >= 1
    assert all(chunk.token_count >= 1 for chunk in chunks)
    assert any("| A | B |" in chunk.text for chunk in chunks)


def test_docling_hybrid_adapter_uses_offline_tokenizer() -> None:
    pytest.importorskip("docling", reason="benchmark group not installed")
    from benchmarks.adapters.competitors import (
        DoclingHybridAdapter,
        _offline_docling_tokenizer,
    )

    tokenizer = _offline_docling_tokenizer()
    assert tokenizer.count_tokens("hello world") == max(1, len(b"hello world") // 3)

    adapter = DoclingHybridAdapter()
    chunks = adapter.split(SIMPLE_MD, config=BenchmarkConfig(max_tokens=240))
    assert len(chunks) >= 1
    assert all(chunk.token_count >= 1 for chunk in chunks)

from __future__ import annotations

from pathlib import Path

from lumberjack.core.parser import MarkdownParser
from lumberjack.core.splitter import MarkdownSplitter
from lumberjack.core.tokenizers import SimpleCharTokenizer
from lumberjack.models import SplitOptions

FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "markdown" / "sample.md").read_text(
    encoding="utf-8"
)


def test_splitter_preserves_heading_context() -> None:
    """Test that splitter preserves heading hierarchy in chunks."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())
    chunks = splitter.split(document, SplitOptions(max_tokens=140, min_tokens=20))

    assert len(chunks) >= 2
    assert any("# Overview" in chunk.text for chunk in chunks)
    assert any("## Details" in chunk.text for chunk in chunks)


def test_splitter_respects_budget_except_unsplittable_code_fence() -> None:
    """Test that splitter respects token budget except for code fences."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    splitter = MarkdownSplitter(tokenizer=SimpleCharTokenizer())
    chunks = splitter.split(document, SplitOptions(max_tokens=180, min_tokens=20))

    oversized = [chunk for chunk in chunks if chunk.token_count > 180]
    if oversized:
        assert all("```" in chunk.text for chunk in oversized)

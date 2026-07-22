from __future__ import annotations

from pathlib import Path
from typing import Literal

from .models import Chunk
from .parser import AutoParser
from .splitter import SiblingSplitter
from .tokenizer import ApproxCharTokenizer


def lumber(
    source: str | bytes | Path,
    *,
    format: Literal["auto", "markdown", "html", "docx"] = "auto",
    max_tokens: int = 1200,
) -> list[Chunk]:
    """Split a document with the default automatic incremental pipeline."""
    parser = AutoParser(format=format)
    tokenizer = ApproxCharTokenizer()
    splitter = SiblingSplitter(tokenizer, max_tokens=max_tokens)
    return splitter.split(parser.parse(source))


__all__ = ["lumber"]

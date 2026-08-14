from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import lumberjack
from lumberjack import Lumberjack, Tree
from lumberjack.models import (
    Chunk,
    ChunkDraft,
    DocTree,
    DocumentBlock,
    DocumentInline,
)
from lumberjack.normalizer import TextNormalizer
from lumberjack.parser import AutoParser, DocxParser, HTMLParser, MarkdownParser
from lumberjack.protocols import (
    ParserProtocol,
    SplitterProtocol,
    TextNormalizerProtocol,
    TextTransformerProtocol,
    TokenizerProtocol,
)
from lumberjack.splitter import ExactSiblingSplitter, SiblingSplitter
from lumberjack.tokenizer import ApproxByteTokenizer
from lumberjack.transformer import PlainTextTransformer, TextTransformer


def test_top_level_exports_lumberjack_and_tree() -> None:
    assert lumberjack.__all__ == ["Lumberjack", "Tree"]
    assert Lumberjack and Tree
    assert not hasattr(lumberjack, "lumber")


def test_public_lumber_pipeline_components() -> None:
    assert AutoParser and MarkdownParser and HTMLParser and DocxParser
    assert SiblingSplitter and ExactSiblingSplitter and ApproxByteTokenizer
    assert TextNormalizer and TextTransformer and PlainTextTransformer
    assert DocTree and ChunkDraft and Chunk and DocumentBlock and DocumentInline
    assert ParserProtocol and SplitterProtocol and TokenizerProtocol
    assert TextNormalizerProtocol and TextTransformerProtocol


def test_removed_component_packages_do_not_exist() -> None:
    package_root = Path(lumberjack.__file__).parent
    assert not (package_root / "core").exists()
    assert not (package_root / "feller").exists()
    assert not (package_root / "sawyer").exists()
    assert not (package_root / "scaler.py").exists()


def test_chunk_serialization_fields() -> None:
    assert [field.name for field in fields(Chunk)] == [
        "chunk_id",
        "chunk_type",
        "body",
        "token_count",
        "estimated_token_count",
        "headings_token_count",
        "body_token_count",
        "ancestor_headings",
        "own_heading",
        "section_level",
        "document_title",
        "document_path",
        "start_line",
        "end_line",
    ]

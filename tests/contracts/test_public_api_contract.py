from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import lumberjack
from lumberjack import Document, Lumberjack
from lumberjack.models import (
    Chunk,
    ChunkDraft,
    DocTree,
    DocumentBlock,
    DocumentInline,
    SplitResult,
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
from lumberjack.splitter import ExactSiblingSplitter, SectionSplitter, SiblingSplitter
from lumberjack.tokenizer import ApproxByteTokenizer
from lumberjack.transformer import PlainTextTransformer, TextTransformer


def test_top_level_exports_lumberjack_and_document() -> None:
    assert lumberjack.__all__ == ["Document", "Lumberjack"]
    assert Lumberjack and Document
    assert not hasattr(lumberjack, "lumber")


def test_public_lumber_pipeline_components() -> None:
    assert AutoParser and MarkdownParser and HTMLParser and DocxParser
    assert SiblingSplitter and ExactSiblingSplitter and ApproxByteTokenizer
    assert TextNormalizer and TextTransformer and PlainTextTransformer
    assert DocTree and ChunkDraft and Chunk and DocumentBlock and DocumentInline
    assert SplitResult
    assert ParserProtocol and SplitterProtocol and TokenizerProtocol
    assert TextNormalizerProtocol and TextTransformerProtocol


def test_lumberjack_defaults_use_the_incremental_section_pipeline() -> None:
    pipeline = Lumberjack()

    assert isinstance(pipeline.tokenizer, ApproxByteTokenizer)
    assert isinstance(pipeline.parser, AutoParser)
    assert isinstance(pipeline.splitter, SectionSplitter)
    assert pipeline.splitter.max_tokens == 1200
    assert pipeline.splitter.skip_empty_sections is True
    assert pipeline.finalizer.skip_empty_sections is True


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

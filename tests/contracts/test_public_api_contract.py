from __future__ import annotations

import inspect
from dataclasses import fields
from importlib.util import find_spec

import lumberjack
import lumberjack.parser as parser_package
from lumberjack import lumber
from lumberjack.block import (
    BlockConfig,
    BlockKind,
    CustomBlockConfig,
    HTMLTableConfig,
    MarkdownTableConfig,
)
from lumberjack.models import Chunk, DocumentAST, DocumentBlock, DocumentInline
from lumberjack.parser import AutoParser, DocxParser, HTMLParser, MarkdownParser
from lumberjack.protocols import ParserProtocol, SplitterProtocol, TokenizerProtocol
from lumberjack.splitter import (
    ExactSectionSplitter,
    ExactSiblingSplitter,
    ExactSubtreeSplitter,
    SectionSplitter,
    SiblingSplitter,
    SubtreeSplitter,
)
from lumberjack.tokenizer import (
    ApproxByteTokenizer,
    TiktokenTokenizer,
    TransformersTokenizer,
)


def test_top_level_only_exports_lumber() -> None:
    assert lumberjack.__all__ == ["lumber"]


def test_lumber_is_deliberately_minimal() -> None:
    parameters = inspect.signature(lumber).parameters
    assert list(parameters) == ["source", "format", "max_tokens"]
    assert parameters["format"].default == "auto"
    assert parameters["max_tokens"].default == 1200


def test_public_components_own_their_implementations() -> None:
    assert AutoParser and MarkdownParser and HTMLParser and DocxParser
    assert SiblingSplitter and SubtreeSplitter and SectionSplitter
    assert ExactSiblingSplitter and ExactSubtreeSplitter and ExactSectionSplitter
    assert ApproxByteTokenizer and TiktokenTokenizer and TransformersTokenizer
    assert BlockConfig and BlockKind and MarkdownTableConfig and HTMLTableConfig
    assert CustomBlockConfig
    assert DocumentAST and DocumentBlock and DocumentInline
    assert ParserProtocol and SplitterProtocol and TokenizerProtocol
    assert AutoParser.__module__ == "lumberjack.parser.auto"
    assert SiblingSplitter.__module__ == "lumberjack.splitter.sibling"
    assert ApproxByteTokenizer.__module__ == "lumberjack.tokenizer"
    assert BlockConfig.__module__ == "lumberjack.block"
    assert DocumentAST.__module__ == "lumberjack.models"


def test_core_package_does_not_exist() -> None:
    assert find_spec("lumberjack.core") is None


def test_parser_package_has_no_module_level_parse_function() -> None:
    assert not hasattr(parser_package, "parse")


def test_default_splitter_names_are_incremental() -> None:
    assert SiblingSplitter.__name__ == "IncrementalSiblingSplitter"
    assert SubtreeSplitter.__name__ == "IncrementalSubtreeSplitter"
    assert SectionSplitter.__name__ == "IncrementalSectionSplitter"
    assert ExactSiblingSplitter is not SiblingSplitter
    assert ExactSubtreeSplitter is not SubtreeSplitter
    assert ExactSectionSplitter is not SectionSplitter


def test_chunk_serialization_fields() -> None:
    assert [field.name for field in fields(Chunk)] == [
        "chunk_id",
        "chunk_type",
        "body",
        "token_count",
        "estimated_token_count",
        "headings",
        "section_level",
        "document_title",
        "document_path",
        "start_line",
        "end_line",
    ]

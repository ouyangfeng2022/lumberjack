from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import lumberjack
from lumberjack import Lumberjack, Tree
from lumberjack.feller import AutoFeller, DocxFeller, HTMLFeller, MarkdownFeller
from lumberjack.models import Bundle, Chunk, DocumentBlock, DocumentInline, Log
from lumberjack.planer import PlainTextPlaner, Planer
from lumberjack.protocols import (
    FellerProtocol,
    PlanerProtocol,
    SawyerProtocol,
    ScalerProtocol,
    SeasonerProtocol,
)
from lumberjack.sawyer import ExactSiblingSawyer, SiblingSawyer
from lumberjack.scaler import ApproxByteScaler
from lumberjack.seasoner import Seasoner


def test_top_level_exports_lumberjack_and_tree() -> None:
    assert lumberjack.__all__ == ["Lumberjack", "Tree"]
    assert Lumberjack and Tree
    assert not hasattr(lumberjack, "lumber")


def test_public_lumber_pipeline_components() -> None:
    assert AutoFeller and MarkdownFeller and HTMLFeller and DocxFeller
    assert SiblingSawyer and ExactSiblingSawyer and ApproxByteScaler
    assert Seasoner and Planer and PlainTextPlaner
    assert Log and Bundle and Chunk and DocumentBlock and DocumentInline
    assert FellerProtocol and SawyerProtocol and ScalerProtocol
    assert SeasonerProtocol and PlanerProtocol


def test_removed_component_packages_do_not_exist() -> None:
    package_root = Path(lumberjack.__file__).parent
    assert not (package_root / "core").exists()
    assert not (package_root / "parser").exists()
    assert not (package_root / "splitter").exists()
    assert not (package_root / "tokenizer.py").exists()


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

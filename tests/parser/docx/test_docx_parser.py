from __future__ import annotations

from lumberjack import Lumberjack
from lumberjack.feller.docx import DocxFeller
from lumberjack.sawyer import SiblingSawyer
from tests.helpers import FIXTURES_DIR, CharacterScaler, saw, sawyer_options

FIXTURES_ROOT = FIXTURES_DIR / "docx"
SAMPLE_DOCX = (FIXTURES_ROOT / "sample.docx").read_bytes()


def test_docx_parser_parses_headings() -> None:
    parser = DocxFeller()
    doc = parser.fell(SAMPLE_DOCX)

    assert doc.title == "Test Document"
    assert len(doc.root.children) >= 1

    h1_titles = [c.title for c in doc.root.children if c.level == 1]
    assert "Introduction" in h1_titles
    assert "Methods" in h1_titles


def test_docx_parser_parses_nested_headings() -> None:
    parser = DocxFeller()
    doc = parser.fell(SAMPLE_DOCX)

    intro = next(c for c in doc.root.children if c.title == "Introduction")
    assert any(c.title == "Background" for c in intro.children)
    assert any(c.level == 2 for c in intro.children)


def test_docx_parser_parses_table() -> None:
    parser = DocxFeller()
    doc = parser.fell(SAMPLE_DOCX)

    all_blocks: list[str] = []

    def _collect(section):
        all_blocks.extend(b.kind for b in section.blocks)
        for child in section.children:
            _collect(child)

    _collect(doc.root)
    assert "table" in all_blocks


def test_docx_parser_parses_lists() -> None:
    parser = DocxFeller()
    doc = parser.fell(SAMPLE_DOCX)

    all_blocks: list[str] = []

    def _collect(section):
        all_blocks.extend(b.kind for b in section.blocks)
        for child in section.children:
            _collect(child)

    _collect(doc.root)
    assert "list" in all_blocks


def test_docx_parser_block_kinds() -> None:
    parser = DocxFeller()
    kinds = parser.block_kinds

    assert kinds == DocxFeller.default_block_kinds
    assert kinds == frozenset(
        {
            "paragraph",
            "table",
            "list",
            "list_item",
            "code_block",
            "blockquote",
        }
    )
    assert isinstance(kinds, frozenset)


def test_docx_lumber_integration() -> None:
    chunks = Lumberjack(max_tokens=500).saw(
        FIXTURES_ROOT / "sample.docx",
    )
    assert len(chunks) >= 1
    assert chunks[0].document_title == "Test Document"
    assert all(chunk.body for chunk in chunks)


def test_docx_lumber_bytes_input() -> None:
    chunks = Lumberjack(max_tokens=500).saw(SAMPLE_DOCX, format="docx")
    assert len(chunks) >= 1
    assert chunks[0].document_title == "Test Document"


def test_docx_through_splitter() -> None:
    parser = DocxFeller()
    doc = parser.fell(SAMPLE_DOCX)

    scaler = CharacterScaler()
    options = sawyer_options(max_tokens=200, merge_below_ratio=0.1)
    sawyer = SiblingSawyer(scaler=scaler, **options)
    chunks = saw(sawyer, doc)

    assert len(chunks) >= 1
    assert all(chunk.token_count > 0 for chunk in chunks)


def test_docx_parser_section_tree_structure() -> None:
    parser = DocxFeller()
    doc = parser.fell(SAMPLE_DOCX)

    def check_levels(section):
        for child in section.children:
            assert child.level > section.level
            check_levels(child)

    check_levels(doc.root)


def test_docx_parser_paragraphs_have_text() -> None:
    parser = DocxFeller()
    doc = parser.fell(SAMPLE_DOCX)

    def _check(section):
        for block in section.blocks:
            if block.kind == "paragraph":
                assert block.text, f"Empty paragraph in {section.title}"
        for child in section.children:
            _check(child)

    _check(doc.root)

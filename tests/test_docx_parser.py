from __future__ import annotations

from pathlib import Path

from lumberjack import lumber
from lumberjack.core.docx import DocxParser
from lumberjack.core.markdown.splitter import RecursiveMarkdownSplitter
from lumberjack.core.models import SplitOptions
from lumberjack.core.tokenizers import SimpleCharTokenizer

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "docx"
SAMPLE_DOCX = (FIXTURES_ROOT / "sample.docx").read_bytes()


def test_docx_parser_parses_headings() -> None:
    parser = DocxParser()
    doc = parser.parse(SAMPLE_DOCX)

    assert doc.title == "Test Document"
    assert len(doc.root.children) >= 1

    h1_titles = [c.title for c in doc.root.children if c.level == 1]
    assert "Introduction" in h1_titles
    assert "Methods" in h1_titles


def test_docx_parser_parses_nested_headings() -> None:
    parser = DocxParser()
    doc = parser.parse(SAMPLE_DOCX)

    intro = next(c for c in doc.root.children if c.title == "Introduction")
    assert any(c.title == "Background" for c in intro.children)
    assert any(c.level == 2 for c in intro.children)


def test_docx_parser_parses_table() -> None:
    parser = DocxParser()
    doc = parser.parse(SAMPLE_DOCX)

    all_blocks: list[str] = []

    def _collect(section):
        all_blocks.extend(b.kind for b in section.blocks)
        for child in section.children:
            _collect(child)

    _collect(doc.root)
    assert "table" in all_blocks


def test_docx_parser_parses_lists() -> None:
    parser = DocxParser()
    doc = parser.parse(SAMPLE_DOCX)

    all_blocks: list[str] = []

    def _collect(section):
        all_blocks.extend(b.kind for b in section.blocks)
        for child in section.children:
            _collect(child)

    _collect(doc.root)
    assert "list" in all_blocks


def test_docx_parser_block_kinds() -> None:
    parser = DocxParser()
    kinds = parser.block_kinds
    assert "paragraph" in kinds
    assert "table" in kinds
    assert "list" in kinds
    assert isinstance(kinds, frozenset)


def test_docx_lumber_integration() -> None:
    chunks = lumber(
        Path(FIXTURES_ROOT / "sample.docx"),
        max_tokens=500,
    )
    assert len(chunks) >= 1
    assert chunks[0].document_title == "Test Document"
    assert all(chunk.body for chunk in chunks)


def test_docx_lumber_bytes_input() -> None:
    chunks = lumber(SAMPLE_DOCX, max_tokens=500, format="docx")
    assert len(chunks) >= 1
    assert chunks[0].document_title == "Test Document"


def test_docx_through_splitter() -> None:
    parser = DocxParser()
    doc = parser.parse(SAMPLE_DOCX)

    tokenizer = SimpleCharTokenizer()
    options = SplitOptions(max_tokens=200, merge_below_tokens=20)
    splitter = RecursiveMarkdownSplitter(tokenizer=tokenizer, options=options)
    chunks = splitter.split(doc)

    assert len(chunks) >= 1
    assert all(chunk.token_count > 0 for chunk in chunks)


def test_docx_parser_section_tree_structure() -> None:
    parser = DocxParser()
    doc = parser.parse(SAMPLE_DOCX)

    def check_levels(section):
        for child in section.children:
            assert child.level > section.level
            check_levels(child)

    check_levels(doc.root)


def test_docx_parser_paragraphs_have_text() -> None:
    parser = DocxParser()
    doc = parser.parse(SAMPLE_DOCX)

    def _check(section):
        for block in section.blocks:
            if block.kind == "paragraph":
                assert block.text, f"Empty paragraph in {section.title}"
        for child in section.children:
            _check(child)

    _check(doc.root)

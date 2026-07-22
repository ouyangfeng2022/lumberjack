from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

import lumberjack
from lumberjack import lumber
from lumberjack.block import (
    BlockConfig,
    BlockKind,
    CustomBlockConfig,
    HTMLTableConfig,
    MarkdownTableConfig,
)
from lumberjack.parser import AutoParser, MarkdownParser
from lumberjack.splitter import ExactSiblingSplitter, SiblingSplitter
from lumberjack.tokenizer import ApproxByteTokenizer
from tests.helpers import FIXTURES_DIR

FIXTURES = FIXTURES_DIR
MARKDOWN_PATH = FIXTURES / "markdown" / "sample.md"
DOCX_PATH = FIXTURES / "docx" / "sample.docx"


def test_package_exports_only_lumber_at_top_level() -> None:
    assert lumberjack.__all__ == ["lumber"]


def test_minimal_lumber_pipeline_splits_markdown() -> None:
    chunks = lumber("# Guide\n\nHello world", max_tokens=100)
    assert chunks
    assert chunks[0].document_title == "Guide"
    assert "Hello world" in chunks[0].body


def test_lumber_auto_detects_path_and_sets_document_path() -> None:
    chunks = lumber(MARKDOWN_PATH, max_tokens=500)
    assert chunks
    assert all(chunk.document_path == str(MARKDOWN_PATH) for chunk in chunks)


@pytest.mark.parametrize(
    ("suffix", "content", "expected_title"),
    [
        (".md", "# Markdown title\n\nBody", "Markdown title"),
        (".html", "<h1>HTML title</h1><p>Body</p>", "HTML title"),
        (".unknown", "<h1>Detected HTML</h1><p>Body</p>", "Detected HTML"),
    ],
)
def test_auto_parser_detects_path_suffix_or_unknown_extension_content(
    tmp_path: Path,
    suffix: str,
    content: str,
    expected_title: str,
) -> None:
    path = tmp_path / f"document{suffix}"
    path.write_text(content, encoding="utf-8")

    document = AutoParser().parse(path)

    assert document.title == expected_title
    assert document.source_path == str(path)


def test_auto_parser_detects_docx_path_and_metadata_override() -> None:
    document = AutoParser().parse(
        DOCX_PATH,
        metadata_overrides={"author": "Override"},
    )
    assert document.title == "Test Document"
    assert document.metadata["author"] == "Override"
    assert document.source_path == str(DOCX_PATH)


def test_lumber_accepts_docx_bytes() -> None:
    chunks = lumber(DOCX_PATH.read_bytes(), max_tokens=500)
    assert chunks
    assert chunks[0].document_title == "Test Document"
    assert any("Introduction" in chunk.body for chunk in chunks)


def test_auto_parser_treats_string_as_content_not_path(tmp_path: Path) -> None:
    apparent_path = tmp_path / "guide.md"
    apparent_path.write_text("# From disk", encoding="utf-8")

    document = AutoParser().parse(str(apparent_path))

    assert document.source_path is None
    assert str(apparent_path) in document.root.blocks[0].text


def test_auto_parser_uses_source_path_suffix_for_text() -> None:
    document = AutoParser().parse("<h1>Looks like HTML</h1>", source_path="captured.md")
    assert document.source_path == "captured.md"
    assert document.root.blocks[0].kind == BlockKind.HTML_BLOCK


def test_auto_parser_detects_structural_html_content() -> None:
    document = AutoParser().parse("<!doctype html><h1>Title</h1><p>Body</p>")
    assert document.title == "Title"
    assert document.root.children[0].blocks[0].text == "Body"


def test_html_metadata_override_has_priority() -> None:
    document = AutoParser(format="html").parse(
        '<meta name="author" content="Ada"><h1>Title</h1>',
        metadata_overrides={"author": "Grace"},
    )
    assert document.metadata["author"] == "Grace"


def test_auto_parser_falls_back_to_markdown() -> None:
    document = AutoParser().parse("# Markdown\n\nBody")
    assert document.title == "Markdown"
    assert document.root.children[0].title == "Markdown"


def test_auto_parser_forced_format_skips_inference() -> None:
    document = AutoParser(format="markdown").parse("<h1>HTML</h1>")
    assert document.root.blocks[0].kind == BlockKind.HTML_BLOCK


def test_auto_parser_rejects_invalid_format() -> None:
    with pytest.raises(ValueError, match="Unsupported input format"):
        AutoParser(format=cast(Any, "xml"))


def test_auto_parser_rejects_non_utf8_non_docx_bytes() -> None:
    with pytest.raises(ValueError, match="non-DOCX binary input"):
        AutoParser().parse(b"\xff\xfe\x00")


def test_metadata_overrides_parser_metadata_and_source_path_is_independent() -> None:
    document = AutoParser().parse(
        "---\ntitle: Front matter\nauthor: Ada\n---\n\nBody",
        metadata_overrides={"author": "Grace", "path": "semantic-value"},
        source_path="archive/guide.md",
    )
    assert document.metadata["author"] == "Grace"
    assert document.metadata["path"] == "semantic-value"
    assert document.source_path == "archive/guide.md"

    chunks = SiblingSplitter(ApproxByteTokenizer()).split(document)
    assert chunks[0].document_path == "archive/guide.md"


def test_markdown_parser_disables_setext_headings_by_default() -> None:
    document = MarkdownParser().parse("Title\n=====\n\nBody")
    assert not document.root.children
    assert "Title" in document.root.blocks[0].text


def test_markdown_parser_can_enable_setext_headings() -> None:
    document = MarkdownParser(disable_lheading=False).parse("Title\n=====\n\nBody")
    assert document.root.children[0].title == "Title"


def test_block_config_objects_are_kind_safe() -> None:
    markdown_table = MarkdownTableConfig(isolated=True)
    html_table = HTMLTableConfig(max_tokens=100)
    code = BlockConfig(BlockKind.CODE_FENCE, split=False)
    custom = CustomBlockConfig("callout", isolated=True)
    assert markdown_table.kind is BlockKind.TABLE
    assert html_table.kind is BlockKind.HTML_TABLE
    assert code.kind is BlockKind.CODE_FENCE
    assert custom.kind == "callout"

    with pytest.raises(ValueError, match="table kinds require"):
        BlockConfig(BlockKind.TABLE)
    with pytest.raises(ValueError, match="positive integer"):
        MarkdownTableConfig(max_tokens=0)


def test_splitter_rejects_dict_and_duplicate_block_configs() -> None:
    tokenizer = ApproxByteTokenizer()
    with pytest.raises(TypeError, match="sequence"):
        SiblingSplitter(tokenizer, block_options={})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duplicate"):
        SiblingSplitter(
            tokenizer,
            block_options=[MarkdownTableConfig(), MarkdownTableConfig()],
        )


def test_explicit_parser_splitter_pipeline() -> None:
    document = MarkdownParser().parse("# Guide\n\nA paragraph")
    chunks = SiblingSplitter(
        ApproxByteTokenizer(),
        max_tokens=100,
        block_options=[BlockConfig(BlockKind.CODE_FENCE, split=False)],
    ).split(document)
    assert chunks[0].body == "# Guide\n\nA paragraph"


def test_default_and_exact_splitters_expose_different_counting_modes() -> None:
    document = MarkdownParser().parse("# Guide\n\nA paragraph")
    incremental = SiblingSplitter(ApproxByteTokenizer()).split(document)[0]
    exact = ExactSiblingSplitter(ApproxByteTokenizer()).split(document)[0]
    assert incremental.token_count == exact.token_count
    assert exact.estimated_token_count == exact.token_count

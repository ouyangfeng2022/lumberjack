from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import lumberjack
from lumberjack import Document, Lumberjack
from lumberjack.block import (
    BlockConfig,
    BlockKind,
    CustomBlockConfig,
    HTMLTableConfig,
    MarkdownTableConfig,
)
from lumberjack.models import (
    DocTree,
    DocumentBlock,
    ExtractionResult,
    InputFormat,
    SectionNode,
    SourceLocation,
)
from lumberjack.parser import AutoParser, DocTreeBuilder, MarkdownParser
from lumberjack.splitter import ExactSiblingSplitter, RecordSplitter, SiblingSplitter
from lumberjack.tokenizer import ApproxByteTokenizer
from tests.helpers import FIXTURES_DIR, saw

FIXTURES = FIXTURES_DIR
MARKDOWN_PATH = FIXTURES / "markdown" / "sample.md"
DOCX_PATH = FIXTURES / "docx" / "sample.docx"


def test_package_exports_lumberjack_and_document_at_top_level() -> None:
    assert lumberjack.__all__ == ["Document", "Lumberjack"]


def test_lumberjack_saw_splits_markdown() -> None:
    result = Lumberjack(max_tokens=100).saw("# Guide\n\nHello world")
    assert result.document.title == "Guide"
    assert result.chunks
    assert "Hello world" in result.chunks[0].body


def test_lumberjack_trace_exposes_pipeline_stages_and_source_locations() -> None:
    trace = Lumberjack(max_tokens=100).trace("# Guide\n\nHello world")

    assert trace.input.source == "# Guide\n\nHello world"
    assert trace.extraction is None
    assert trace.document.title == "Guide"
    assert trace.drafts
    assert trace.chunks[0].source_locations == (
        SourceLocation(line_start=3, line_end=3),
    )
    assert json.loads(json.dumps(trace.to_dict()))["chunks"][0]["source_locations"] == [
        {
            "source": None,
            "byte_start": None,
            "byte_end": None,
            "line_start": 3,
            "line_end": 3,
            "page_start": None,
            "page_end": None,
            "sheet": None,
            "row_start": None,
            "row_end": None,
            "column_start": None,
            "column_end": None,
            "json_path": None,
            "element_id": None,
            "bounding_box": None,
        }
    ]


def test_lumberjack_trace_preserves_parser_defined_source_locations() -> None:
    location = SourceLocation(page_start=2, page_end=2, element_id="p-17")

    class LocatedParser:
        block_kinds = frozenset({"paragraph"})

        def parse(self, document: Document) -> DocTree:
            del document
            root = SectionNode(level=0, title="")
            root.add_block(
                DocumentBlock(
                    kind="paragraph",
                    text="Extracted content",
                    source_locations=(location,),
                )
            )
            return DocTree(title="Located", source="", root=root)

        def extract(self, document: Document) -> ExtractionResult:
            del document
            return ExtractionResult(
                parser_name="located",
                parser_version="test",
                raw_output="raw extraction",
                normalized_output="Extracted content",
                locations=(location,),
            )

    trace = Lumberjack(parser=LocatedParser(), max_tokens=100).trace("input")

    assert trace.chunks[0].source_locations == (location,)
    assert trace.extraction is not None
    assert trace.extraction.parser_name == "located"


def test_doc_tree_builder_supports_flat_records_without_synthetic_headings() -> None:
    location = SourceLocation(sheet="Sales", row_start=2, row_end=2)
    document = (
        DocTreeBuilder(title="Rows", topology="records", block_kinds=["tabular_row"])
        .add_record("Ada,42", kind="tabular_row", locations=[location])
        .build()
    )

    assert document.root.children == []
    assert document.topology == "records"
    assert document.root.blocks[0].kind == "tabular_row"
    assert document.root.blocks[0].source_locations == (location,)


def test_doc_tree_builder_adds_field_values_without_synthetic_headings() -> None:
    document = (
        DocTreeBuilder(block_kinds=["field_value"])
        .add_field_value(
            "status",
            "active",
            locations=[SourceLocation(json_path="$.status")],
        )
        .build()
    )

    assert document.root.children == []
    assert document.root.blocks[0].text == "status: active"
    assert document.root.blocks[0].attrs == {"field": "status", "value": "active"}


def test_doc_tree_builder_rejects_records_without_record_provenance() -> None:
    builder = DocTreeBuilder(topology="records", block_kinds=["record"])

    with pytest.raises(ValueError, match="record locations must include"):
        builder.add_record("missing provenance", locations=[SourceLocation()])


def test_record_splitter_packs_rows_without_heading_context() -> None:
    document = (
        DocTreeBuilder(title="Rows", topology="records", block_kinds=["tabular_row"])
        .add_record(
            "Ada,42",
            kind="tabular_row",
            locations=[SourceLocation(row_start=2, row_end=2)],
        )
        .add_record(
            "Grace,37",
            kind="tabular_row",
            locations=[SourceLocation(row_start=3, row_end=3)],
        )
        .build()
    )

    chunks = saw(RecordSplitter(ApproxByteTokenizer(), max_tokens=100), document)

    assert len(chunks) == 1
    assert chunks[0].ancestor_headings == ()
    assert chunks[0].own_heading is None
    assert chunks[0].protected is False
    assert [location.row_start for location in chunks[0].source_locations] == [2, 3]


def test_hierarchical_splitters_reject_record_documents() -> None:
    document = (
        DocTreeBuilder(title="Rows", topology="records", block_kinds=["record"])
        .add_record("one", locations=[SourceLocation(json_path="$.items[0]")])
        .build()
    )

    with pytest.raises(ValueError, match="supports only hierarchical topology"):
        SiblingSplitter(ApproxByteTokenizer()).split(document)


def test_record_splitter_reports_an_oversized_atomic_record_as_protected() -> None:
    document = (
        DocTreeBuilder(title="Rows", topology="records", block_kinds=["record"])
        .add_record(
            "x" * 100,
            locations=[SourceLocation(json_path="$.items[0]")],
        )
        .build()
    )

    chunk = saw(RecordSplitter(ApproxByteTokenizer(), max_tokens=10), document)[0]

    assert chunk.protected is True
    assert chunk.token_count > 10


def test_lumberjack_auto_detects_path_and_sets_document_path() -> None:
    result = Lumberjack(max_tokens=500).saw(MARKDOWN_PATH)
    assert result.chunks
    assert all(chunk.document_path == str(MARKDOWN_PATH) for chunk in result.chunks)


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


def test_lumberjack_accepts_docx_bytes() -> None:
    result = Lumberjack(max_tokens=500).saw(DOCX_PATH.read_bytes())
    assert result.chunks
    assert result.document.title == "Test Document"
    assert any(chunk.own_heading == (1, "Introduction") for chunk in result.chunks)


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
    document = AutoParser().parse(
        '<meta name="author" content="Ada"><h1>Title</h1>',
        format="html",
        metadata_overrides={"author": "Grace"},
    )
    assert document.metadata["author"] == "Grace"


def test_auto_parser_falls_back_to_markdown() -> None:
    document = AutoParser().parse("# Markdown\n\nBody")
    assert document.title == "Markdown"
    assert document.root.children[0].title == "Markdown"


def test_auto_parser_forced_format_skips_inference() -> None:
    document = AutoParser().parse("<h1>HTML</h1>", format="markdown")
    assert document.root.blocks[0].kind == BlockKind.HTML_BLOCK


def test_auto_parser_rejects_invalid_format() -> None:
    with pytest.raises(ValueError, match="Unsupported input format"):
        AutoParser().parse(Document("body", format=cast(InputFormat, "xml")))


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

    chunks = saw(SiblingSplitter(ApproxByteTokenizer()), document)
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
    splitter = SiblingSplitter(
        ApproxByteTokenizer(),
        max_tokens=100,
        block_options=[BlockConfig(BlockKind.CODE_FENCE, split=False)],
    )
    chunks = saw(splitter, document)
    assert chunks[0].own_heading == (1, "Guide")
    assert chunks[0].body == "A paragraph"


def test_default_and_exact_splitters_expose_different_counting_modes() -> None:
    document = MarkdownParser().parse("# Guide\n\nA paragraph")
    incremental = saw(SiblingSplitter(ApproxByteTokenizer()), document)[0]
    exact = saw(ExactSiblingSplitter(ApproxByteTokenizer()), document)[0]
    assert incremental.token_count == exact.token_count
    assert exact.estimated_token_count == exact.token_count

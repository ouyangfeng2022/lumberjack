"""Native LlamaIndex pipeline components (node parser + reader)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from lumberjack.block import BlockConfig, BlockKind, MarkdownTableConfig
from lumberjack.models import InputFormat

pytest.importorskip("llama_index.core")

from llama_index.core import Document as LlamaDocument
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser.interface import NodeParser
from llama_index.core.schema import BaseNode, NodeRelationship, TextNode

from lumberjack.integrations.llama_index_pipeline import (
    LumberjackNodeParser,
    LumberjackReader,
    lumberjack_node_id,
    render_doc_tree,
)

MARKDOWN = "# Guide\n\nAlpha intro.\n\n## Setup\n\nInstall first."


class _StubFallback(NodeParser):
    """Dependency-free node parser marking that fallback routing happened."""

    def _parse_nodes(
        self,
        nodes: Sequence[BaseNode],
        show_progress: bool = False,  # noqa: ARG002 - ABC signature
        **kwargs: Any,  # noqa: ARG002 - ABC signature
    ) -> list[BaseNode]:
        return [TextNode(text=f"fallback:{node.get_content()[:8]}") for node in nodes]


def _document(
    text: str = MARKDOWN, id_: str | None = None, **metadata: Any
) -> LlamaDocument:
    fields: dict[str, Any] = {
        "text": text,
        "metadata": {"file_path": "docs/x.md", **metadata},
    }
    if id_ is not None:
        fields["id_"] = id_
    return LlamaDocument(**fields)


def _texts(nodes: Sequence[BaseNode]) -> list[str]:
    return [node.get_content() for node in nodes]


def _related(node: BaseNode, relationship: NodeRelationship) -> str:
    related = node.relationships[relationship]
    assert not isinstance(related, list)
    return related.node_id


def test_node_parser_emits_structure_aware_nodes() -> None:
    parser = LumberjackNodeParser(max_tokens=64)
    source = _document()
    nodes = parser.get_nodes_from_documents([source])

    assert _texts(nodes) == ["Alpha intro.", "Install first."]
    assert [node.id_ for node in nodes] == [
        lumberjack_node_id(0, source),
        lumberjack_node_id(1, source),
    ]
    first, second = nodes
    assert first.metadata["own_heading"] == [1, "Guide"]
    assert second.metadata["own_heading"] == [2, "Setup"]
    assert first.metadata["start_line"] == 3
    assert second.metadata["end_line"] == 7

    assert _related(first, NodeRelationship.SOURCE) == source.id_
    assert _related(second, NodeRelationship.PREVIOUS) == first.id_
    assert _related(first, NodeRelationship.NEXT) == second.id_


def test_node_parser_excludes_chunk_metadata_from_embed_and_llm() -> None:
    nodes = LumberjackNodeParser(max_tokens=64).get_nodes_from_documents([_document()])
    chunk_keys = {"own_heading", "ancestor_headings", "token_count", "start_line"}
    for node in nodes:
        assert chunk_keys <= set(node.excluded_embed_metadata_keys)
        assert chunk_keys <= set(node.excluded_llm_metadata_keys)


def test_node_parser_heading_context_prefixes_breadcrumbs() -> None:
    nodes = LumberjackNodeParser(max_tokens=64, heading_context=True)
    parsed = nodes.get_nodes_from_documents([_document()])
    assert _texts(parsed) == [
        "# Guide\n\nAlpha intro.",
        "# Guide\n\n## Setup\n\nInstall first.",
    ]


def test_node_parser_runs_inside_ingestion_pipeline() -> None:
    pipeline = IngestionPipeline(transformations=[LumberjackNodeParser(max_tokens=64)])
    nodes = pipeline.run(documents=[_document()])
    assert _texts(nodes) == ["Alpha intro.", "Install first."]
    assert nodes[0].metadata["document_title"] == "Guide"


def test_node_parser_feeds_vector_store_index() -> None:
    from llama_index.core import VectorStoreIndex

    nodes = LumberjackNodeParser(max_tokens=64).get_nodes_from_documents([_document()])
    built = VectorStoreIndex(nodes=nodes, embed_model=MockEmbedding(embed_dim=8))
    hits = built.as_retriever(similarity_top_k=1).retrieve("install")
    assert hits[0].text == "Install first."


def test_node_parser_fallback_routes_by_file_suffix() -> None:
    parser = LumberjackNodeParser(
        max_tokens=64,
        fallback=_StubFallback(),
        fallback_suffixes=(".pdf",),
    )
    pdf = LlamaDocument(
        text="Flat PDF prose without structure.",
        metadata={"file_path": "a/report.PDF"},
    )
    markdown = _document()
    routed = parser.get_nodes_from_documents([pdf, markdown])

    assert _texts(routed) == ["fallback:Flat PDF", "Alpha intro.", "Install first."]


def test_node_parser_rejects_unknown_splitter_eagerly() -> None:
    with pytest.raises(ValueError, match="Unsupported splitter"):
        LumberjackNodeParser(splitter="nonexistent")


def test_node_parser_serialization_round_trip() -> None:
    parser = LumberjackNodeParser(
        max_tokens=128,
        splitter="subtree",
        tokenizer="approx",
        merge_below_ratio=0.25,
        block_options=[
            BlockConfig(BlockKind.CODE_FENCE, split=False),
            MarkdownTableConfig(repeat_header=False),
        ],
    )
    payload = parser.to_dict()
    import json

    json.dumps(payload)  # payload must stay JSON-safe

    restored = LumberjackNodeParser.from_dict(payload)
    assert restored.max_tokens == 128
    assert restored.splitter == "subtree"
    assert restored.merge_below_ratio == 0.25
    assert restored.block_options == [
        {"kind": "code_fence", "isolated": False, "split": False, "max_tokens": None},
        {
            "kind": "table",
            "isolated": False,
            "split": True,
            "max_tokens": None,
            "repeat_header": False,
        },
    ]
    nodes = restored.get_nodes_from_documents([_document()])
    # 128 tokens fit the whole document, so the restored pipeline emits one chunk.
    assert _texts(nodes) == ["Alpha intro.\n\n## Setup\n\nInstall first."]


def test_node_parser_ids_are_deterministic_across_runs() -> None:
    parser = LumberjackNodeParser(max_tokens=64)
    first = parser.get_nodes_from_documents([_document(id_="stable-source")])
    second = parser.get_nodes_from_documents(
        [_document(text=MARKDOWN, id_="stable-source")]
    )
    assert [node.id_ for node in first] == [node.id_ for node in second]


def _docx_fixture() -> Path:
    fixture = Path(__file__).parents[1] / "fixtures" / "docx" / "sample.docx"
    if not fixture.exists():  # pragma: no cover - docx extra not installed
        pytest.skip("DOCX fixture requires the docx extra")
    return fixture


def test_reader_renders_docx_to_canonical_markdown() -> None:
    documents = LumberjackReader().load_data(_docx_fixture())
    assert len(documents) == 1
    document = documents[0]
    assert "# Introduction" in document.text
    assert "## Background" in document.text
    assert "|" in document.text  # tables survive as Markdown tables
    assert document.metadata["file_name"] == "sample.docx"
    assert document.metadata["file_path"].endswith("sample.docx")


def test_reader_preserves_markdown_structure_and_front_matter(tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    source.write_text(
        "---\ntitle: Handbook\nauthor: Ada\n---\n\n# Guide\n\nBody text.\n",
        encoding="utf-8",
    )
    documents = LumberjackReader().load_data(source)
    document = documents[0]
    assert "# Guide" in document.text
    assert "Body text." in document.text
    assert document.metadata["title"] == "Handbook"
    assert document.metadata["author"] == "Ada"

    # The canonical rendering round-trips through the node parser.
    nodes = LumberjackNodeParser(max_tokens=64).get_nodes_from_documents([document])
    assert "Body text." in _texts(nodes)


def test_reader_rejects_unsupported_explicit_format() -> None:
    bogus_format = cast("InputFormat", "pdf")
    with pytest.raises(ValueError, match="Unsupported input format"):
        LumberjackReader(input_format=bogus_format)


def test_reader_auto_detects_html(tmp_path: Path) -> None:
    source = tmp_path / "page.html"
    source.write_text(
        "<html><body><h1>Guide</h1><p>HTML body.</p></body></html>",
        encoding="utf-8",
    )
    documents = LumberjackReader().load_data(source)
    assert "# Guide" in documents[0].text
    assert "HTML body." in documents[0].text


def test_render_doc_tree_skips_empty_sections() -> None:
    documents = LumberjackReader().load_data(_docx_fixture())
    tree_text = documents[0].text
    rendered = render_doc_tree  # public helper stays importable
    assert callable(rendered)
    assert "\n\n\n" not in tree_text

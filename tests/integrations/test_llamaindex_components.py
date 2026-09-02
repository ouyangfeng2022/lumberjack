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


@pytest.fixture(name="_local_tiktoken")
def local_tiktoken(monkeypatch: pytest.MonkeyPatch) -> None:
    class Encoding:
        def encode(self, text: str) -> list[int]:
            return list(text.encode("utf-8"))

    import tiktoken

    monkeypatch.setattr(tiktoken, "encoding_for_model", lambda _model: Encoding())


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


def test_node_parser_feeds_vector_store_index(_local_tiktoken) -> None:
    from llama_index.core import VectorStoreIndex

    nodes = LumberjackNodeParser(max_tokens=64).get_nodes_from_documents([_document()])
    built = VectorStoreIndex(
        nodes=nodes, embed_model=MockEmbedding(embed_dim=8), transformations=[]
    )
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


HIERARCHICAL_MD = (
    "# Guide\n\nIntro paragraph.\n\n"
    "## Setup\n\nInstall step one.\n\nInstall step two.\n\n"
    "## Usage\n\nRun it now.\n\nMore usage detail.\n"
)


def _hierarchical_nodes(
    parser: LumberjackNodeParser | None = None, id_: str | None = None
):
    parser = parser or LumberjackNodeParser(max_tokens=40, emit_parents=True)
    fields: dict[str, Any] = {
        "text": HIERARCHICAL_MD,
        "metadata": {"file_path": "x.md"},
    }
    if id_ is not None:
        fields["id_"] = id_
    return parser.get_nodes_from_documents([LlamaDocument(**fields)])


def test_emit_parents_disabled_by_default() -> None:
    nodes = _hierarchical_nodes(LumberjackNodeParser(max_tokens=40))
    assert all(node.metadata["chunk_type"] != "section" for node in nodes)
    assert all(NodeRelationship.PARENT not in node.relationships for node in nodes)


def test_emit_parents_groups_real_sections() -> None:
    nodes = _hierarchical_nodes()
    parents = [n for n in nodes if n.metadata["chunk_type"] == "section"]
    leaves = [n for n in nodes if n.metadata["chunk_type"] != "section"]

    assert [parent.metadata["own_heading"][1] for parent in parents] == [
        "Guide",
        "Setup",
        "Usage",
    ]
    # The Setup section has two leaves; every section still gets one parent.
    assert len(leaves) == 3
    assert len(parents) == 3

    _guide, setup, usage = parents
    assert setup.metadata["ancestor_headings"] == [[1, "Guide"]]
    assert setup.metadata["section_level"] == 2
    assert setup.metadata["token_count"] > 0
    assert setup.metadata["start_line"] is not None
    assert setup.text == "# Guide\n\n## Setup\n\nInstall step one.\n\nInstall step two."

    # Leaves point to their section parent; parents list their leaves.
    leaf_by_id = {node.id_: node for node in leaves}
    for child in setup.child_nodes:
        assert (
            leaf_by_id[child.node_id].relationships[NodeRelationship.PARENT].node_id
            == setup.id_
        )
    assert setup.id_ != usage.id_


def test_emit_parents_ids_are_deterministic() -> None:
    first = _hierarchical_nodes(id_="stable-source")
    second = _hierarchical_nodes(id_="stable-source")
    first_ids = {n.id_ for n in first}
    second_ids = {n.id_ for n in second}
    assert first_ids == second_ids
    assert any(n.metadata["chunk_type"] == "section" for n in first)


def test_emit_parents_metadata_is_json_safe() -> None:
    import json

    nodes = _hierarchical_nodes()
    for node in nodes:
        json.dumps(node.metadata)  # must not raise


def test_emit_parents_serialization_round_trip() -> None:
    parser = LumberjackNodeParser(max_tokens=40, emit_parents=True)
    restored = LumberjackNodeParser.from_dict(parser.to_dict())
    assert restored.emit_parents is True
    nodes = restored.get_nodes_from_documents(
        [LlamaDocument(text=HIERARCHICAL_MD, metadata={"file_path": "x.md"})]
    )
    assert sum(n.metadata["chunk_type"] == "section" for n in nodes) == 3


def test_auto_merging_retriever_merges_to_section_parent(_local_tiktoken) -> None:
    from llama_index.core import VectorStoreIndex
    from llama_index.core.retrievers import AutoMergingRetriever
    from llama_index.core.storage.storage_context import StorageContext

    section = "\n".join(
        f"Detail paragraph {i} with enough words to become its own chunk."
        for i in range(12)
    )
    text = f"# Guide\n\nIntro.\n\n## Big\n\n{section}\n\n## Other\n\nOne line.\n"
    nodes = LumberjackNodeParser(
        max_tokens=60, emit_parents=True
    ).get_nodes_from_documents(
        [LlamaDocument(text=text, metadata={"file_path": "x.md"})]
    )
    leaves = [n for n in nodes if n.metadata["chunk_type"] != "section"]
    big_parent = next(n for n in nodes if n.metadata["own_heading"] == [2, "Big"])
    assert len(big_parent.child_nodes or []) == 6

    storage = StorageContext.from_defaults()
    index = VectorStoreIndex(
        nodes=nodes,
        storage_context=storage,
        embed_model=MockEmbedding(embed_dim=8),
        transformations=[],
    )
    retriever = AutoMergingRetriever(
        vector_retriever=cast(Any, index.as_retriever(similarity_top_k=len(leaves))),
        storage_context=storage,
    )
    texts = [hit.node.get_content() for hit in retriever.retrieve("detail")]
    # All six Big leaves are hit, so they merge into the real section parent.
    merged = [
        t for t in texts if t.startswith("# Guide\n\n## Big\n\nDetail paragraph 0")
    ]
    assert len(merged) == 1

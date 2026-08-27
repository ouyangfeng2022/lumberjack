"""Native LlamaIndex pipeline components backed by Lumberjack.

Unlike the conversion helpers in :mod:`lumberjack.integrations.llama_index`,
the components here plug Lumberjack into LlamaIndex's own ingestion flow:

- :class:`LumberjackNodeParser` replaces ``SentenceSplitter`` /
  ``MarkdownNodeParser`` inside ``IngestionPipeline.transformations`` or any
  ``NodeParser`` slot.
- :class:`LumberjackReader` normalizes Markdown/HTML/DOCX files into
  canonical Markdown ``Document`` objects for ``SimpleDirectoryReader``-style
  loading, so a single reader plus node parser handles every Lumberjack
  format.

Importing this module requires ``llama-index-core`` (``pip install
lumberjack-py[llama-index]``).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from llama_index.core.node_parser.interface import NodeParser
from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import (
    BaseNode,
    MetadataMode,
    NodeRelationship,
    TextNode,
)
from llama_index.core.schema import (
    Document as LlamaDocument,
)
from pydantic import ConfigDict, Field, PrivateAttr, model_validator

from lumberjack.models import (
    DocTree,
    InputFormat,
    SectionNode,
)
from lumberjack.models import (
    Document as LumberjackSource,
)
from lumberjack.parser import AutoParser

from ._components import (
    PipelineSettings,
    block_option_to_dict,
    block_options_from_values,
    chunk_content,
)
from ._metadata import chunk_metadata

if TYPE_CHECKING:
    IdFunc = "Callable[[int, BaseNode], str]"

__all__ = [
    "LumberjackNodeParser",
    "LumberjackReader",
    "lumberjack_node_id",
    "render_doc_tree",
]


def lumberjack_node_id(i: int, doc: BaseNode) -> str:
    """Deterministic chunk-node id, stable across re-runs of one source node."""
    return f"{doc.node_id}:{i}"


def render_doc_tree(tree: DocTree) -> str:
    """Render a parsed tree back to canonical Markdown text.

    Section headings become ATX headings and every block contributes its
    canonical rendered text, so binary formats such as DOCX round-trip into
    structure-aware downstream splitting.
    """
    parts: list[str] = []

    def visit(section: SectionNode) -> None:
        if section.level > 0 and section.title.strip():
            parts.append(f"{'#' * section.level} {section.title.strip()}")
        parts.extend(
            block.text.strip()
            for block in section.blocks
            if block.text and block.text.strip()
        )
        for child in section.children:
            visit(child)

    visit(tree.root)
    return "\n\n".join(parts)


class LumberjackNodeParser(NodeParser):
    """LlamaIndex node parser backed by Lumberjack structure-aware splitting.

    Drop it into ``IngestionPipeline.transformations`` (or anywhere a
    ``NodeParser`` is accepted) instead of ``SentenceSplitter``. Chunks keep
    Lumberjack provenance metadata (heading path, token counts, source line
    ranges), carry deterministic node ids for stable re-indexing, and are
    linked to their source node through ``SOURCE``/``PREVIOUS``/``NEXT``
    relationships.

    Args:
        max_tokens: Maximum tokens per chunk; also forwarded as the base
            ``chunk_size`` so generic LlamaIndex tooling sees a sane value.
        splitter: Lumberjack splitter name (``section``, ``subtree``,
            ``sibling``, or their ``exact-`` variants).
        tokenizer: Lumberjack token counter (``approx``, ``tiktoken``,
            ``transformers``).
        heading_context: Prefix each node text with its rendered heading
            breadcrumb so embeddings see the section context. Defaults to
            ``Chunk.body`` only.
        input_format: Format hint for the text inside nodes (``auto``,
            ``markdown``, ``html``).
        block_options: Typed ``lumberjack.block`` options (or their
            serialized dict form) for per-block splitting behavior.
        fallback_suffixes: File suffixes (e.g. ``(".pdf",)``) routed to
            ``fallback`` instead of Lumberjack, for sources whose structure
            was already destroyed upstream.
        fallback: Node parser used for the suffix-routed sources. Not
            serialized by ``to_dict``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    max_tokens: int = 1024
    splitter: str = "section"
    tokenizer: str = "approx"
    ideal_max_tokens_ratio: float = 0.8
    merge_below_ratio: float = 0.125
    skip_empty_sections: bool = True
    heading_sensitive: bool = True
    max_heading_level: int | None = None
    heading_context: bool = False
    input_format: InputFormat = "auto"
    block_options: list[Any] | None = None
    fallback_suffixes: tuple[str, ...] = ()
    fallback: NodeParser | None = Field(default=None, exclude=True)
    id_func: Any = Field(default=lumberjack_node_id)

    _pipeline: Any = PrivateAttr()

    @classmethod
    def class_name(cls) -> str:
        return "LumberjackNodeParser"

    @model_validator(mode="before")
    @classmethod
    def _normalize_block_options(cls, values: Any) -> Any:
        if not isinstance(values, Mapping):
            return values
        raw = values.get("block_options")
        if raw is None:
            return values
        values = dict(values)
        values["block_options"] = [
            option if isinstance(option, Mapping) else block_option_to_dict(option)
            for option in raw
        ]
        return values

    def model_post_init(self, __context: Any) -> None:
        settings = PipelineSettings(
            max_tokens=self.max_tokens,
            splitter=self.splitter,
            tokenizer=self.tokenizer,
            ideal_max_tokens_ratio=self.ideal_max_tokens_ratio,
            merge_below_ratio=self.merge_below_ratio,
            skip_empty_sections=self.skip_empty_sections,
            heading_sensitive=self.heading_sensitive,
            max_heading_level=self.max_heading_level,
            input_format=self.input_format,
            block_options=block_options_from_values(self.block_options),
        )
        self._pipeline = settings.build()

    def _route_to_fallback(self, node: BaseNode) -> bool:
        if self.fallback is None or not self.fallback_suffixes:
            return False
        file_path = node.metadata.get("file_path")
        if not isinstance(file_path, str):
            return False
        return file_path.lower().endswith(
            tuple(suffix.lower() for suffix in self.fallback_suffixes)
        )

    def _parse_nodes(
        self,
        nodes: Sequence[BaseNode],
        show_progress: bool = False,
        **kwargs: Any,
    ) -> list[BaseNode]:
        parsed: list[BaseNode] = []
        for node in nodes:
            fallback = self.fallback
            if fallback is not None and self._route_to_fallback(node):
                parsed.extend(
                    fallback.get_nodes_from_documents(
                        [node],  # type: ignore  # BaseNode works at runtime
                        show_progress=show_progress,
                        **kwargs,
                    )
                )
                continue
            source_path = node.metadata.get("file_path")
            result = self._pipeline.run(
                LumberjackSource(
                    source=node.get_content(metadata_mode=MetadataMode.NONE),
                    format=self.input_format,
                    source_path=source_path if isinstance(source_path, str) else None,
                )
            )
            parsed.extend(self._nodes_for_chunks(node, result.chunks))
        return parsed

    def _nodes_for_chunks(
        self, source: BaseNode, chunks: Iterable[Any]
    ) -> list[TextNode]:
        nodes: list[TextNode] = []
        excluded_embed = set(source.excluded_embed_metadata_keys)
        excluded_llm = set(source.excluded_llm_metadata_keys)
        for i, chunk in enumerate(chunks):
            metadata = chunk_metadata(chunk)
            chunk_keys = set(metadata)
            nodes.append(
                TextNode(
                    id_=self.id_func(i, source),
                    text=chunk_content(chunk, heading_context=self.heading_context),
                    metadata=metadata,
                    excluded_embed_metadata_keys=sorted(excluded_embed | chunk_keys),
                    excluded_llm_metadata_keys=sorted(excluded_llm | chunk_keys),
                    embedding=source.embedding,
                    relationships={
                        NodeRelationship.SOURCE: source.as_related_node_info()
                    },
                )
            )
        return nodes

    def to_dict(self, **kwargs: Any) -> dict:
        data = super().to_dict(**kwargs)
        if self.id_func is lumberjack_node_id:
            data.pop("id_func", None)
        return data


_SUFFIX_FORMATS: dict[str, InputFormat] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".mdx": "markdown",
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".docx": "docx",
}

_READER_FORMATS = ("markdown", "html", "docx")


def _json_safe_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in metadata.items():
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            continue
        result[str(key)] = value
    return result


class LumberjackReader(BaseReader):
    """Read Markdown/HTML/DOCX files into canonical Markdown documents.

    Every supported file is parsed by Lumberjack and re-rendered as
    canonical Markdown, preserving the heading tree, tables, lists, and code
    blocks. Pair with :class:`LumberjackNodeParser` downstream so all formats
    flow through one structure-aware splitting path. Parsed front matter and
    file provenance are attached as document metadata.

    Args:
        input_format: Force ``markdown``, ``html``, or ``docx``; ``auto``
            detects from the file suffix.
    """

    def __init__(self, *, input_format: InputFormat = "auto") -> None:
        if input_format != "auto" and input_format not in _READER_FORMATS:
            raise ValueError(
                f"Unsupported input format: {input_format}. "
                f"Supported: {', '.join(('auto', *_READER_FORMATS))}"
            )
        self.input_format: InputFormat = input_format
        self._parser = AutoParser()

    def _resolve_format(self, path: Path) -> InputFormat:
        if self.input_format != "auto":
            return self.input_format
        suffix_format = _SUFFIX_FORMATS.get(path.suffix.lower())
        return suffix_format if suffix_format is not None else "markdown"

    def lazy_load_data(
        self, input_file: Path | str, extra_info: dict | None = None
    ) -> Iterator[LlamaDocument]:
        path = Path(input_file)
        tree = self._parser.parse(
            path.read_bytes(),
            format=self._resolve_format(path),
            source_path=path,
        )
        metadata = {
            "file_path": str(path.resolve()),
            "file_name": path.name,
            **_json_safe_metadata(tree.metadata),
            **(extra_info or {}),
        }
        yield LlamaDocument(
            text=render_doc_tree(tree),
            metadata=metadata,
        )

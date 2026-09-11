"""Native LangChain splitting components backed by Lumberjack.

Unlike the conversion helpers in :mod:`lumberjack.integrations.langchain`,
the components here plug Lumberjack into LangChain's own text-processing
interfaces:

- :class:`LumberjackTextSplitter` is a drop-in ``TextSplitter`` subclass
  usable anywhere ``RecursiveCharacterTextSplitter`` is accepted, including
  the free ``create_documents`` / ``split_documents`` metadata plumbing.
- :class:`LumberjackDocumentTransformer` is a ``BaseDocumentTransformer``
  for LangChain's indexing API (``langchain.indexing``).

Importing this module requires ``langchain-core`` and
``langchain-text-splitters`` (``pip install lumberjack-py[langchain]``).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from langchain_core.documents import Document as LangchainDocument
from langchain_core.documents.transformers import BaseDocumentTransformer
from langchain_text_splitters import TextSplitter

from lumberjack.models import Chunk, InputFormat
from lumberjack.models import Document as LumberjackSource

from ._components import PipelineSettings, chunk_content
from ._metadata import chunk_metadata

__all__ = ["LumberjackDocumentTransformer", "LumberjackTextSplitter"]


class _LumberjackSplittingMixin:
    """Shared construction and splitting for the LangChain components."""

    _settings: PipelineSettings
    _pipeline: Any
    _heading_context: bool

    def _init_settings(self, **values: Any) -> None:
        self._settings = PipelineSettings.from_values(**values)
        self._pipeline = self._settings.build()

    def split_chunks(self, text: str, *, source_path: str | None = None) -> list[Chunk]:
        """Run the Lumberjack pipeline over one text and return its chunks."""
        return self._pipeline.run(
            LumberjackSource(
                source=text,
                format=self._settings.input_format,
                source_path=source_path,
            )
        ).chunks

    def chunk_documents(
        self,
        documents: Iterable[LangchainDocument],
    ) -> list[LangchainDocument]:
        """Split LangChain documents, merging chunk provenance into metadata."""
        split: list[LangchainDocument] = []
        for document in documents:
            source_path = document.metadata.get("file_path")
            chunks = self.split_chunks(
                document.page_content,
                source_path=source_path if isinstance(source_path, str) else None,
            )
            prefix = document.id if document.id else ""
            for chunk in chunks:
                split.append(
                    LangchainDocument(
                        id=f"{prefix}:{chunk.chunk_id}" if prefix else chunk.chunk_id,
                        page_content=chunk_content(
                            chunk, heading_context=self._heading_context
                        ),
                        metadata={**document.metadata, **chunk_metadata(chunk)},
                    )
                )
        return split


class LumberjackTextSplitter(_LumberjackSplittingMixin, TextSplitter):
    """LangChain ``TextSplitter`` backed by Lumberjack structure-aware splitting.

    A drop-in replacement for ``RecursiveCharacterTextSplitter``: ``split_text``
    returns structure-aware chunk texts, while ``create_documents`` /
    ``split_documents`` keep each input document's metadata and additionally
    attach Lumberjack provenance (heading path, token counts, source line
    ranges) to every produced document.

    Args:
        max_tokens: Maximum tokens per chunk; also forwarded as the base
            ``chunk_size`` so generic LangChain tooling sees a sane value.
        splitter: Lumberjack splitter name (``section``, ``subtree``,
            ``sibling``, or their ``exact-`` variants).
        tokenizer: Lumberjack token counter (``approx``, ``tiktoken``,
            ``transformers``).
        heading_context: Prefix each split text with its rendered heading
            breadcrumb. Defaults to ``Chunk.body`` only.
        input_format: Format hint for the texts (``auto``, ``markdown``,
            ``html``).
        block_options: Typed ``lumberjack.block`` options for per-block
            splitting behavior.
        kwargs: Forwarded to the ``TextSplitter`` base class.
    """

    def __init__(
        self,
        *,
        max_tokens: int = 1024,
        splitter: str = "section",
        tokenizer: str = "approx",
        ideal_max_tokens_ratio: float = 0.8,
        merge_below_ratio: float = 0.125,
        skip_empty_sections: bool = True,
        heading_sensitive: bool = True,
        max_heading_level: int | None = None,
        heading_context: bool = False,
        input_format: InputFormat = "auto",
        block_options: Sequence[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("chunk_overlap", 0)
        super().__init__(chunk_size=max_tokens, **kwargs)
        self._heading_context = heading_context
        self._init_settings(
            max_tokens=max_tokens,
            splitter=splitter,
            tokenizer=tokenizer,
            ideal_max_tokens_ratio=ideal_max_tokens_ratio,
            merge_below_ratio=merge_below_ratio,
            skip_empty_sections=skip_empty_sections,
            heading_sensitive=heading_sensitive,
            max_heading_level=max_heading_level,
            input_format=input_format,
            block_options=block_options,
        )

    def split_text(self, text: str) -> list[str]:
        chunks = self.split_chunks(text)
        return [
            chunk_content(chunk, heading_context=self._heading_context)
            for chunk in chunks
        ]

    def create_documents(
        self,
        texts: list[str],
        metadatas: list[dict[Any, Any]] | None = None,
    ) -> list[LangchainDocument]:
        documents = [
            LangchainDocument(page_content=text, metadata=metadata or {})
            for text, metadata in zip(
                texts, metadatas or [{} for _ in texts], strict=False
            )
        ]
        return self.chunk_documents(documents)


class LumberjackDocumentTransformer(_LumberjackSplittingMixin, BaseDocumentTransformer):
    """Lumberjack splitter as a LangChain document transformer.

    Plug it into LangChain's indexing API
    (``langchain.indexing.api.upsert_and_relocate``-style flows) wherever a
    ``BaseDocumentTransformer`` is accepted. Deterministic document ids
    (``<source id>:<chunk id>``) keep repeated indexing runs incremental.
    Accepts the same keyword configuration as
    :class:`LumberjackTextSplitter`.
    """

    def __init__(
        self,
        *,
        max_tokens: int = 1024,
        splitter: str = "section",
        tokenizer: str = "approx",
        ideal_max_tokens_ratio: float = 0.8,
        merge_below_ratio: float = 0.125,
        skip_empty_sections: bool = True,
        heading_sensitive: bool = True,
        max_heading_level: int | None = None,
        heading_context: bool = False,
        input_format: InputFormat = "auto",
        block_options: Sequence[Any] | None = None,
    ) -> None:
        self._heading_context = heading_context
        self._init_settings(
            max_tokens=max_tokens,
            splitter=splitter,
            tokenizer=tokenizer,
            ideal_max_tokens_ratio=ideal_max_tokens_ratio,
            merge_below_ratio=merge_below_ratio,
            skip_empty_sections=skip_empty_sections,
            heading_sensitive=heading_sensitive,
            max_heading_level=max_heading_level,
            input_format=input_format,
            block_options=block_options,
        )

    def transform_documents(
        self,
        documents: Sequence[LangchainDocument],
        **kwargs: Any,  # noqa: ARG002 - accepted for ABC compatibility
    ) -> Sequence[LangchainDocument]:
        return self.chunk_documents(documents)

    async def atransform_documents(
        self,
        documents: Sequence[LangchainDocument],
        **kwargs: Any,
    ) -> Sequence[LangchainDocument]:
        return self.transform_documents(documents, **kwargs)

"""Native Haystack pipeline components backed by Lumberjack.

Unlike the conversion helpers in :mod:`lumberjack.integrations.haystack`,
the components here plug Lumberjack into Haystack's own pipeline flow:

- :class:`LumberjackDocumentSplitter` is a ``@component`` splitter that
  replaces the built-in ``DocumentSplitter`` slot, e.g. after
  ``MarkdownToDocument`` / ``HTMLToDocument`` converters.

Importing this module requires ``haystack-ai`` (``pip install
lumberjack-py[haystack]``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from haystack import Document as HaystackDocument
from haystack import component

from lumberjack.models import Document as LumberjackSource
from lumberjack.models import InputFormat

from ._components import PipelineSettings, chunk_content
from ._metadata import chunk_metadata

__all__ = ["LumberjackDocumentSplitter"]


@component
class LumberjackDocumentSplitter:
    """Haystack splitter component backed by Lumberjack.

    Wire it into a ``Pipeline`` wherever the built-in ``DocumentSplitter``
    would go: it consumes ``list[Document]`` and emits one ``Document`` per
    Lumberjack chunk, copying the source meta and attaching Lumberjack
    provenance (heading path, token counts, source line ranges). Output ids
    are ``<source id>:<chunk id>`` so repeated runs stay incremental.

    Documents without content pass through unchanged.

    Args:
        max_tokens: Maximum tokens per chunk.
        splitter: Lumberjack splitter name (``section``, ``subtree``,
            ``sibling``, or their ``exact-`` variants).
        tokenizer: Lumberjack token counter (``approx``, ``tiktoken``,
            ``transformers``).
        heading_context: Prefix each split content with its rendered heading
            breadcrumb. Defaults to ``Chunk.body`` only.
        input_format: Format hint for the document contents (``auto``,
            ``markdown``, ``html``).
        block_options: Typed ``lumberjack.block`` options for per-block
            splitting behavior.
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
        self._settings = PipelineSettings.from_values(
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
        self._pipeline = self._settings.build()

    @component.output_types(documents=list[HaystackDocument])
    def run(
        self, documents: list[HaystackDocument]
    ) -> dict[str, list[HaystackDocument]]:
        split: list[HaystackDocument] = []
        for document in documents:
            if document.content is None:
                split.append(document)
                continue
            source_path = document.meta.get("file_path")
            result = self._pipeline.run(
                LumberjackSource(
                    source=document.content,
                    format=self._settings.input_format,
                    source_path=source_path if isinstance(source_path, str) else None,
                )
            )
            for chunk in result.chunks:
                split.append(
                    HaystackDocument(
                        id=f"{document.id}:{chunk.chunk_id}",
                        content=chunk_content(
                            chunk, heading_context=self._heading_context
                        ),
                        meta={**document.meta, **chunk_metadata(chunk)},
                    )
                )
        return {"documents": split}

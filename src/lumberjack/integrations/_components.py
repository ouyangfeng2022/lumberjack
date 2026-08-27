"""Shared configuration for framework pipeline components.

Framework components (node parsers, text splitters, splitter components)
accept the same keyword surface as the CLI/Web adapters and normalize it
into one :class:`PipelineSettings` value that assembles a reusable
Lumberjack pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from lumberjack._internal.options import block_config_from_mapping
from lumberjack._internal.pipeline import Pipeline, build_pipeline
from lumberjack.block import BlockOption
from lumberjack.models import Chunk, InputFormat, render_heading_path

BASE_CONFIG_FIELDS = ("isolated", "split", "max_tokens")
TABLE_CONFIG_FIELDS = ("repeat_header",)


def block_option_to_dict(option: BlockOption) -> dict[str, Any]:
    """Return the JSON-safe serialization of one typed block option."""
    payload: dict[str, Any] = {"kind": str(option.kind)}
    for name in BASE_CONFIG_FIELDS:
        payload[name] = getattr(option, name)
    for name in TABLE_CONFIG_FIELDS:
        if hasattr(option, name):
            payload[name] = getattr(option, name)
    return payload


def block_options_from_values(
    values: Iterable[BlockOption | Mapping[str, Any]] | None,
) -> tuple[BlockOption, ...] | None:
    """Normalize typed block options or their serialized dicts, in order."""
    if values is None:
        return None
    result: list[BlockOption] = []
    for value in values:
        if isinstance(value, Mapping):
            serialized = cast(Mapping[str, Any], value)
            kind = str(serialized["kind"])
            config = {key: item for key, item in serialized.items() if key != "kind"}
            result.append(block_config_from_mapping(kind, config))
        else:
            result.append(value)
    return tuple(result)


@dataclass(slots=True, frozen=True)
class PipelineSettings:
    """Keyword surface shared by every framework pipeline component."""

    max_tokens: int = 1024
    splitter: str = "section"
    tokenizer: str = "approx"
    ideal_max_tokens_ratio: float = 0.8
    merge_below_ratio: float = 0.125
    skip_empty_sections: bool = True
    heading_sensitive: bool = True
    max_heading_level: int | None = None
    input_format: InputFormat = "auto"
    block_options: tuple[BlockOption, ...] | None = None

    def build(self) -> Pipeline:
        """Assemble the Lumberjack pipeline for these settings."""
        return build_pipeline(
            tokenizer=self.tokenizer,
            splitter=self.splitter,
            max_tokens=self.max_tokens,
            ideal_max_tokens_ratio=self.ideal_max_tokens_ratio,
            merge_below_ratio=self.merge_below_ratio,
            skip_empty_sections=self.skip_empty_sections,
            heading_sensitive=self.heading_sensitive,
            max_heading_level=self.max_heading_level,
            block_options=self.block_options,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe settings for component serialization."""
        payload: dict[str, Any] = {
            "max_tokens": self.max_tokens,
            "splitter": self.splitter,
            "tokenizer": self.tokenizer,
            "ideal_max_tokens_ratio": self.ideal_max_tokens_ratio,
            "merge_below_ratio": self.merge_below_ratio,
            "skip_empty_sections": self.skip_empty_sections,
            "heading_sensitive": self.heading_sensitive,
            "max_heading_level": self.max_heading_level,
            "input_format": self.input_format,
        }
        if self.block_options is not None:
            payload["block_options"] = [
                block_option_to_dict(option) for option in self.block_options
            ]
        return payload

    @classmethod
    def from_values(cls, **values: Any) -> PipelineSettings:
        """Build settings from raw values, normalizing block option forms."""
        return cls(
            **{key: value for key, value in values.items() if key != "block_options"},
            block_options=block_options_from_values(values.get("block_options")),
        )


def chunk_content(chunk: Chunk, *, heading_context: bool) -> str:
    """Return the framework text for one chunk.

    With ``heading_context`` the node text is prefixed with the rendered
    Markdown heading breadcrumb so embeddings see the section context;
    otherwise the text is exactly ``Chunk.body``.
    """
    if not heading_context:
        return chunk.body
    path = chunk.ancestor_headings
    if chunk.own_heading is not None:
        path += (chunk.own_heading,)
    heading = render_heading_path(path)
    if not heading:
        return chunk.body
    return f"{heading}\n\n{chunk.body}"


__all__ = [
    "PipelineSettings",
    "block_option_to_dict",
    "block_options_from_values",
    "chunk_content",
]

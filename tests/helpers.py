from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lumberjack.block import (
    BlockConfig,
    BlockKind,
    CustomBlockConfig,
    HTMLTableConfig,
    MarkdownTableConfig,
)
from lumberjack.splitter import (
    ExactSectionSplitter,
    ExactSiblingSplitter,
    ExactSubtreeSplitter,
    SectionSplitter,
    SiblingSplitter,
    SubtreeSplitter,
)
from lumberjack.tokenizer import (
    ApproxCharTokenizer,
    TiktokenTokenizer,
    TransformersTokenizer,
)

# Root of the shared test fixtures, regardless of which test subpackage imports
# this helper. Keeps moved tests from recomputing ``__file__``-relative paths.
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class CharacterTokenizer:
    """Test-only tokenizer that counts each character as one token."""

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(ord(char) for char in text)

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text)


@dataclass(frozen=True)
class BaseParams:
    """Legacy-shaped test fixture converted to the new public block API."""

    isolated: bool = False
    split: bool = True
    max_tokens: int | None = None


@dataclass(frozen=True)
class TableBlockParams(BaseParams):
    repeat_header: bool = True


def resolve_block_options(
    _block_kinds: frozenset[str],
    overrides: dict[str, BaseParams] | None,
) -> dict[str, BaseParams]:
    return dict(overrides or {})


def _block_configs(
    options: dict[str, BaseParams] | None,
) -> list[BlockConfig | MarkdownTableConfig | HTMLTableConfig | CustomBlockConfig]:
    result: list[
        BlockConfig | MarkdownTableConfig | HTMLTableConfig | CustomBlockConfig
    ] = []
    for kind, params in (options or {}).items():
        common = {
            "isolated": params.isolated,
            "split": params.split,
            "max_tokens": params.max_tokens,
        }
        if kind == "table":
            result.append(
                MarkdownTableConfig(
                    **common,
                    repeat_header=getattr(params, "repeat_header", True),
                )
            )
        elif kind == "html_table":
            result.append(
                HTMLTableConfig(
                    **common,
                    repeat_header=getattr(params, "repeat_header", True),
                )
            )
        else:
            try:
                block_kind = BlockKind(kind)
            except ValueError:
                result.append(CustomBlockConfig(kind, **common))
            else:
                result.append(BlockConfig(block_kind, **common))
    return result


def splitter_options(
    *,
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_ratio: float = 0.125,
    skip_empty_sections: bool = True,
    render_headings: bool = True,
    max_heading_level: int | None = None,
    block_options: dict[str, BaseParams] | None = None,
) -> dict[str, Any]:
    return {
        "max_tokens": max_tokens,
        "ideal_max_tokens_ratio": ideal_max_tokens_ratio,
        "merge_below_ratio": merge_below_ratio,
        "skip_empty_sections": skip_empty_sections,
        "render_headings": render_headings,
        "max_heading_level": max_heading_level,
        "block_options": _block_configs(block_options),
    }


def section_options(**kwargs: Any) -> dict[str, Any]:
    """Build direct constructor kwargs for section splitters."""
    options = splitter_options(**kwargs)
    options.pop("merge_below_ratio")
    return options


def create_splitter(
    name: str,
    tokenizer=None,
    options: dict[str, Any] | None = None,
    **kwargs: Any,
):
    config = dict(options or {})
    config.update(kwargs)
    tokenizer = tokenizer or ApproxCharTokenizer()
    normalized = name.strip().lower()
    classes = {
        "sibling": SiblingSplitter,
        "incremental-sibling": SiblingSplitter,
        "exact-sibling": ExactSiblingSplitter,
        "subtree": SubtreeSplitter,
        "incremental-subtree": SubtreeSplitter,
        "exact-subtree": ExactSubtreeSplitter,
        "section": SectionSplitter,
        "incremental-section": SectionSplitter,
        "exact-section": ExactSectionSplitter,
    }
    cls = classes.get(normalized)
    if cls is None:
        raise ValueError(f"Unsupported splitter: {name}")
    if "section" in normalized:
        config.pop("merge_below_ratio", None)
    return cls(tokenizer, **config)


def create_tokenizer(name: str):
    normalized = name.strip().lower()
    if normalized == "approx":
        return ApproxCharTokenizer()
    if normalized == "tiktoken":
        return TiktokenTokenizer()
    if normalized == "transformers":
        return TransformersTokenizer()
    raise ValueError(f"Unsupported tokenizer: {name}")

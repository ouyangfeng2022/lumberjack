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
from lumberjack.mill import Mill
from lumberjack.models import Chunk, InputFormat, Log, Tree
from lumberjack.sawyer import (
    ExactSectionSawyer,
    ExactSiblingSawyer,
    ExactSubtreeSawyer,
    SectionSawyer,
    SiblingSawyer,
    SubtreeSawyer,
)
from lumberjack.scaler import (
    ApproxByteScaler,
    TiktokenScaler,
    TransformersScaler,
)

# Root of the shared test fixtures, regardless of which test subpackage imports
# this helper. Keeps moved tests from recomputing ``__file__``-relative paths.
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class CharacterScaler:
    """Test-only scaler that counts each character as one token."""

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(ord(char) for char in text)

    def scale(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text)


def fell(
    feller,
    source: str | bytes | Path,
    *,
    format: InputFormat = "auto",
    document_title: str | None = None,
    metadata_overrides: dict[str, object] | None = None,
    source_path: str | Path | None = None,
) -> Log:
    return feller.fell(
        Tree(
            source=source,
            format=format,
            document_title=document_title,
            metadata_overrides=dict(metadata_overrides or {}),
            source_path=source_path,
        )
    )


def saw(sawyer, log: Log) -> list[Chunk]:
    return Mill(
        sawyer.scaler,
        skip_empty_sections=sawyer.skip_empty_sections,
    ).mill(log, sawyer.saw(log))


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


def sawyer_options(
    *,
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_ratio: float = 0.125,
    skip_empty_sections: bool = True,
    heading_sensitive: bool = True,
    max_heading_level: int | None = None,
    block_options: dict[str, BaseParams] | None = None,
) -> dict[str, Any]:
    return {
        "max_tokens": max_tokens,
        "ideal_max_tokens_ratio": ideal_max_tokens_ratio,
        "merge_below_ratio": merge_below_ratio,
        "skip_empty_sections": skip_empty_sections,
        "heading_sensitive": heading_sensitive,
        "max_heading_level": max_heading_level,
        "block_options": _block_configs(block_options),
    }


def section_sawyer_options(**kwargs: Any) -> dict[str, Any]:
    """Build direct constructor kwargs for section splitters."""
    return sawyer_options(**kwargs)


def create_sawyer(
    name: str,
    scaler=None,
    options: dict[str, Any] | None = None,
    **kwargs: Any,
):
    config = dict(options or {})
    config.update(kwargs)
    scaler = scaler or ApproxByteScaler()
    normalized = name.strip().lower()
    classes = {
        "sibling": SiblingSawyer,
        "incremental-sibling": SiblingSawyer,
        "exact-sibling": ExactSiblingSawyer,
        "subtree": SubtreeSawyer,
        "incremental-subtree": SubtreeSawyer,
        "exact-subtree": ExactSubtreeSawyer,
        "section": SectionSawyer,
        "incremental-section": SectionSawyer,
        "exact-section": ExactSectionSawyer,
    }
    cls = classes.get(normalized)
    if cls is None:
        raise ValueError(f"Unsupported sawyer: {name}")
    return cls(scaler, **config)


def create_scaler(name: str):
    normalized = name.strip().lower()
    if normalized == "approx":
        return ApproxByteScaler()
    if normalized == "tiktoken":
        return TiktokenScaler()
    if normalized == "transformers":
        return TransformersScaler()
    raise ValueError(f"Unsupported scaler: {name}")

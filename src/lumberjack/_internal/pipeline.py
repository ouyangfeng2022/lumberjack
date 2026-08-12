"""Private adapter shared by the CLI and Web API."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from ..block import BlockOption
from ..feller import AutoFeller
from ..mill import Mill
from ..models import Chunk, InputFormat, Tree
from ..sawyer import (
    ExactSectionSawyer,
    ExactSiblingSawyer,
    ExactSubtreeSawyer,
    SectionSawyer,
    SiblingSawyer,
    SubtreeSawyer,
)
from ..scaler import (
    ApproxByteScaler,
    TiktokenScaler,
    TransformersScaler,
)

_SAWYERS = {
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


def _scaler(name: str):
    normalized = name.strip().lower()
    if normalized == "approx":
        return ApproxByteScaler()
    if normalized == "tiktoken":
        return TiktokenScaler()
    if normalized == "transformers":
        return TransformersScaler()
    raise ValueError(f"Unsupported tokenizer: {name}")


def saw_source(
    source: str | bytes | Path,
    *,
    format: InputFormat = "auto",
    document_title: str | None = None,
    metadata_overrides: Mapping[str, object] | None = None,
    source_path: str | Path | None = None,
    tokenizer: str = "approx",
    splitter: str = "sibling",
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_ratio: float = 0.125,
    skip_empty_sections: bool = True,
    heading_sensitive: bool = True,
    max_heading_level: int | None = None,
    block_options: Iterable[BlockOption] | None = None,
) -> list[Chunk]:
    """Run the configurable built-in pipeline for non-Python interfaces."""
    feller_impl = AutoFeller()
    log = feller_impl.fell(
        Tree(
            source=source,
            format=format,
            document_title=document_title,
            metadata_overrides=dict(metadata_overrides or {}),
            source_path=source_path,
        )
    )
    scaler_impl = _scaler(tokenizer)
    normalized_sawyer = splitter.strip().lower()
    if normalized_sawyer not in _SAWYERS:
        raise ValueError(f"Unsupported splitter: {splitter}")
    common = {
        "max_tokens": max_tokens,
        "ideal_max_tokens_ratio": ideal_max_tokens_ratio,
        "skip_empty_sections": skip_empty_sections,
        "heading_sensitive": heading_sensitive,
        "max_heading_level": max_heading_level,
        "block_options": block_options,
    }
    if normalized_sawyer in {"sibling", "incremental-sibling"}:
        sawyer_impl = SiblingSawyer(
            scaler_impl, merge_below_ratio=merge_below_ratio, **common
        )
    elif normalized_sawyer == "exact-sibling":
        sawyer_impl = ExactSiblingSawyer(
            scaler_impl, merge_below_ratio=merge_below_ratio, **common
        )
    elif normalized_sawyer in {"subtree", "incremental-subtree"}:
        sawyer_impl = SubtreeSawyer(
            scaler_impl, merge_below_ratio=merge_below_ratio, **common
        )
    elif normalized_sawyer == "exact-subtree":
        sawyer_impl = ExactSubtreeSawyer(
            scaler_impl, merge_below_ratio=merge_below_ratio, **common
        )
    elif normalized_sawyer in {"section", "incremental-section"}:
        sawyer_impl = SectionSawyer(
            scaler_impl, merge_below_ratio=merge_below_ratio, **common
        )
    else:
        sawyer_impl = ExactSectionSawyer(
            scaler_impl, merge_below_ratio=merge_below_ratio, **common
        )
    bundles = sawyer_impl.saw(log)
    return Mill(scaler_impl, skip_empty_sections=skip_empty_sections).mill(log, bundles)


BUILTIN_SAWYER_NAMES = tuple(_SAWYERS)

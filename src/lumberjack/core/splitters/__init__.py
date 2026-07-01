from __future__ import annotations

from ..models import SplitOptions
from ..protocols import SplitterProtocol, TokenizerProtocol
from .base import BaseSplitter
from .recursive import RecursiveSplitter
from .section import SectionSplitter

SPLITTER_REGISTRY: dict[str, type[BaseSplitter]] = {
    "recursive": RecursiveSplitter,
    "section": SectionSplitter,
}


def create_splitter(
    name: str,
    tokenizer: TokenizerProtocol | None = None,
    options: SplitOptions | None = None,
) -> SplitterProtocol:
    """Instantiate a splitter by name."""
    normalized = name.strip().lower()
    cls = SPLITTER_REGISTRY.get(normalized)
    if cls is None:
        raise ValueError(f"Unsupported splitter: {name}")
    return cls(tokenizer=tokenizer, options=options)


__all__ = [
    "SPLITTER_REGISTRY",
    "BaseSplitter",
    "RecursiveSplitter",
    "SectionSplitter",
    "create_splitter",
]

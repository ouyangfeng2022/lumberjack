from __future__ import annotations

from ..models import SplitOptions
from ..protocols import SplitterProtocol, TokenizerProtocol
from ..tokenizers import ApproxCharTokenizer
from .base import BaseSplitter
from .recursive import (
    ExactRecursiveSplitter,
    IncrementalRecursiveSplitter,
    RecursiveSplitter,
)
from .section import (
    ExactSectionSplitter,
    IncrementalSectionSplitter,
    SectionSplitter,
)

# Splitter topology + counting strategy, keyed by name.  ``recursive`` and
# ``section`` default to the exact (full-recount) variants for backward
# compatibility; pass ``incremental-recursive`` / ``incremental-section`` to
# opt into the additive-estimate path.
SPLITTER_REGISTRY: dict[str, type[BaseSplitter]] = {
    "recursive": ExactRecursiveSplitter,
    "exact-recursive": ExactRecursiveSplitter,
    "incremental-recursive": IncrementalRecursiveSplitter,
    "section": ExactSectionSplitter,
    "exact-section": ExactSectionSplitter,
    "incremental-section": IncrementalSectionSplitter,
}


def create_splitter(
    name: str,
    tokenizer: TokenizerProtocol | None = None,
    options: SplitOptions | None = None,
) -> SplitterProtocol:
    """Instantiate a splitter by name.

    Args:
        name: Splitter name.  One of ``"recursive"`` (alias for
            ``"exact-recursive"``, the default), ``"section"`` (alias for
            ``"exact-section"``), ``"exact-recursive"``,
            ``"incremental-recursive"``, ``"exact-section"``, or
            ``"incremental-section"``.  Exact splitters fully recount rendered
            text at every budget decision; incremental splitters use an
            additive estimate + 8-char separator-delta window.
        tokenizer: Tokenizer engine.  Defaults to :class:`ApproxCharTokenizer`.
        options: Split options.

    Raises:
        ValueError: If *name* is not a registered splitter.
    """
    normalized = name.strip().lower()
    cls = SPLITTER_REGISTRY.get(normalized)
    if cls is None:
        raise ValueError(f"Unsupported splitter: {name}")
    return cls(tokenizer=tokenizer or ApproxCharTokenizer(), options=options)


__all__ = [
    "SPLITTER_REGISTRY",
    "BaseSplitter",
    "ExactRecursiveSplitter",
    "ExactSectionSplitter",
    "IncrementalRecursiveSplitter",
    "IncrementalSectionSplitter",
    "RecursiveSplitter",
    "SectionSplitter",
    "create_splitter",
]

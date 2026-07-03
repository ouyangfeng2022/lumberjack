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
    ExactSectionFlatSplitter,
    ExactSectionSplitter,
    IncrementalSectionFlatSplitter,
    IncrementalSectionSplitter,
    SectionFlatSplitter,
    SectionSplitter,
)

# Splitter topology + counting strategy, keyed by name.  ``recursive`` and
# ``section`` default to the exact (full-recount) variants for backward
# compatibility; pass ``incremental-recursive`` / ``incremental-section`` to
# opt into the additive-estimate path.  ``section-flat`` variants disable
# subtree-collapse and tail-fragment merging.
SPLITTER_REGISTRY: dict[str, type[BaseSplitter]] = {
    "recursive": ExactRecursiveSplitter,
    "exact-recursive": ExactRecursiveSplitter,
    "incremental-recursive": IncrementalRecursiveSplitter,
    "section": ExactSectionSplitter,
    "exact-section": ExactSectionSplitter,
    "section-flat": ExactSectionFlatSplitter,
    "exact-section-flat": ExactSectionFlatSplitter,
    "incremental-section": IncrementalSectionSplitter,
    "incremental-section-flat": IncrementalSectionFlatSplitter,
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
            ``"exact-section"``), ``"section-flat"`` (alias for
            ``"exact-section-flat"``), ``"exact-recursive"``,
            ``"incremental-recursive"``, ``"exact-section"``,
            ``"incremental-section"``, ``"exact-section-flat"``, or
            ``"incremental-section-flat"``.  Exact splitters fully recount
            rendered text at every budget decision; incremental splitters
            use an additive estimate + 8-char separator-delta window.
            ``section-flat`` variants disable subtree-collapse and
            tail-fragment merging.
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
    "ExactSectionFlatSplitter",
    "ExactSectionSplitter",
    "IncrementalRecursiveSplitter",
    "IncrementalSectionFlatSplitter",
    "IncrementalSectionSplitter",
    "RecursiveSplitter",
    "SectionFlatSplitter",
    "SectionSplitter",
    "create_splitter",
]

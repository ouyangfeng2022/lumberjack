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
    ExactSubtreeSplitter,
    IncrementalSectionSplitter,
    IncrementalSubtreeSplitter,
    SectionSplitter,
    SubtreeSplitter,
)

# Splitter topology + counting strategy, keyed by name.  ``recursive``,
# ``subtree``, and ``section`` default to the exact (full-recount) variants;
# pass ``incremental-recursive`` / ``incremental-subtree`` /
# ``incremental-section`` to opt into the additive-estimate path.  The
# ``section`` family is per-heading — it emits one chunk per heading section's
# direct body with no subtree-collapse and no tail-fragment merging.
SPLITTER_REGISTRY: dict[str, type[BaseSplitter]] = {
    "recursive": ExactRecursiveSplitter,
    "exact-recursive": ExactRecursiveSplitter,
    "incremental-recursive": IncrementalRecursiveSplitter,
    "subtree": ExactSubtreeSplitter,
    "exact-subtree": ExactSubtreeSplitter,
    "incremental-subtree": IncrementalSubtreeSplitter,
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
            ``"exact-recursive"``, the default), ``"subtree"`` (alias for
            ``"exact-subtree"``), ``"section"`` (alias for
            ``"exact-section"``), ``"exact-recursive"``,
            ``"incremental-recursive"``, ``"exact-subtree"``,
            ``"incremental-subtree"``, ``"exact-section"``, or
            ``"incremental-section"``.  Exact splitters fully recount
            rendered text at every budget decision; incremental splitters
            use an additive estimate + 8-char separator-delta window.
            ``subtree`` is subtree-first (collapses a fitting subtree into
            one chunk, with tail-fragment merging); ``section`` is
            per-heading (no subtree-collapse, no tail-fragment merging).
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
    "ExactSubtreeSplitter",
    "IncrementalRecursiveSplitter",
    "IncrementalSectionSplitter",
    "IncrementalSubtreeSplitter",
    "RecursiveSplitter",
    "SectionSplitter",
    "SubtreeSplitter",
    "create_splitter",
]

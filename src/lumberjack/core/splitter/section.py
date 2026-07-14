from __future__ import annotations

from .base import BaseSplitter
from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin
from .topology.section import SectionTopologyMixin


class ExactSectionSplitter(ExactCountingMixin, SectionTopologyMixin, BaseSplitter):
    """Per-heading section splitter without subtree-collapse or tail merging.

    Emits one chunk per heading section's direct body and recurses into
    children.  This variant:

    1. Never collapses an entire subtree into a single chunk (no
       subtree-collapse short-circuit — see :class:`ExactSubtreeSplitter` for
       that topology).
    2. Never calls :meth:`_merge_small_chunks` — tail-fragment merging is
       fully disabled in this variant, regardless of ``merge_below_ratio``.

    Oversized section bodies are still split by token budget respecting
    ``block_options`` (standalone isolation, splittable kinds, per-block
    budgets).  Every budget decision fully recounts the rendered candidate
    text.

    Registered as ``"section"`` (the default) and ``"exact-section"``.
    Works with any tokenizer.
    """


class IncrementalSectionSplitter(
    IncrementalCountingMixin, SectionTopologyMixin, BaseSplitter
):
    """Per-heading section splitter (incremental estimate) without subtree-collapse or tail merging.

    Same per-section topology as :class:`ExactSectionSplitter`, but uses
    the additive incremental estimate path: the subtree is pre-measured and
    budget decisions use a running estimate rather than full rendered
    recounts.

    No subtree-collapse short-circuit and no tail-fragment merging.

    Registered as ``"incremental-section"``.  Works with any tokenizer.
    """


# Backward-compatible alias: the default ``section`` splitter is the exact one.
SectionSplitter = ExactSectionSplitter

__all__ = [
    "ExactSectionSplitter",
    "IncrementalSectionSplitter",
    "SectionSplitter",
]

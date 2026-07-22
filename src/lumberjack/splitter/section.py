from __future__ import annotations

from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin
from .topology.section import SectionTopologyMixin


class ExactSectionSplitter(ExactCountingMixin, SectionTopologyMixin):
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

    Publicly exposed as ``ExactSectionSplitter`` and selected by the
    ``exact-section`` CLI/Web integration name. Works with any tokenizer.
    """


class IncrementalSectionSplitter(IncrementalCountingMixin, SectionTopologyMixin):
    """Per-heading section splitter (incremental estimate) without subtree-collapse or tail merging.

    Same per-section topology as :class:`ExactSectionSplitter`, but uses
    the additive incremental estimate path: the subtree is pre-measured and
    budget decisions use a running estimate rather than full rendered
    recounts.

    No subtree-collapse short-circuit and no tail-fragment merging.

    This is also the unprefixed public ``SectionSplitter`` default. Works with
    any tokenizer.
    """


# The unprefixed public splitter uses incremental counting by default.
SectionSplitter = IncrementalSectionSplitter

__all__ = [
    "ExactSectionSplitter",
    "IncrementalSectionSplitter",
    "SectionSplitter",
]

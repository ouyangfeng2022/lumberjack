from __future__ import annotations

from .exact import ExactCountingMixin
from .incremental import IncrementalCountingMixin
from .topology.section import SectionTopologyMixin


class ExactSectionSawyer(ExactCountingMixin, SectionTopologyMixin):
    """Per-heading section sawyer without subtree-collapse.

    Emits one bundle per heading section's direct body and recurses into
    children.  This variant:

    1. Never collapses an entire subtree into a single bundle (no
       subtree-collapse short-circuit — see :class:`ExactSubtreeSawyer` for
       that topology).
    2. Merges only adjacent same-heading paragraph tails, bottom-up, according
       to ``merge_below_ratio``.  Non-text block bundles remain isolated.

    Oversized section bodies are still split by token budget respecting
    ``block_options`` (standalone isolation, splittable kinds, per-block
    budgets).  Every budget decision fully recounts the rendered candidate
    text.

    Publicly exposed as ``ExactSectionSawyer`` and selected by the
    ``exact-section`` CLI/Web integration name. Works with any scaler.
    """


class IncrementalSectionSawyer(IncrementalCountingMixin, SectionTopologyMixin):
    """Per-heading section sawyer using incremental estimates.

    Same per-section topology as :class:`ExactSectionSawyer`, but uses
    the additive incremental estimate path: the subtree is pre-measured and
    budget decisions use a running estimate rather than full rendered
    recounts.

    It has no subtree-collapse short-circuit.  Small adjacent paragraph tails
    from the same heading are merged bottom-up according to
    ``merge_below_ratio``; non-text block bundles are not merged.

    This is also the unprefixed public ``SectionSawyer`` default. Works with
    any scaler.
    """


# The unprefixed public sawyer uses incremental counting by default.
SectionSawyer = IncrementalSectionSawyer

__all__ = [
    "ExactSectionSawyer",
    "IncrementalSectionSawyer",
    "SectionSawyer",
]

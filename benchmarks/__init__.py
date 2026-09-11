"""Reproducible benchmark harness for Lumberjack.

This package is deliberately kept outside the distributable ``lumberjack``
runtime.  It is useful to contributors and evaluators, but it is not part of
the library's public API.
"""

# Standard note attached by ``benchmarks.run`` to every non-native adapter;
# it is a comparability statement, not an oracle diagnostic. Aggregation in
# ``benchmarks.compare`` filters on this exact string.
PROVENANCE_NOTE = (
    "adapter output has no normalized source-line provenance; "
    "provenance coverage is not directly comparable"
)

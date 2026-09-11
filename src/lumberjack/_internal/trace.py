"""Bounded selection of public pipeline trace stages for integrations."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Literal, cast

from ..models import PipelineTrace, _json_value

TraceStage = Literal[
    "input", "extraction", "document", "drafts", "chunks", "diagnostics"
]
TRACE_STAGES: tuple[TraceStage, ...] = (
    "input",
    "extraction",
    "document",
    "drafts",
    "chunks",
    "diagnostics",
)


def select_trace_stages(
    trace: PipelineTrace,
    stages: Iterable[TraceStage],
    *,
    max_bytes: int,
) -> dict[str, object]:
    """Select requested stages and reject a serialized result above *max_bytes*."""
    selected = tuple(dict.fromkeys(stages))
    if max_bytes <= 0:
        raise ValueError("trace max_bytes must be greater than 0")
    unknown = [stage for stage in selected if stage not in TRACE_STAGES]
    if unknown:
        raise ValueError(
            f"Unknown trace stage(s): {', '.join(unknown)}. "
            f"Valid stages: {', '.join(TRACE_STAGES)}"
        )
    # Serialize only the requested stages; materializing the whole trace
    # would double peak memory for large documents.
    result = {stage: _json_value(getattr(trace, stage)) for stage in selected}
    try:
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
    except TypeError as exc:
        raise ValueError(f"Trace stage is not JSON serializable: {exc}") from exc
    if len(encoded) > max_bytes:
        raise ValueError(
            f"Selected trace stages exceed the {max_bytes}-byte response limit"
        )
    return cast(dict[str, object], result)


__all__ = ["TRACE_STAGES", "TraceStage", "select_trace_stages"]

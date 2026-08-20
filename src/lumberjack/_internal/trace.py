"""Bounded selection of public pipeline trace stages for integrations."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Literal, cast

from ..models import PipelineTrace

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
    payload = trace.to_dict()
    result = {stage: payload[stage] for stage in selected}
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > max_bytes:
        raise ValueError(
            f"Selected trace stages exceed the {max_bytes}-byte response limit"
        )
    return cast(dict[str, object], result)


__all__ = ["TRACE_STAGES", "TraceStage", "select_trace_stages"]

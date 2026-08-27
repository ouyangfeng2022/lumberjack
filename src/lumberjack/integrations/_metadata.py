"""Shared, JSON-safe metadata for external RAG framework adapters."""

from __future__ import annotations

from typing import Any, cast

from lumberjack.models import Chunk
from lumberjack.serialization import chunk_to_dict


def chunk_metadata(chunk: Chunk) -> dict[str, object]:
    """Return complete retrieval metadata for ``chunk`` without its body.

    The result only contains JSON-compatible values.  It preserves Lumberjack
    provenance, including source locations, for every framework adapter.
    """
    payload = chunk_to_dict(chunk)
    payload.pop("body")
    return cast(dict[str, object], payload)


def metadata_keys(metadata: dict[str, object]) -> list[str]:
    """Return metadata keys in insertion order for framework exclusion APIs."""
    return list(cast(dict[str, Any], metadata))

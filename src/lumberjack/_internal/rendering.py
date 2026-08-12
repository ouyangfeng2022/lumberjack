from __future__ import annotations

RENDER_SEPARATOR = "\n\n"


def join_rendered_blocks(parts: list[str]) -> str:
    """Join non-empty canonical rendered blocks with blank-line separators."""
    cleaned = [part for part in parts if part]
    return RENDER_SEPARATOR.join(cleaned)


__all__ = ["RENDER_SEPARATOR", "join_rendered_blocks"]

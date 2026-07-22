from __future__ import annotations


def join_rendered_blocks(parts: list[str]) -> str:
    """Join non-empty canonical rendered blocks with blank-line separators."""
    cleaned = [part for part in parts if part]
    return "\n\n".join(cleaned)


__all__ = ["join_rendered_blocks"]

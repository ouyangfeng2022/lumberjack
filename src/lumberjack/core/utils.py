from __future__ import annotations


def join_markdown(parts: list[str]) -> str:
    """Join non-empty Markdown parts with double-newline separators."""
    cleaned = [part for part in parts if part]
    return "\n\n".join(cleaned)


__all__ = ["join_markdown"]

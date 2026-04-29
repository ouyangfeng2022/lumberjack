from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import HeadingPath


def join_markdown(parts: list[str]) -> str:
    """Join non-empty Markdown parts with double-newline separators."""
    cleaned = [part.strip("\n") for part in parts if part and part.strip()]
    return "\n\n".join(cleaned).strip()


def render_heading(level: int, title: str) -> str:
    """Render a heading as a Markdown ATX heading string."""
    if level <= 0:
        return title.strip()
    return f"{'#' * level} {title.strip()}"


def render_heading_path(path: HeadingPath) -> str:
    """Render a full heading breadcrumb path as nested Markdown headings."""
    return join_markdown([render_heading(level, title) for level, title in path])

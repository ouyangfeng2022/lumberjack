from __future__ import annotations

from collections.abc import Iterable

from ..models import HeadingPath
from ..utils import join_markdown


def render_heading_path(path: HeadingPath) -> str:
    """Render a full heading breadcrumb path as nested Markdown headings."""

    def _render_heading(level: int, title: str) -> str:
        """Render a heading as a Markdown ATX heading string."""
        if level <= 0:
            return title.strip()
        return f"{'#' * level} {title.strip()}"

    return join_markdown([_render_heading(level, title) for level, title in path])


def common_heading_path(paths: Iterable[HeadingPath]) -> HeadingPath:
    iterator = iter(paths)
    first = tuple(next(iterator, ()))
    common = first
    for path in iterator:
        limit = min(len(common), len(path))
        index = 0
        while index < limit and common[index] == path[index]:
            index += 1
        common = common[:index]
        if not common:
            break
    return common


__all__ = ["common_heading_path", "render_heading_path"]

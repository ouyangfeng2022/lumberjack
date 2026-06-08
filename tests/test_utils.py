from __future__ import annotations

from lumberjack.utils import join_markdown


def test_join_markdown_does_not_strip_part_content() -> None:
    assert join_markdown(["  a  ", "b"]) == "  a  \n\nb"

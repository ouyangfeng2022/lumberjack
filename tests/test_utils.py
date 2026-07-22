from __future__ import annotations

from lumberjack.core.utils import join_rendered_blocks


def test_join_rendered_blocks_does_not_strip_part_content() -> None:
    assert join_rendered_blocks(["  a  ", "b"]) == "  a  \n\nb"

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from markdown_it import MarkdownIt
    from markdown_it.rules_block import StateBlock
    from markdown_it.rules_inline import StateInline


BRACKETS_MATH_INLINE_RE = re.compile(r"^\\\((.+?)\\\)", re.DOTALL)
BRACKETS_MATH_BLOCK_EQNO_RE = re.compile(
    r"^\\\[(((?!\\\]|\\\[)[\s\S])+?)\\\]\s*?\(([^)$\r\n]+?)\)",
    re.M,
)
BRACKETS_MATH_BLOCK_RE = re.compile(r"^\\\[([\s\S]+?)\\\]", re.M)


def brackets_math_plugin(md: MarkdownIt) -> None:
    md.inline.ruler.before("escape", "math_inline", _inline_func)
    md.block.ruler.before(
        "fence", "math_block_eqno", make_block_func(allow_labels=True)
    )
    md.block.ruler.before("fence", "math_block", make_block_func(allow_labels=False))


def _inline_func(state: StateInline, silent: bool) -> bool:
    src = state.src
    tag = "\\("
    if not src.startswith(tag, state.pos):
        return False
    match = BRACKETS_MATH_INLINE_RE.match(src[state.pos :])
    if match is None:
        return False

    if not silent:
        token = state.push("math_inline", "math", 0)
        token.content = match.group(1)
        token.markup = tag

    state.pos += match.end()
    return True


def make_block_func(
    allow_labels: bool = True,
) -> Callable[[StateBlock, int, int, bool], bool]:

    def _block_func(
        state: StateBlock, begLine: int, endLine: int, silent: bool
    ) -> bool:
        begin = state.bMarks[begLine] + state.tShift[begLine]
        src = state.src
        tag = "\\["
        if not src.startswith(tag, begin):
            return False

        re_c = BRACKETS_MATH_BLOCK_EQNO_RE if allow_labels else BRACKETS_MATH_BLOCK_RE
        name = "math_block_eqno" if allow_labels else "math_block"
        match = re_c.match(src[begin:])
        if match is None:
            return False

        if state.parentType == "blockquote" and "\n" in match.group(1):
            return False

        endpos = begin + match.end() - 1
        next_line = begLine + 1

        line = begLine
        while line < endLine:
            if state.bMarks[line] <= endpos <= state.eMarks[line]:
                next_line = line + 1
                break
            line += 1

        if not silent:
            token = state.push(name, "math", 0)
            token.block = True
            token.content = match.group(1)
            if match.lastindex is not None:
                token.info = match.group(match.lastindex)
            token.info = match.group(0)
            token.markup = tag
            token.map = [begLine, next_line]

        state.line = next_line
        return True

    return _block_func

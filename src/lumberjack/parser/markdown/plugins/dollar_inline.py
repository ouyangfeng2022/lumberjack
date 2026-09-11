"""Corrected inline ``$...$`` math rule for the Markdown parser.

The upstream ``mdit_py_plugins`` dollarmath rule has two defects that matter
for this project's currency-vs-math contract:

1. With ``allow_digits=False`` it probes ``state.src[state.pos - 1]`` to reject
   a digit before the opening ``$`` — at ``pos == 0`` Python's negative index
   silently reads the *last* character, so ``"$x$ costs 3"`` at the start of a
   paragraph is misrejected as currency.
2. With ``allow_space=True`` (needed for the supported ``$ a+b=c $`` dialect)
   prose like ``"a $ b $ c"`` or ``"price $ 5 and $ 10"`` parses as math.

This rule keeps the supported dialect while fixing both: the boundary checks
are bounds-safe, and a space-surrounded candidate must contain at least one
non-alphanumeric character (math punctuation) to count as math.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from markdown_it.rules_inline import StateInline

__all__ = ["corrected_math_inline"]


def _is_escaped(src: str, pos: int) -> bool:
    backslashes = 0
    index = pos - 1
    while index >= 0 and src[index] == "\\":
        backslashes += 1
        index -= 1
    return bool(backslashes % 2)


def _is_wordy(content: str) -> bool:
    """True when space-surrounded content has no math punctuation at all."""
    return all(character.isalnum() or character.isspace() for character in content)


def corrected_math_inline(state: StateInline, silent: bool) -> bool:
    """Inline ``$...$`` math with currency-safe boundary rules."""
    src = state.src
    pos = state.pos

    if src[pos] != "$":
        return False
    if _is_escaped(src, pos):
        return False
    if pos + 1 >= len(src):
        return False
    if pos > 0 and src[pos - 1].isdigit():
        # "1$x$" reads as currency-adjacent text, not math.
        return False

    end = src.find("$", pos + 1)
    while end != -1 and _is_escaped(src, end):
        end = src.find("$", end + 1)
    if end == -1:
        return False
    if end + 1 < len(src) and src[end + 1].isdigit():
        # "$x$2" and "price $5 and $10" stay text.
        return False

    content = src[pos + 1 : end]
    if not content:
        return False
    if content[0].isspace() and content[-1].isspace() and _is_wordy(content.strip()):
        # "a $ b $ c" / "price $ 5 and $ 10": space-surrounded wordy prose is
        # not math, while "$ a+b=c $" keeps its math punctuation.
        return False

    if not silent:
        token = state.push("math_inline", "math", 0)
        token.content = content
        token.markup = "$"
    state.pos = end + 1
    return True

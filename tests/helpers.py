from __future__ import annotations


class CharacterTokenizer:
    """Test-only tokenizer that counts each character as one token.

    Exact-count engine: the splitter fully recounts rendered text at every
    budget decision and never uses the incremental estimate path.
    """

    is_exact = True

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(ord(char) for char in text)

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text)


class IncrementalCharacterTokenizer(CharacterTokenizer):
    """Character-count tokenizer that drives the additive incremental path.

    Non-exact (``is_exact = False``): the splitter pre-measures sections,
    uses its own 8-char separator-delta window for joins, and only fully
    recounts at finalization.  Used by tests that verify the incremental
    estimate behavior (8-char tail window, no oversized rendering recounts).
    """

    is_exact = False

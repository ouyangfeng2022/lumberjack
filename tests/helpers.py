from __future__ import annotations


class CharacterTokenizer:
    """Test-only tokenizer that counts each character as one token."""

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(ord(char) for char in text)

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text)

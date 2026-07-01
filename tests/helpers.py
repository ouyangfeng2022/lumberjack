from __future__ import annotations


class CharacterTokenizer:
    """Test-only tokenizer that counts each character as one token."""

    def __init__(self, token_counter: str = "accurate") -> None:
        self.token_counter = token_counter

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(ord(char) for char in text)

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text)

    @property
    def is_incremental(self) -> bool:
        return self.token_counter == "incremental"

    def count_text(self, text: str) -> int:
        return self.count(text, cache=True)

    def count_budget_text(self, text: str, *, estimated_count: int) -> int:
        if self.token_counter == "incremental":
            return estimated_count
        return self.count_text(text)

    def count_estimated_text(self, text: str, *, estimated_count: int) -> int:
        if self.token_counter == "incremental":
            return estimated_count
        return self.count_text(text)

    def separator_delta(self, text: str, separator: str) -> int:
        if not text:
            return 0
        if self.is_incremental:
            text = text.rstrip("\n")[-8:]
        return self.count(f"{text}{separator}", cache=True) - self.count(
            text, cache=True
        )

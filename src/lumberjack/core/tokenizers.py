from __future__ import annotations

from ..base.interfaces import TokenizerProtocol


class TiktokenTokenizer(TokenizerProtocol):
    """Tokenizer backed by the tiktoken library for model-aware BPE token counting."""

    def __init__(self, model: str = "gpt-4o-mini"):
        try:
            import tiktoken
        except ImportError as exc:
            raise RuntimeError(
                "tiktoken is not installed. Install with `pip install lumberjack[tokenizers]`."
            ) from exc

        self.encoding = tiktoken.encoding_for_model(model)

    def encode(self, text: str) -> list[int]:
        return self.encoding.encode(text)

    def count(self, text: str) -> int:
        return len(self.encode(text))


class SimpleCharTokenizer:
    """Character-level tokenizer that counts each character as one token."""

    def encode(self, text: str) -> list[int]:
        return [ord(c) for c in text]

    def count(self, text: str) -> int:
        return len(text)


def create_tokenizer(name: str) -> TokenizerProtocol:
    """Instantiate a tokenizer by name (``"simple"`` or ``"tiktoken"``)."""
    normalized = name.strip().lower()
    if normalized == "simple":
        return SimpleCharTokenizer()
    if normalized == "tiktoken":
        return TiktokenTokenizer()
    raise ValueError(f"Unsupported tokenizer: {name}")

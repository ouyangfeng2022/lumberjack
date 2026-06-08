from __future__ import annotations

from threading import RLock

from ..base.interfaces import TokenizerProtocol


class TiktokenTokenizer(TokenizerProtocol):
    """Tokenizer backed by the tiktoken library."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_cache_size: int = 1000,
    ):
        import tiktoken
        from cachetools import LRUCache

        self.encoding = tiktoken.encoding_for_model(model)

        self._cache: LRUCache[str, tuple[int, ...]] = LRUCache(maxsize=max_cache_size)

        self._lock = RLock()

    def encode(
        self,
        text: str,
        *,
        cache: bool = False,
    ) -> tuple[int, ...]:
        if not text:
            return ()

        if cache:
            with self._lock:
                cached = self._cache.get(text)
                if cached is not None:
                    return cached
        token_ids = tuple(self.encoding.encode(text))

        if cache:
            with self._lock:
                self._cache[text] = token_ids

        return token_ids

    def count(
        self,
        text: str,
        *,
        cache: bool = False,
    ) -> int:
        if not text:
            return 0
        return len(self.encode(text, cache=cache))

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()


class SimpleCharTokenizer(TokenizerProtocol):
    """Character-level tokenizer that counts each character as one token."""

    def encode(self, text: str, *, cache=False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(ord(c) for c in text)

    def count(self, text: str, *, cache=False) -> int:  # noqa: ARG002
        return len(text)


def create_tokenizer(name: str) -> TokenizerProtocol:
    """Instantiate a tokenizer by name (``"simple"`` or ``"tiktoken"``)."""
    normalized = name.strip().lower()
    if normalized == "simple":
        return SimpleCharTokenizer()
    if normalized == "tiktoken":
        return TiktokenTokenizer()
    raise ValueError(f"Unsupported tokenizer: {name}")

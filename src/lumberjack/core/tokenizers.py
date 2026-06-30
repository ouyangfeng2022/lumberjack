from __future__ import annotations

from threading import RLock
from typing import Literal, Protocol, TypeAlias

from .protocols import TokenizerProtocol

CountMode: TypeAlias = Literal["exact", "incremental"]  # noqa: UP040


class TokenCountStrategy(Protocol):
    """Abstracts how the splitter counts tokens at internal decision sites.

    Two implementations exist: :class:`ExactTokenCount` counts the fully
    rendered text at every site (used by the ``simple`` and ``accurate``
    modes); :class:`IncrementalTokenCount` reuses the additive / separator-delta
    arithmetic (used by the ``estimate`` mode).
    """

    def count_body(self, parts: list[str], separator: str) -> int: ...

    def count_text(self, text: str) -> int: ...

    def separator_delta(self, text: str, separator: str) -> int: ...


class TiktokenTokenizer(TokenizerProtocol):
    """Tokenizer backed by the tiktoken library."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_cache_size: int = 1000,
        default_cache: bool = False,
    ):
        import tiktoken
        from cachetools import LRUCache

        self.encoding = tiktoken.encoding_for_model(model)
        self.default_cache = default_cache
        self._cache: LRUCache[str, tuple[int, ...]] = LRUCache(maxsize=max_cache_size)

        self._lock = RLock()

    def encode(
        self,
        text: str,
        *,
        cache: bool | None = None,
    ) -> tuple[int, ...]:
        if not text:
            return ()

        use_cache = self.default_cache if cache is None else cache
        if use_cache:
            with self._lock:
                cached = self._cache.get(text)
                if cached is not None:
                    return cached
        token_ids = tuple(self.encoding.encode(text))

        if use_cache:
            with self._lock:
                self._cache[text] = token_ids

        return token_ids

    def count(
        self,
        text: str,
        *,
        cache: bool | None = None,
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


class ApproxCharTokenizer(TokenizerProtocol):
    """Approximate tokenizer that estimates tokens as ``len(text) // 4``.

    A common industry rule of thumb (character count divided by four) used by
    the ``token_counter="simple"`` counting mode.  The splitter only uses
    :meth:`count`; :meth:`encode` is a protocol placeholder.
    """

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return ()

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text) // 4


class ExactTokenCount:
    """Counting strategy that counts fully rendered text at every site."""

    def __init__(self, tokenizer: TokenizerProtocol) -> None:
        self.tokenizer = tokenizer

    def count_body(self, parts: list[str], separator: str) -> int:
        rendered = separator.join(parts)
        return self.tokenizer.count(rendered, cache=True)

    def count_text(self, text: str) -> int:
        return self.tokenizer.count(text, cache=True)

    def separator_delta(self, text: str, separator: str) -> int:
        if not text:
            return self.tokenizer.count(separator, cache=True)
        return self.tokenizer.count(
            f"{text}{separator}", cache=True
        ) - self.tokenizer.count(text, cache=True)


class IncrementalTokenCount:
    """Counting strategy that reuses additive / separator-window arithmetic.

    ``separator_delta`` mirrors the original ``_separator_delta_after`` 8-char
    tail-window approximation so the incremental mode reproduces the legacy
    estimate behavior.
    """

    _DELTA_WINDOW = 8

    def __init__(self, tokenizer: TokenizerProtocol) -> None:
        self.tokenizer = tokenizer

    def count_body(self, parts: list[str], separator: str) -> int:
        if not parts:
            return 0
        rendered = separator.join(parts)
        return self.tokenizer.count(rendered, cache=True)

    def count_text(self, text: str) -> int:
        return self.tokenizer.count(text, cache=True)

    def separator_delta(self, text: str, separator: str) -> int:
        if not text:
            return 0
        tail = text.rstrip("\n")[-self._DELTA_WINDOW :]
        return self.tokenizer.count(
            f"{tail}{separator}", cache=True
        ) - self.tokenizer.count(tail, cache=True)


def create_tokenizer(name: str) -> TokenizerProtocol:
    """Instantiate a tokenizer by name (``"simple"`` or ``"tiktoken"``)."""
    normalized = name.strip().lower()
    if normalized == "simple":
        return SimpleCharTokenizer()
    if normalized == "tiktoken":
        return TiktokenTokenizer()
    raise ValueError(f"Unsupported tokenizer: {name}")
